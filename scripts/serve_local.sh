#!/usr/bin/env bash
# Serve Qwen3-8B locally with llama.cpp (Metal) behind an OpenAI-compatible API.
#
# Settings that matter for the experiments:
#   -np 1          one slot, so every request reuses the previous request's KV cache
#                  (the same longest-common-prefix reuse that vLLM does per block)
#   -cram 0        disable llama.cpp's extra host-RAM prompt cache, so the only cache
#                  in play is the slot's KV cache (simpler to reason about, and saves RAM)
#   -ctk/-ctv q8_0 8-bit KV cache: 32K context in ~2.4 GB instead of ~4.7 GB
#   --metrics      Prometheus metrics at /metrics
set -euo pipefail

MODEL="${MODEL:-$HOME/models/Qwen3-8B-Q4_K_M.gguf}"
PORT="${PORT:-8080}"
CTX="${CTX:-32768}"

exec llama-server \
  -m "$MODEL" \
  --alias qwen3-8b \
  --host 127.0.0.1 --port "$PORT" \
  -c "$CTX" -np 1 \
  -ngl 99 -fa on \
  -ctk q8_0 -ctv q8_0 \
  -cram 0 \
  --jinja \
  --metrics \
  --no-webui
