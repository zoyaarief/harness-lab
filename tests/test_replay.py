import json
import random

import httpx

from harness_lab.replay import build_prompts, clip_sessions, select_sessions, export_sessions, parse_metrics, replay_level, shared_prefix_length


def common_prefix(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


SESSION = {
    "session_id": "job/t1",
    "variant": "full",
    "first_call_cached_tokens": 50,
    "calls": [
        {"kind": "agent", "prompt_tokens": 120, "reuse_tokens": 0, "output_tokens": 5, "gap_s": 0.0},
        {"kind": "agent", "prompt_tokens": 200, "reuse_tokens": 118, "output_tokens": 4, "gap_s": 0.0},
        {"kind": "agent", "prompt_tokens": 150, "reuse_tokens": 60, "output_tokens": 3, "gap_s": 0.0},
    ],
}


def test_prompts_reproduce_the_recorded_prefix_structure():
    shared = list(range(50))
    prompts = build_prompts(SESSION, shared, random.Random(0), vocab=(1000, 150000))
    assert [len(p) for p in prompts] == [120, 200, 150]
    assert prompts[0][:50] == shared
    assert common_prefix(prompts[0], prompts[1]) == 118
    assert common_prefix(prompts[1], prompts[2]) == 60


def write_trace(path, calls, variant="full"):
    path.parent.mkdir(parents=True)
    lines = [{"type": "run_start", "model": "local/m", "config": {"variant": variant}}]
    lines += [{"type": "llm_call", **c} for c in calls]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def test_export_computes_reuse_and_gaps(tmp_path):
    calls = [
        {"kind": "agent", "prompt_tokens": 700, "cached_tokens": 600, "completion_tokens": 20, "started_at": 100.0, "e2e_ms": 2000},
        {"kind": "agent", "prompt_tokens": 900, "cached_tokens": 800, "completion_tokens": 30, "started_at": 103.5, "e2e_ms": 1000},
        {"kind": "agent", "prompt_tokens": 400, "cached_tokens": 5000, "completion_tokens": 0, "started_at": 104.5, "e2e_ms": 1000},
    ]
    write_trace(tmp_path / "exp-full-t1" / "task__a" / "agent" / "harness_trace.jsonl", calls)
    (session,) = export_sessions([tmp_path / "exp-full-t1"])
    assert session["session_id"] == "exp-full-t1/task__a"
    assert [c["reuse_tokens"] for c in session["calls"]] == [0, 700, 900]
    assert [c["gap_s"] for c in session["calls"]] == [0.0, 1.5, 0.0]
    assert session["calls"][2]["output_tokens"] == 1
    assert shared_prefix_length([session]) == 600


def test_parse_metrics_sums_labelled_samples():
    text = (
        "# HELP vllm:prefix_cache_hits_total hits\n"
        'vllm:prefix_cache_hits_total{engine="0"} 30.0\n'
        'vllm:prefix_cache_hits_total{engine="1"} 12.0\n'
        "vllm:kv_cache_usage_perc 0.25\n"
    )
    assert parse_metrics(text) == {"vllm:prefix_cache_hits_total": 42.0, "vllm:kv_cache_usage_perc": 0.25}


async def test_replay_level_against_fake_server():
    seen = []
    hits = {"n": 0}

    async def handler(request):
        if request.url.path == "/metrics":
            hits["n"] += 10
            body = f"vllm:prefix_cache_hits_total {hits['n'] // 2}\nvllm:prefix_cache_queries_total {hits['n']}\n"
            return httpx.Response(200, text=body)
        payload = json.loads(request.content)
        seen.append(payload)
        chunks = [{"choices": [{"text": "x"}]} for _ in range(payload["max_tokens"])]
        chunks.append({"choices": [], "usage": {"prompt_tokens": len(payload["prompt"]), "completion_tokens": payload["max_tokens"]}})
        text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=text)

    sessions = [SESSION, {**SESSION, "session_id": "job/t2"}]
    result = await replay_level(
        sessions, base_url="http://fake/v1", model="m", concurrency=2, transport=httpx.MockTransport(handler)
    )
    level = result["level"]
    assert level["requests"] == 6 and level["errors"] == 0
    assert all(p["ignore_eos"] and p["min_tokens"] == p["max_tokens"] for p in seen)
    assert sorted(len(p["prompt"]) for p in seen) == [120, 120, 150, 150, 200, 200]
    assert level["server_prefix_hit_rate"] == 0.5
    assert level["ttft_p50_ms"] is not None and level["output_tokens_per_s"] > 0


def test_clip_sessions_stops_at_first_call_that_does_not_fit():
    clipped = clip_sessions([SESSION], max_model_len=180)
    assert [c["prompt_tokens"] for c in clipped[0]["calls"]] == [120]
    assert clipped[0]["clipped"] is True
    assert clip_sessions([SESSION], max_model_len=100) == []
    assert clip_sessions([SESSION], None) == [SESSION]


def test_reused_sessions_get_distinct_token_ids():
    chosen = select_sessions([SESSION], "full", 3)
    assert [s["session_id"] for s in chosen] == ["job/t1", "job/t1#copy1", "job/t1#copy2"]
    shared = list(range(50))
    first = build_prompts(chosen[0], shared, random.Random(f"0-{chosen[0]['session_id']}"))
    second = build_prompts(chosen[1], shared, random.Random(f"0-{chosen[1]['session_id']}"))
    assert common_prefix(first[0], second[0]) == 50  # only the harness preamble is shared


def test_export_drops_interrupted_sessions_and_caps_gaps(tmp_path):
    slow = [
        {"kind": "agent", "prompt_tokens": 500, "cached_tokens": 0, "completion_tokens": 5, "started_at": 0.0, "e2e_ms": 1000},
        {"kind": "agent", "prompt_tokens": 700, "cached_tokens": 500, "completion_tokens": 5, "started_at": 4000.0, "e2e_ms": 1000},
    ]
    ok = [
        {"kind": "agent", "prompt_tokens": 500, "cached_tokens": 0, "completion_tokens": 5, "started_at": 0.0, "e2e_ms": 1000},
        {"kind": "agent", "prompt_tokens": 700, "cached_tokens": 500, "completion_tokens": 5, "started_at": 301.0, "e2e_ms": 1000},
    ]
    write_trace(tmp_path / "job" / "slept__a" / "agent" / "harness_trace.jsonl", slow)
    write_trace(tmp_path / "job" / "fine__b" / "agent" / "harness_trace.jsonl", ok)
    sessions = export_sessions([tmp_path / "job"], max_gap_s=120.0, drop_gap_above_s=600.0)
    assert [s["session_id"] for s in sessions] == ["job/fine__b"]
    assert [c["gap_s"] for c in sessions[0]["calls"]] == [0.0, 120.0]  # 300 s capped to 120 s
