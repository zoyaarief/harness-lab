# harness-lab

A small, configurable **coding agent harness** for measuring how harness design choices
change two things at once:

1. **Task success.** Does the agent solve the task?
2. **Inference workload.** How many prompt tokens does each design send? How many of
   them can the server serve from its KV cache? What does that do to time to first
   token (TTFT), decode time, and the split between model time and tool time?

The harness runs as a custom agent inside [Harbor](https://github.com/harbor-framework/harbor),
the evaluation framework behind Terminal-Bench. It talks to any OpenAI-compatible endpoint.
The main experiments run **for free on a MacBook**, using `llama.cpp` and an open model.

> Results: *in progress.* See [Results](#results).

## Why this matters

Coding agents send an unusual kind of traffic to inference servers:

- prompts are long, and they grow on every turn;
- outputs are short;
- the GPU sits idle while tools run between turns.

A server can only reuse cached attention state (the KV cache) for the part of a prompt
that is byte-for-byte identical to an earlier request. So the way a harness manages its
context decides how much prefill work the GPU actually does. This project measures that
directly.

## What the harness does

```
Harbor task container (Docker)  <-- bash / view_file / edit_file / submit --
        |                                                                   |
        '-- stdout, exit code -->  harness loop  -- streamed request -->  model server
                                   (context strategy,                     (llama.cpp / vLLM /
                                    tool set, limits)                      NVIDIA API catalog)
                                        |
                                        '--> harness_trace.jsonl: per call TTFT, inter-token
                                             gaps, prompt / cached / output tokens, server
                                             prefill time, tool time
```

The settings under study (see [`configs/`](configs)):

| Variant | Context strategy | What changes for the server |
|---|---|---|
| `full` | Keep every message | Largest prompts. The prefix never changes, so the cache hits. |
| `truncate` | Cap each tool output at 2,000 chars when it is added | Smaller prompts, and the prefix still never changes. |
| `rolling` | Show only the last 3 tool outputs; elide older ones on every call | Smaller prompts, but the prefix changes each turn, so the cache misses. |
| `compaction` | Summarize the history once the prompt passes ~12k tokens | One cache miss per compaction. |
| `bash-only` | Full history, but no view/edit tools | Tool-design ablation. |
| `reasoning` | Full history, thinking mode on | Many more output tokens. |

## Benchmark: `py-bugfix-lite`

Twelve small Python tasks in Harbor format ([`tasks/py-bugfix-lite`](tasks/py-bugfix-lite)):

- **Kinds of task:** off-by-one errors, LRU recency, Decimal money math, deep-merge
  mutation, JSON-schema error paths, a CLI feature, a noisy 4,000-line log to parse,
  and a large test suite with very long failure output.
- **Grading:** the agent sees visible tests, but the verifier runs *hidden* tests that
  check every stated requirement.
- **Disk:** all tasks share two image layers, so the whole set costs little disk space.
- **Validation:** `scripts/check_tasks.py` checks that every task's tests fail on the
  shipped code and pass with the reference fix. Harbor's `oracle` agent scores 1.0 on
  the tasks and the `nop` agent (does nothing) scores 0.0.

A small open model can solve some of these, so pass rates fall between 0% and 100% and
differences between variants are measurable. Terminal-Bench 2.0 is too hard for an 8B
model and too large for a laptop disk.

## Quick start

Requirements: macOS or Linux, Docker, [uv](https://docs.astral.sh/uv/), and
[llama.cpp](https://github.com/ggml-org/llama.cpp) (`brew install uv llama.cpp`).

```bash
uv sync --extra analysis

# 1. Model: Qwen3-8B, 4-bit GGUF (5.0 GB)
mkdir -p ~/models
curl -L -o ~/models/Qwen3-8B-Q4_K_M.gguf \
  https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf

# 2. Serve it (OpenAI-compatible API on :8080)
scripts/serve_local.sh

# 3. Check the benchmark, then run one task
uv run pytest -q
uv run python scripts/check_tasks.py
uv run harbor run -p tasks/py-bugfix-lite -i csv-report-totals \
  -a harness_lab.harbor_agent:HarnessLabAgent -m local/qwen3-8b \
  --ak config=configs/full.yaml -n 1

# 4. Run the experiment grid and build the report
scripts/run_matrix.sh
uv run --extra analysis python analysis/report.py jobs/exp-* --out results/local-qwen3-8b
```

To use the free [NVIDIA API catalog](https://build.nvidia.com) instead, copy
`.env.example` to `.env`, add `NVIDIA_API_KEY`, and pass `-m nvidia/<model id>`.

## Why Qwen3-8B

It is a standard transformer: every layer uses full attention. Its prefix-cache
behavior therefore matches the datacenter models this project is about. Newer small
models such as Qwen3.5 mix linear-attention layers into the stack, which changes how
prefix caching works.

## Measurement notes

- **TTFT and inter-token gaps** are measured on the client from the streamed response.
  llama.cpp also reports its own prompt-processing time and per-token decode time; the
  analysis prefers those server numbers where they exist.
- **Cached tokens** come from `usage.prompt_tokens_details.cached_tokens`, falling back
  to llama.cpp's `timings.cache_n`. "Prefill computed" means prompt tokens minus
  cached tokens.
- **Server settings:** the local server uses a single slot and no host-RAM prompt cache
  (`scripts/serve_local.sh`), so the only cache in play is that slot's KV cache.
- **Controls:**
  - Variants are interleaved trial by trial, one task at a time.
  - Every trace records the harness git commit, model, endpoint and full config.
- **Hardware dependence:**
  - Token counts and cache hit rates don't depend on the hardware.
  - Latencies are specific to an Apple M4 with 16 GB of RAM, which is memory-constrained
    with Docker running; read them as relative comparisons.

## Repository layout

```
src/harness_lab/   loop.py (agent loop)   llm.py (streaming client + timing)
                   context.py (strategies)   tools.py   tracing.py   harbor_agent.py
configs/           one YAML per variant
tasks/             py-bugfix-lite (generated by scripts/make_py_bugfix_lite.py)
scripts/           serve_local.sh   run_matrix.sh   check_tasks.py
analysis/          report.py -> summary table, CSVs, charts
tests/             unit tests (fake model and executor; no network)
```

## Results

*Experiments are running; this section will hold the summary table, charts and findings.*
