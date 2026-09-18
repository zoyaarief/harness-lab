"""Replay recorded agent sessions against vLLM on a Modal GPU.

One run (an L4 for well under an hour) fits in Modal's free monthly credit.

    uv run --with modal modal setup                     # one-time: log in to Modal
    uv run python -m harness_lab.replay export jobs/exp-* --out traces/sessions.jsonl
    uv run --with modal modal run serving/modal_replay.py --sessions traces/sessions.jsonl

The container starts vLLM twice (prefix caching on, then off) and replays the chosen
harness variants at several concurrency levels against each. vLLM and the replay client
run in the same container, so no traffic crosses the network. Results are written to
results/replay-<gpu>/.
"""

import json
import subprocess
import time
from pathlib import Path

import modal

VLLM_VERSION = "0.29.0"
MODEL = "Qwen/Qwen3-8B-FP8"
GPU = "L4"
PORT = 8000

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(f"vllm=={VLLM_VERSION}", "httpx")
    .add_local_python_source("harness_lab")
)
hf_cache = modal.Volume.from_name("harness-lab-hf-cache", create_if_missing=True)
app = modal.App("harness-lab-replay", image=image)

SERVER_CONFIGS = {
    "prefix-cache-on": ["--enable-prefix-caching"],
    "prefix-cache-off": ["--no-enable-prefix-caching"],
}


def wait_until_healthy(process: subprocess.Popen, timeout_s: int = 1200) -> None:
    import httpx

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"vLLM exited early with code {process.returncode}")
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(5)
    raise TimeoutError("vLLM did not become healthy in time")


@app.function(gpu=GPU, timeout=3 * 60 * 60, volumes={"/root/.cache/huggingface": hf_cache})
def replay_on_gpu(
    sessions_jsonl: str,
    variants: list[str],
    concurrency: list[int],
    sessions_per_worker: int,
    server_configs: list[str],
) -> dict:
    import asyncio

    from harness_lab import replay

    sessions = [json.loads(line) for line in sessions_jsonl.splitlines() if line.strip()]
    gpu_name = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True
    ).stdout.strip()
    results = {"gpu": gpu_name, "model": MODEL, "vllm": VLLM_VERSION, "configs": {}}

    for config in server_configs:
        command = [
            "vllm", "serve", MODEL,
            "--port", str(PORT),
            "--max-model-len", "32768",
            "--gpu-memory-utilization", "0.90",
            "--enable-prompt-tokens-details",
            *SERVER_CONFIGS[config],
        ]  # fmt: skip
        print(f"[modal] starting: {' '.join(command)}", flush=True)
        server = subprocess.Popen(command)
        try:
            wait_until_healthy(server)
            hf_cache.commit()
            results["configs"][config] = asyncio.run(
                replay.replay_matrix(
                    sessions,
                    base_url=f"http://127.0.0.1:{PORT}/v1",
                    model=MODEL,
                    variants=variants,
                    concurrency=concurrency,
                    sessions_per_worker=sessions_per_worker,
                    label=config,
                    log=lambda msg: print(msg, flush=True),
                )
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                server.kill()
    return results


@app.local_entrypoint()
def main(
    sessions: str = "traces/sessions.jsonl",
    variants: str = "full,rolling",
    concurrency: str = "1,4,8,16",
    sessions_per_worker: int = 3,
    configs: str = "prefix-cache-on,prefix-cache-off",
    out: str = "",
):
    from harness_lab import replay

    result = replay_on_gpu.remote(
        Path(sessions).read_text(),
        variants.split(","),
        [int(c) for c in concurrency.split(",")],
        sessions_per_worker,
        configs.split(","),
    )
    out_dir = Path(out or f"results/replay-{GPU.lower()}")
    levels = []
    for config, data in result["configs"].items():
        replay.write_results(data, out_dir / config)
        levels.extend(data["levels"])
    header = f"GPU: {result['gpu']} · model: {result['model']} · vLLM {result['vllm']}\n\n"
    (out_dir / "summary.md").write_text(header + replay.levels_markdown(levels))
    (out_dir / "levels.json").write_text(json.dumps({**result, "configs": None, "levels": levels}, indent=2))
    print(header + replay.levels_markdown(levels))
