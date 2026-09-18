"""Streaming client for OpenAI-compatible chat endpoints, with per-call timing.

Client-side timing:
  ttft_ms  time from sending the request to the first chunk that carries output
           (content, reasoning, or a tool-call delta)
  itl_ms   gaps between later output chunks. Some servers pack several tokens into
           one chunk, so this is an approximation of inter-token latency.

Server-side timing (llama.cpp returns a `timings` object) is recorded next to it
when available and is the ground truth for prefill and per-token decode time.
"""

import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


class ContextOverflowError(Exception):
    """The prompt no longer fits in the model's context window."""


class RetryableStreamError(Exception):
    """The server reported a transient failure (overload, rate limit) inside the stream."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    def to_message(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class CallStats:
    started_at: float = 0.0
    ttft_ms: float | None = None
    e2e_ms: float = 0.0
    decode_ms: float | None = None
    itl_ms_mean: float | None = None
    itl_ms_p50: float | None = None
    itl_ms_p95: float | None = None
    n_output_chunks: int = 0
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    completion_tokens: int | None = None
    server_prompt_ms: float | None = None
    server_prompt_tokens_computed: int | None = None
    server_decode_ms_per_token: float | None = None
    finish_reason: str | None = None
    retries: int = 0

    @property
    def prefill_tokens_computed(self) -> int | None:
        """Prompt tokens the server actually had to process (not served from cache)."""
        if self.server_prompt_tokens_computed is not None:
            return self.server_prompt_tokens_computed
        if self.prompt_tokens is None:
            return None
        return self.prompt_tokens - (self.cached_tokens or 0)


@dataclass
class LLMResponse:
    content: str
    reasoning: str
    tool_calls: list[ToolCall]
    stats: CallStats = field(default_factory=CallStats)

    def to_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [tc.to_message() for tc in self.tool_calls]
        return message


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


class LLMClient:
    RETRYABLE_STATUS = {429, 500, 502, 503, 504}
    RETRYABLE_MARKERS = ("overloaded", "unavailable", "rate limit", "rate_limit", "try again")

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_sec: float = 600.0,
        max_retries: int = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.timeout = httpx.Timeout(timeout_sec, connect=10.0)
        self.max_retries = max_retries
        self.transport = transport  # tests inject a mock transport

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.8,
        extra_body: dict[str, Any] | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        if tools:
            body["tools"] = tools
        body.update(extra_body or {})

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._stream(body)
                response.stats.retries = attempt
                return response
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in self.RETRYABLE_STATUS or attempt == self.max_retries:
                    raise
            except (httpx.TransportError, httpx.RemoteProtocolError, RetryableStreamError):
                if attempt == self.max_retries:
                    raise
            await asyncio.sleep(min(60, 2 ** (attempt + 1)))
        raise AssertionError("unreachable")

    async def _stream(self, body: dict[str, Any]) -> LLMResponse:
        stats = CallStats(started_at=time.time())
        content: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        output_times: list[float] = []

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            async with client.stream("POST", self.url, json=body, headers=self.headers) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode(errors="replace")
                    if resp.status_code == 400 and _looks_like_overflow(text):
                        raise ContextOverflowError(text[:500])
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code}: {text[:500]}", request=resp.request, response=resp
                    )
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    if "error" in chunk:
                        message = json.dumps(chunk["error"])
                        if _looks_like_overflow(message):
                            raise ContextOverflowError(message[:500])
                        error = chunk["error"] if isinstance(chunk["error"], dict) else {}
                        if error.get("code") in self.RETRYABLE_STATUS or any(
                            m in message.lower() for m in self.RETRYABLE_MARKERS
                        ):
                            raise RetryableStreamError(message[:500])
                        raise RuntimeError(f"Streaming error from server: {message[:500]}")

                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        got_output = False
                        if delta.get("content"):
                            content.append(delta["content"])
                            got_output = True
                        if delta.get("reasoning_content"):
                            reasoning.append(delta["reasoning_content"])
                            got_output = True
                        for tc in delta.get("tool_calls") or []:
                            slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                            got_output = True
                        if got_output:
                            output_times.append(time.perf_counter())
                        if choice.get("finish_reason"):
                            stats.finish_reason = choice["finish_reason"]

                    if chunk.get("usage"):
                        usage = chunk["usage"]
                        stats.prompt_tokens = usage.get("prompt_tokens")
                        stats.completion_tokens = usage.get("completion_tokens")
                        details = usage.get("prompt_tokens_details") or {}
                        if details.get("cached_tokens") is not None:
                            stats.cached_tokens = details["cached_tokens"]
                    if chunk.get("timings"):
                        timings = chunk["timings"]
                        stats.server_prompt_ms = timings.get("prompt_ms")
                        stats.server_prompt_tokens_computed = timings.get("prompt_n")
                        stats.server_decode_ms_per_token = timings.get("predicted_per_token_ms")
                        if stats.cached_tokens is None and timings.get("cache_n") is not None:
                            stats.cached_tokens = timings["cache_n"]

        t_end = time.perf_counter()
        stats.e2e_ms = (t_end - t0) * 1000
        stats.n_output_chunks = len(output_times)
        if output_times:
            stats.ttft_ms = (output_times[0] - t0) * 1000
            stats.decode_ms = (output_times[-1] - output_times[0]) * 1000
            gaps = [(b - a) * 1000 for a, b in zip(output_times, output_times[1:])]
            if gaps:
                stats.itl_ms_mean = statistics.fmean(gaps)
                stats.itl_ms_p50 = _percentile(gaps, 50)
                stats.itl_ms_p95 = _percentile(gaps, 95)

        tool_calls = [
            ToolCall(id=slot["id"] or f"call_{i}", name=slot["name"], arguments=slot["arguments"])
            for i, slot in sorted(calls.items())
        ]
        return LLMResponse("".join(content), "".join(reasoning), tool_calls, stats)


def _looks_like_overflow(text: str) -> bool:
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in ("context length", "context size", "exceed_context", "maximum context", "too many tokens")
    )
