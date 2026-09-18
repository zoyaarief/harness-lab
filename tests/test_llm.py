import json

import httpx
import pytest

from harness_lab.llm import ContextOverflowError, LLMClient


def sse(*chunks) -> bytes:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"


def client_for(handler) -> LLMClient:
    return LLMClient("http://fake/v1", "m", transport=httpx.MockTransport(handler), max_retries=1)


async def test_parses_streamed_tool_call_usage_and_timings():
    body = sse(
        {"choices": [{"delta": {"content": "Let me look."}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "bash", "arguments": '{"comm'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'and": "ls"}'}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 12, "prompt_tokens_details": {"cached_tokens": 900}},
            "timings": {"cache_n": 900, "prompt_n": 100, "prompt_ms": 250.0, "predicted_per_token_ms": 40.0},
        },
    )
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    response = await client_for(handler).chat([{"role": "user", "content": "hi"}], tools=[{"x": 1}])

    assert seen["stream"] is True and seen["stream_options"] == {"include_usage": True}
    assert response.content == "Let me look."
    assert [(tc.id, tc.name, tc.arguments) for tc in response.tool_calls] == [("c1", "bash", '{"command": "ls"}')]
    s = response.stats
    assert (s.prompt_tokens, s.cached_tokens, s.completion_tokens) == (1000, 900, 12)
    assert s.prefill_tokens_computed == 100
    assert s.server_prompt_ms == 250.0 and s.finish_reason == "tool_calls"
    assert s.ttft_ms is not None and s.n_output_chunks == 3
    assert response.to_message()["tool_calls"][0]["function"]["name"] == "bash"


async def test_prefill_falls_back_to_usage_when_no_server_timings():
    body = sse(
        {"choices": [{"delta": {"content": "ok"}}]},
        {"choices": [], "usage": {"prompt_tokens": 500, "completion_tokens": 1}},
    )
    response = await client_for(lambda r: httpx.Response(200, content=body)).chat([])
    assert response.stats.cached_tokens is None
    assert response.stats.prefill_tokens_computed == 500


async def test_context_overflow_is_classified():
    def handler(request):
        return httpx.Response(400, json={"error": {"message": "the request exceeds the available context size"}})

    with pytest.raises(ContextOverflowError):
        await client_for(handler).chat([])


async def test_retries_on_rate_limit(monkeypatch):
    calls = []

    async def no_sleep(_):
        pass

    monkeypatch.setattr("harness_lab.llm.asyncio.sleep", no_sleep)

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}))

    response = await client_for(handler).chat([])
    assert response.content == "ok" and response.stats.retries == 1


async def test_retries_on_overload_reported_inside_the_stream(monkeypatch):
    calls = []

    async def no_sleep(_):
        pass

    monkeypatch.setattr("harness_lab.llm.asyncio.sleep", no_sleep)

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            error = {"error": {"message": "Service temporarily overloaded", "code": 503}}
            return httpx.Response(200, content=sse(error))
        return httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}))

    response = await client_for(handler).chat([])
    assert response.content == "ok" and response.stats.retries == 1


async def test_other_stream_errors_are_not_retried():
    def handler(request):
        return httpx.Response(200, content=sse({"error": {"message": "bad tool schema", "code": 400}}))

    with pytest.raises(RuntimeError, match="bad tool schema"):
        await client_for(handler).chat([])
