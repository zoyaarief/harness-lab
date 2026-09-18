"""Replay recorded agent sessions against a real serving stack.

Each harness trace records, per model call: the prompt length, how many prompt tokens the
server reused from the previous request (`cached_tokens`), the output length, and the wall
time between calls (mostly tool execution). `export` turns those traces into sessions.
`run` rebuilds every session as synthetic token-ID prompts with the same prefix structure
and sends many sessions at once to an OpenAI-compatible `/v1/completions` endpoint such
as vLLM, recording TTFT, inter-token latency, throughput, and the server's own
prefix-cache and KV-cache metrics.

    python -m harness_lab.replay export jobs/exp-* --out traces/sessions.jsonl
    python -m harness_lab.replay run traces/sessions.jsonl --base-url http://127.0.0.1:8000/v1 \
        --model Qwen/Qwen3-8B-FP8 --variants full rolling --concurrency 1 4 8 16 --out results/replay/local

Only httpx and the standard library are needed, so this module also runs inside the
Modal GPU container (serving/modal_replay.py).
"""

import argparse
import asyncio
import csv
import json
import random
import re
import statistics
import time
from pathlib import Path
from typing import Any

import httpx

# Regular (non-special) token IDs for the Qwen3 tokenizer; override with --vocab for other models.
DEFAULT_VOCAB = (1_000, 150_000)

# --------------------------------------------------------------------------- export


def export_sessions(
    job_dirs: list[Path], max_gap_s: float = 120.0, drop_gap_above_s: float = 600.0
) -> list[dict[str, Any]]:
    """Turn traces into sessions.

    `gap_s` is the wall time between calls, mostly tool execution. Two guards keep machine
    artifacts out of the replay: a trial whose trace has a gap longer than
    `drop_gap_above_s` was interrupted (the laptop slept) and is dropped entirely, and every
    remaining gap is capped at `max_gap_s` so one slow tool call cannot stall a replay.
    """
    sessions = []
    for job in job_dirs:
        for trace in sorted(job.glob("*/agent/harness_trace.jsonl")):
            records = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
            calls = [r for r in records if r["type"] == "llm_call" and r.get("prompt_tokens")]
            if not calls:
                continue
            start = records[0]
            session_calls = []
            prev = None
            interrupted = False
            for call in calls:
                reuse = 0
                gap = 0.0
                if prev is not None:
                    reuse = min(call.get("cached_tokens") or 0, prev["prompt_tokens"])
                    gap = max(0.0, call["started_at"] - (prev["started_at"] + prev["e2e_ms"] / 1000))
                    if gap > drop_gap_above_s:
                        interrupted = True
                        break
                session_calls.append(
                    {
                        "kind": call["kind"],
                        "prompt_tokens": call["prompt_tokens"],
                        "reuse_tokens": reuse,
                        "output_tokens": max(1, call.get("completion_tokens") or 1),
                        "gap_s": round(min(gap, max_gap_s), 3),
                    }
                )
                prev = call
            if interrupted:
                continue
            sessions.append(
                {
                    "session_id": f"{job.name}/{trace.parent.parent.name}",
                    "variant": start["config"]["variant"],
                    "model": start.get("model"),
                    "first_call_cached_tokens": calls[0].get("cached_tokens") or 0,
                    "calls": session_calls,
                }
            )
    return sessions


def shared_prefix_length(sessions: list[dict[str, Any]]) -> int:
    """Tokens every session shares up front (system prompt + tool definitions).

    Consecutive trials ran on the same server slot, so a session's first call could only
    reuse what it shares with the previous session: the harness preamble.
    """
    firsts = [s["first_call_cached_tokens"] for s in sessions if s["first_call_cached_tokens"] > 0]
    if not firsts:
        return 0
    smallest_first_prompt = min(s["calls"][0]["prompt_tokens"] for s in sessions)
    return min(int(statistics.median(firsts)), smallest_first_prompt)


# --------------------------------------------------------------------------- prompts


def build_prompts(
    session: dict[str, Any], shared_prefix: list[int], rng: random.Random, vocab: tuple[int, int] = DEFAULT_VOCAB
) -> list[list[int]]:
    """Token-ID prompts whose prefix overlap with the previous call matches the trace."""
    prompts: list[list[int]] = []
    prev: list[int] | None = None
    for call in session["calls"]:
        n = call["prompt_tokens"]
        if prev is None:
            base = shared_prefix[: min(len(shared_prefix), n)]
        else:
            base = prev[: min(call["reuse_tokens"], n)]
        prompt = base + [rng.randrange(*vocab) for _ in range(n - len(base))]
        prompts.append(prompt)
        prev = prompt
    return prompts


# --------------------------------------------------------------------------- server metrics

_SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEinfNa]+)")


def parse_metrics(text: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        match = _SAMPLE.match(line)
        if match:
            try:
                totals[match.group(1)] = totals.get(match.group(1), 0.0) + float(match.group(3))
            except ValueError:
                continue
    return totals


def pick(metrics: dict[str, float], *names: str) -> float | None:
    for name in names:
        if name in metrics:
            return metrics[name]
    return None


PREFIX_HITS = ("vllm:prefix_cache_hits_total", "vllm:gpu_prefix_cache_hits_total", "vllm:prefix_cache_hits")
PREFIX_QUERIES = ("vllm:prefix_cache_queries_total", "vllm:gpu_prefix_cache_queries_total", "vllm:prefix_cache_queries")
PREEMPTIONS = ("vllm:num_preemptions_total", "vllm:num_preemptions")
KV_USAGE = ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc")


async def fetch_metrics(client: httpx.AsyncClient, metrics_url: str) -> dict[str, float]:
    try:
        response = await client.get(metrics_url, timeout=10)
        return parse_metrics(response.text) if response.status_code == 200 else {}
    except httpx.HTTPError:
        return {}


# --------------------------------------------------------------------------- requests


async def send(
    client: httpx.AsyncClient, url: str, model: str, prompt: list[int], output_tokens: int
) -> dict[str, Any]:
    body = {
        "model": model,
        "prompt": prompt,
        "max_tokens": output_tokens,
        "min_tokens": output_tokens,
        "ignore_eos": True,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    t0 = time.perf_counter()
    arrivals: list[float] = []
    usage: dict[str, Any] = {}
    error = None
    try:
        async with client.stream("POST", url, json=body) as resp:
            if resp.status_code >= 400:
                error = f"HTTP {resp.status_code}: {(await resp.aread())[:200]!r}"
            else:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    if chunk.get("choices"):
                        arrivals.append(time.perf_counter())
                    if chunk.get("usage"):
                        usage = chunk["usage"]
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"
    end = time.perf_counter()
    gaps = [(b - a) * 1000 for a, b in zip(arrivals, arrivals[1:])]
    return {
        "ttft_ms": (arrivals[0] - t0) * 1000 if arrivals else None,
        "e2e_ms": (end - t0) * 1000,
        "itl_ms_mean": statistics.fmean(gaps) if gaps else None,
        "itl_gaps_ms": gaps,
        "server_prompt_tokens": usage.get("prompt_tokens"),
        "server_output_tokens": usage.get("completion_tokens"),
        "server_cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "error": error,
    }


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))]


async def replay_level(
    sessions: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    concurrency: int,
    gap_scale: float = 1.0,
    seed: int = 0,
    vocab: tuple[int, int] = DEFAULT_VOCAB,
    label: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Run `sessions` with `concurrency` closed-loop workers (each worker = one agent)."""
    url = base_url.rstrip("/") + "/completions"
    metrics_url = base_url.rstrip("/").removesuffix("/v1") + "/metrics"
    prefix_rng = random.Random(f"{seed}-shared")
    shared = [prefix_rng.randrange(*vocab) for _ in range(shared_prefix_length(sessions))]
    queue: asyncio.Queue = asyncio.Queue()
    for session in sessions:
        queue.put_nowait(session)
    requests: list[dict[str, Any]] = []
    kv_samples: list[float] = []
    done = asyncio.Event()

    limits = httpx.Limits(max_connections=concurrency + 4, max_keepalive_connections=concurrency + 4)
    async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=10), limits=limits, transport=transport) as client:
        before = await fetch_metrics(client, metrics_url)

        async def sample_kv() -> None:
            while not done.is_set():
                usage = pick(await fetch_metrics(client, metrics_url), *KV_USAGE)
                if usage is not None:
                    kv_samples.append(usage)
                try:
                    await asyncio.wait_for(done.wait(), timeout=1.0)
                except TimeoutError:
                    pass

        async def worker(worker_id: int) -> None:
            while True:
                try:
                    session = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                rng = random.Random(f"{seed}-{session['session_id']}")
                prompts = build_prompts(session, shared, rng, vocab)
                for index, (call, prompt) in enumerate(zip(session["calls"], prompts)):
                    if index and gap_scale > 0:
                        await asyncio.sleep(call["gap_s"] * gap_scale)
                    started = time.perf_counter()
                    result = await send(client, url, model, prompt, call["output_tokens"])
                    requests.append(
                        {
                            "label": label,
                            "concurrency": concurrency,
                            "worker": worker_id,
                            "session_id": session["session_id"],
                            "variant": session["variant"],
                            "call_index": index,
                            "kind": call["kind"],
                            "prompt_tokens": call["prompt_tokens"],
                            "reuse_tokens": call["reuse_tokens"] if index else len(shared),
                            "output_tokens": call["output_tokens"],
                            "t_start_s": started - t0,
                            **result,
                        }
                    )

        sampler = asyncio.create_task(sample_kv())
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(concurrency)))
        wall = time.perf_counter() - t0
        done.set()
        await sampler
        after = await fetch_metrics(client, metrics_url)

    def delta(names: tuple[str, ...]) -> float | None:
        a, b = pick(before, *names), pick(after, *names)
        return None if a is None or b is None else b - a

    ok = [r for r in requests if r["error"] is None]
    hits, queries = delta(PREFIX_HITS), delta(PREFIX_QUERIES)
    gaps = [g for r in ok for g in r["itl_gaps_ms"]]
    ttfts = [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]
    level = {
        "label": label,
        "concurrency": concurrency,
        "sessions": len(sessions),
        "requests": len(requests),
        "errors": len(requests) - len(ok),
        "wall_s": wall,
        "output_tokens_per_s": sum(r["output_tokens"] for r in ok) / wall if wall else None,
        "prompt_tokens_per_s": sum(r["prompt_tokens"] for r in ok) / wall if wall else None,
        "requests_per_s": len(ok) / wall if wall else None,
        "ttft_p50_ms": _pct(ttfts, 50),
        "ttft_p90_ms": _pct(ttfts, 90),
        "ttft_p99_ms": _pct(ttfts, 99),
        "itl_p50_ms": _pct(gaps, 50),
        "itl_p99_ms": _pct(gaps, 99),
        "e2e_p50_ms": _pct([r["e2e_ms"] for r in ok], 50),
        "trace_reuse_rate": sum(r["reuse_tokens"] for r in ok) / max(1, sum(r["prompt_tokens"] for r in ok)),
        "server_prefix_hit_rate": (hits / queries) if hits is not None and queries else None,
        "server_preemptions": delta(PREEMPTIONS),
        "kv_cache_usage_peak": max(kv_samples) if kv_samples else None,
    }
    for r in requests:
        r.pop("itl_gaps_ms")
    return {"level": level, "requests": requests}


def clip_sessions(sessions: list[dict[str, Any]], max_model_len: int | None) -> list[dict[str, Any]]:
    """Cut each session at its first call that would not fit the server's context window."""
    if not max_model_len:
        return sessions
    clipped = []
    for session in sessions:
        calls = []
        for call in session["calls"]:
            if call["prompt_tokens"] + call["output_tokens"] > max_model_len:
                break
            calls.append(call)
        if calls:
            clipped.append({**session, "calls": calls, "clipped": len(calls) < len(session["calls"])})
    return clipped


def select_sessions(sessions: list[dict[str, Any]], variant: str, count: int) -> list[dict[str, Any]]:
    pool = sorted((s for s in sessions if s["variant"] == variant), key=lambda s: s["session_id"])
    if not pool:
        raise ValueError(f"No sessions for variant {variant!r}")
    chosen = []
    for i in range(count):
        session, copy = pool[i % len(pool)], i // len(pool)
        # A reused session gets its own replay id, and so its own token IDs; otherwise the
        # second copy would hit the first copy's cache entries and inflate the hit rate.
        chosen.append(session if copy == 0 else {**session, "session_id": f"{session['session_id']}#copy{copy}"})
    return chosen


async def replay_matrix(
    sessions: list[dict[str, Any]],
    *,
    base_url: str,
    model: str,
    variants: list[str],
    concurrency: list[int],
    sessions_per_worker: int = 3,
    gap_scale: float = 1.0,
    label: str = "",
    max_model_len: int | None = None,
    out: Path | None = None,
    log=print,
) -> dict[str, Any]:
    sessions = clip_sessions(sessions, max_model_len)
    levels, requests = [], []
    for variant in variants:
        for c in concurrency:
            chosen = select_sessions(sessions, variant, c * sessions_per_worker)
            tag = f"{label}/{variant}" if label else variant
            log(f"[replay] {tag} concurrency={c} sessions={len(chosen)}")
            result = await replay_level(
                chosen, base_url=base_url, model=model, concurrency=c, gap_scale=gap_scale, label=tag
            )
            level = result["level"]
            log(
                f"[replay]   wall={level['wall_s']:.0f}s out_tok/s={level['output_tokens_per_s']:.1f} "
                f"ttft_p50={level['ttft_p50_ms']}ms hit_rate={level['server_prefix_hit_rate']} errors={level['errors']}"
            )
            levels.append(level)
            requests.extend(result["requests"])
            if out is not None:  # save after every level: a killed run still leaves results
                write_results({"levels": levels, "requests": requests}, out)
                (out / "summary.md").write_text(levels_markdown(levels))
    return {"levels": levels, "requests": requests}


def write_results(result: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "levels.json").write_text(json.dumps(result["levels"], indent=2))
    if result["requests"]:
        with (out / "requests.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(result["requests"][0]))
            writer.writeheader()
            writer.writerows(result["requests"])


def _fmt(value: Any, spec: str) -> str:
    return "–" if value is None else format(value, spec)


def levels_markdown(levels: list[dict[str, Any]]) -> str:
    lines = [
        "| Workload | Concurrency | Requests | Output tok/s | TTFT p50 / p90 (ms) | ITL p50 / p99 (ms) "
        "| Prefix reuse in trace | Server prefix-cache hit rate | Peak KV-cache use | Preemptions |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lv in levels:
        lines.append(
            f"| {lv['label']} | {lv['concurrency']} | {lv['requests']} | {_fmt(lv['output_tokens_per_s'], ',.1f')} "
            f"| {_fmt(lv['ttft_p50_ms'], ',.0f')} / {_fmt(lv['ttft_p90_ms'], ',.0f')} "
            f"| {_fmt(lv['itl_p50_ms'], '.1f')} / {_fmt(lv['itl_p99_ms'], '.1f')} "
            f"| {_fmt(lv['trace_reuse_rate'], '.0%')} | {_fmt(lv['server_prefix_hit_rate'], '.0%')} "
            f"| {_fmt(lv['kv_cache_usage_peak'], '.0%')} | {_fmt(lv['server_preemptions'], '.0f')} |"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    exp = sub.add_parser("export", help="Turn Harbor job directories into replayable sessions")
    exp.add_argument("jobs", nargs="+", type=Path)
    exp.add_argument("--out", type=Path, required=True)
    exp.add_argument("--max-gap-s", type=float, default=120.0, help="Cap the pause between calls")
    exp.add_argument("--drop-gap-above-s", type=float, default=600.0,
                     help="Drop a session whose trace has a longer gap (the machine slept)")

    run = sub.add_parser("run", help="Replay sessions against an OpenAI-compatible completions server")
    run.add_argument("sessions", type=Path)
    run.add_argument("--base-url", required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--variants", nargs="+", default=["full"])
    run.add_argument("--concurrency", nargs="+", type=int, default=[1, 4, 8, 16])
    run.add_argument("--sessions-per-worker", type=int, default=3)
    run.add_argument("--gap-scale", type=float, default=1.0, help="Multiply recorded tool gaps (0 = no gaps)")
    run.add_argument("--label", default="")
    run.add_argument("--max-model-len", type=int, default=None, help="Clip sessions to fit this context window")
    run.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "export":
        sessions = export_sessions(args.jobs, args.max_gap_s, args.drop_gap_above_s)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(s) + "\n" for s in sessions))
        by_variant: dict[str, int] = {}
        for s in sessions:
            by_variant[s["variant"]] = by_variant.get(s["variant"], 0) + 1
        print(f"Wrote {len(sessions)} sessions to {args.out} {by_variant}; shared prefix {shared_prefix_length(sessions)} tokens")
        return

    sessions = [json.loads(line) for line in args.sessions.read_text().splitlines() if line.strip()]
    result = asyncio.run(
        replay_matrix(
            sessions,
            base_url=args.base_url,
            model=args.model,
            variants=args.variants,
            concurrency=args.concurrency,
            sessions_per_worker=args.sessions_per_worker,
            gap_scale=args.gap_scale,
            label=args.label,
            max_model_len=args.max_model_len,
            out=args.out,
        )
    )
    write_results(result, args.out)
    (args.out / "summary.md").write_text(levels_markdown(result["levels"]))
    print(levels_markdown(result["levels"]))


if __name__ == "__main__":
    main()
