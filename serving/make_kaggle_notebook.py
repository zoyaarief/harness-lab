"""Build a self-contained Kaggle notebook that replays agent sessions against vLLM on a free T4.

The notebook embeds harness_lab/replay.py and the sessions file, so it needs no access to
this repository. Import it on kaggle.com (Create -> Import Notebook), set Accelerator to
"GPU T4 x2", turn Internet on, and Run All. Download replay-results.zip from the Output tab.

    uv run python serving/make_kaggle_notebook.py traces/sessions.jsonl --out ~/Downloads/harness-lab-replay.ipynb

Kaggle's T4s (compute capability 7.5) need the kaggle-vllm build of vLLM: float16, eager
mode, and the Triton attention backend. The default model is Qwen3-1.7B so a single T4
keeps enough KV-cache room for several concurrent agent sessions. Replay uses token IDs,
so any Qwen3-family model reproduces the recorded prompt lengths and prefix overlap.
"""

import argparse
import base64
import gzip
import json
from pathlib import Path

REPLAY_SOURCE = Path(__file__).resolve().parents[1] / "src" / "harness_lab" / "replay.py"


def blob(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data, mtime=0)).decode()


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.strip("\n").splitlines(keepends=True),
    }


def build(sessions: bytes, model: str, max_model_len: int, variants: list[str], concurrency: list[int],
          sessions_per_worker: int, title: str) -> dict:
    cells = [
        md(f"""
# {title}

Replays recorded coding-agent sessions from
[harness-lab](https://github.com/zoyaarief/harness-lab) against **vLLM on a Kaggle T4**, first
with prefix caching **on**, then **off**, at several concurrency levels.

**Before running:** Settings → Accelerator → **GPU T4 x2**, and Settings → Internet → **On**
(needs a phone-verified account). Then **Run All**. When it finishes, download
`replay-results.zip` from the Output panel (right side, `/kaggle/working`).
"""),
        code("!nvidia-smi"),
        code('!pip install -q "kaggle-vllm[hub]==0.2.0"'),
        code("""
# Install the T4-validated vLLM build and load its environment variables into this kernel.
import os, shlex, shutil, subprocess

subprocess.run(["kaggle-vllm", "bootstrap", "--strict"], check=True)
env_script = subprocess.run(["kaggle-vllm", "env"], capture_output=True, text=True, check=True).stdout
for line in env_script.splitlines():
    line = line.strip()
    if line.startswith("export ") and "=" in line:
        key, _, value = line[len("export "):].partition("=")
        os.environ[key] = shlex.split(value)[0] if value.strip() else ""
print(env_script)
subprocess.run(["kaggle-vllm", "doctor", "--strict"])
print("vllm executable:", shutil.which("vllm"))
"""),
        code(f"""
# Embedded files: the replay tool (harness_lab/replay.py) and the recorded sessions.
import base64, gzip, pathlib

REPLAY_PY = "{blob(REPLAY_SOURCE.read_bytes())}"
SESSIONS = "{blob(sessions)}"

work = pathlib.Path("/kaggle/working")
(work / "replay.py").write_bytes(gzip.decompress(base64.b64decode(REPLAY_PY)))
(work / "sessions.jsonl").write_bytes(gzip.decompress(base64.b64decode(SESSIONS)))
print(sum(1 for _ in open(work / "sessions.jsonl")), "sessions")
"""),
        code(f"""
MODEL = "{model}"
MAX_MODEL_LEN = {max_model_len}
VARIANTS = {json.dumps(variants)}
CONCURRENCY = {json.dumps(concurrency)}
SESSIONS_PER_WORKER = {sessions_per_worker}
PORT = 8000
CONFIGS = {{"prefix-cache-on": ["--enable-prefix-caching"], "prefix-cache-off": ["--no-enable-prefix-caching"]}}
OPTIONAL_FLAGS = ["--enable-prompt-tokens-details"]  # dropped automatically if this build rejects it
"""),
        code("""
import sys, time, urllib.request

def start_server(config, optional_flags):
    log = open(work / f"vllm-{config}.log", "w")
    # `kaggle-vllm serve` only forwards a fixed set of flags, so call the vllm it staged
    # (on PATH via `kaggle-vllm env`) with the same T4 defaults plus our own flags.
    command = [
        "vllm", "serve", MODEL,
        "--served-model-name", MODEL,
        "--host", "127.0.0.1",
        "--port", str(PORT),
        "--tensor-parallel-size", "1",
        "--dtype", "float16",
        "--enforce-eager",
        "--disable-custom-all-reduce",
        "--max-model-len", str(MAX_MODEL_LEN),
        "--gpu-memory-utilization", "0.85",
        *CONFIGS[config], *optional_flags,
    ]
    print(" ".join(command))
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "0"}
    return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env)

def wait_healthy(process, timeout_s=1500):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(5)
    raise TimeoutError("vLLM did not become healthy")

def stop(process):
    process.terminate()
    try:
        process.wait(timeout=90)
    except subprocess.TimeoutExpired:
        process.kill()
    time.sleep(10)  # let the GPU memory free up

def serve(config):
    global OPTIONAL_FLAGS
    for flags in (OPTIONAL_FLAGS, []):
        process = start_server(config, flags)
        if wait_healthy(process):
            OPTIONAL_FLAGS = flags  # remember what this build accepts
            return process
        print(f"server exited (code {process.returncode}); last log lines:")
        print("".join(open(work / f"vllm-{config}.log").readlines()[-25:]))
        if not flags:
            break
    raise RuntimeError("vLLM failed to start; see the log above")
"""),
        code("""
import shutil

for config in CONFIGS:
    server = serve(config)
    try:
        subprocess.run(
            [sys.executable, "-u", str(work / "replay.py"), "run", str(work / "sessions.jsonl"),
             "--base-url", f"http://127.0.0.1:{PORT}/v1", "--model", MODEL,
             "--variants", *VARIANTS, "--concurrency", *map(str, CONCURRENCY),
             "--sessions-per-worker", str(SESSIONS_PER_WORKER),
             "--max-model-len", str(MAX_MODEL_LEN),
             "--label", config, "--out", str(work / "results" / config)],
            check=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    finally:
        stop(server)
        shutil.make_archive(str(work / "replay-results"), "zip", work / "results")
"""),
        code("""
import shutil
gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"],
                     capture_output=True, text=True).stdout.strip()
(work / "results" / "environment.txt").write_text(f"GPU: {gpu}\\nmodel: {MODEL}\\nmax_model_len: {MAX_MODEL_LEN}\\n")
for log in work.glob("vllm-*.log"):
    shutil.copy(log, work / "results" / log.name)
shutil.make_archive(str(work / "replay-results"), "zip", work / "results")
for summary in sorted((work / "results").glob("*/summary.md")):
    print(f"## {summary.parent.name}\\n{summary.read_text()}")
print("Download replay-results.zip from the Output panel.")
"""),
    ]
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True, "isGpuEnabled": True},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sessions", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--max-model-len", type=int, default=16384)
    parser.add_argument("--variants", nargs="+", default=["full", "rolling"])
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--sessions-per-worker", type=int, default=2)
    parser.add_argument("--title", default="harness-lab: agent session replay on vLLM (Kaggle T4)")
    args = parser.parse_args()

    notebook = build(
        args.sessions.read_bytes(), args.model, args.max_model_len, args.variants,
        args.concurrency, args.sessions_per_worker, args.title,
    )
    args.out.expanduser().parent.mkdir(parents=True, exist_ok=True)
    args.out.expanduser().write_text(json.dumps(notebook, indent=1))
    print(f"Wrote {args.out} ({args.out.expanduser().stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
