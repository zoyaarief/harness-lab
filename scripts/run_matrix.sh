#!/usr/bin/env bash
# Run harness variants over a task set with Harbor.
#
# Variants are interleaved trial by trial (all variants for trial 1, then trial 2, ...)
# so slow drift on the machine (thermals, memory pressure) hits every variant equally.
# Finished jobs are skipped, so the script can be re-run after an interruption.
#
#   scripts/run_matrix.sh                                   # defaults below
#   VARIANTS="full bash-only" TRIALS=3 PREFIX=tools scripts/run_matrix.sh
#   MODEL=nvidia/qwen/qwen3-coder-480b-a35b-instruct PREFIX=nim CONCURRENCY=2 scripts/run_matrix.sh
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-local/qwen3-8b}"
TASKS="${TASKS:-tasks/py-bugfix-lite}"
VARIANTS="${VARIANTS:-full truncate rolling compaction}"
TRIALS="${TRIALS:-2}"
PREFIX="${PREFIX:-exp}"
# Keep 1 for the local server: it has one slot, so extra requests would just queue
# and inflate TTFT.
CONCURRENCY="${CONCURRENCY:-1}"

env_args=()
[[ -f .env ]] && env_args=(--env-file .env)

finished() {
  [[ -f "jobs/$1/result.json" ]] &&
    python3 -c "import json,sys; sys.exit(0 if json.load(open('jobs/$1/result.json')).get('finished_at') else 1)"
}

for trial in $(seq 1 "$TRIALS"); do
  for variant in $VARIANTS; do
    job="${PREFIX}-${variant}-t${trial}"
    if finished "$job"; then
      echo "skip $job (finished)"
      continue
    fi
    echo "=== $job  $(date '+%H:%M:%S')"
    uv run harbor run \
      -p "$TASKS" \
      -a harness_lab.harbor_agent:HarnessLabAgent \
      -m "$MODEL" \
      --ak "config=configs/${variant}.yaml" \
      -n "$CONCURRENCY" \
      --job-name "$job" \
      -y -q "${env_args[@]}" ${EXTRA_ARGS:-}
  done
done
echo "=== done $(date '+%H:%M:%S')"
