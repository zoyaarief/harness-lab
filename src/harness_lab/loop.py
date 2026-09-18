"""The agent loop: prompt -> model -> tool calls -> observations -> repeat."""

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from harness_lab.config import HarnessConfig
from harness_lab.context import COMPACTION_PROMPT, make_strategy
from harness_lab.llm import CallStats, ContextOverflowError, LLMClient, RetryableStreamError
from harness_lab.tools import Executor, ToolRunner, tool_specs
from harness_lab.tracing import Tracer

SYSTEM_PROMPT = """\
You are an autonomous software engineer working inside a Linux container.
Complete the user's task by calling tools. The working directory is {workdir}.

How to work:
- Explore the relevant files before changing anything.
- Make small, targeted changes.
- Verify your change (run the tests or a quick check) before finishing.
- Every reply must call at least one tool. Never reply with text only.
- When the task is complete and verified, call `submit`."""

NUDGE = "You did not call a tool. Call a tool to continue, or call `submit` if the task is complete."

REPEAT_WARNING = (
    "\n\n[harness] You have now made this exact `{name}` call {count} times. Repeating it will not "
    "give a different result. Change your approach: look at other files, list directories, "
    "or re-read the task."
)


def call_signature(name: str, arguments: str) -> tuple[str, str]:
    try:
        return name, json.dumps(json.loads(arguments), sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        return name, arguments.strip()


@dataclass
class RunTotals:
    llm_calls: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    prefill_tokens_computed: int = 0
    llm_time_ms: float = 0.0
    tool_time_ms: float = 0.0
    tool_calls: int = 0
    tool_errors: int = 0
    format_errors: int = 0
    compactions: int = 0
    repeat_warnings: int = 0

    def add_call(self, stats: CallStats) -> None:
        self.llm_calls += 1
        self.prompt_tokens += stats.prompt_tokens or 0
        self.cached_tokens += stats.cached_tokens or 0
        self.completion_tokens += stats.completion_tokens or 0
        self.prefill_tokens_computed += stats.prefill_tokens_computed or 0
        self.llm_time_ms += stats.e2e_ms


@dataclass
class RunResult:
    stop_reason: str
    steps: int
    totals: RunTotals = field(default_factory=RunTotals)
    error: str | None = None


class TokenEstimator:
    """Estimate prompt tokens from characters, calibrated by the server's real counts."""

    def __init__(self, tools: list[dict[str, Any]]):
        self.tool_chars = len(json.dumps(tools))
        self.tokens_per_char = 0.3

    def chars(self, messages: list[dict[str, Any]]) -> int:
        return self.tool_chars + sum(len(json.dumps(m)) for m in messages)

    def estimate(self, messages: list[dict[str, Any]]) -> int:
        return int(self.chars(messages) * self.tokens_per_char)

    def calibrate(self, messages: list[dict[str, Any]], prompt_tokens: int | None) -> None:
        if prompt_tokens:
            self.tokens_per_char = prompt_tokens / max(1, self.chars(messages))


async def run_agent(
    instruction: str,
    executor: Executor,
    llm: LLMClient,
    cfg: HarnessConfig,
    tracer: Tracer,
) -> RunResult:
    strategy = make_strategy(cfg)
    tools = tool_specs(cfg.tool_set)
    runner = ToolRunner(executor, cfg.tool_set, cfg.command_timeout_sec)
    estimator = TokenEstimator(tools)
    totals = RunTotals()
    call_counts: Counter[tuple[str, str]] = Counter()

    # A config can set a key to null to drop it for providers that reject it.
    extra_body = {"chat_template_kwargs": {"enable_thinking": cfg.reasoning}, **cfg.extra_body}
    extra_body = {k: v for k, v in extra_body.items() if v is not None}

    workdir = (await executor.run("pwd", 10)).output.strip() or "the current directory"
    system = {"role": "system", "content": SYSTEM_PROMPT.format(workdir=workdir)}
    task = {"role": "user", "content": instruction}
    messages: list[dict[str, Any]] = [system, task]

    async def call_llm(request: list[dict[str, Any]], step: int, kind: str):
        response = await llm.chat(
            request,
            tools,
            max_tokens=cfg.max_output_tokens,
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            extra_body=extra_body,
        )
        estimator.calibrate(request, response.stats.prompt_tokens)
        totals.add_call(response.stats)
        tracer.write(
            {
                "type": "llm_call",
                "kind": kind,
                "step": step,
                "n_messages": len(request),
                "request_chars": estimator.chars(request),
                "n_tool_calls": len(response.tool_calls),
                "tool_names": [tc.name for tc in response.tool_calls],
                "output_chars": len(response.content) + len(response.reasoning),
                **asdict(response.stats),
                "prefill_tokens_computed": response.stats.prefill_tokens_computed,
            }
        )
        return response

    async def compact(step: int) -> None:
        request = strategy.render(messages) + [{"role": "user", "content": COMPACTION_PROMPT}]
        response = await call_llm(request, step, kind="compaction")
        summary = response.content.strip() or "(The model returned an empty summary.)"
        messages[:] = [
            system,
            {
                "role": "user",
                "content": f"{instruction}\n\n## Summary of your progress so far\n{summary}\n\n"
                "Continue the task from here.",
            },
        ]
        totals.compactions += 1
        tracer.write({"type": "compaction", "step": step, "summary_chars": len(summary)})

    def finish(reason: str, steps: int, error: str | None = None) -> RunResult:
        result = RunResult(reason, steps, totals, error)
        tracer.write({"type": "run_end", "stop_reason": reason, "steps": steps, "error": error, **asdict(totals)})
        return result

    step = 0
    try:
        for step in range(1, cfg.max_steps + 1):
            rendered = strategy.render(messages)
            estimated = estimator.estimate(rendered)
            # len > 2: there must be work to summarize, or a long task would compact forever.
            if len(messages) > 2 and strategy.should_compact(estimated):
                await compact(step)
                rendered = strategy.render(messages)
                estimated = estimator.estimate(rendered)
            if estimated + cfg.max_output_tokens > cfg.max_context_tokens:
                return finish("context_limit", step - 1)

            response = await call_llm(rendered, step, kind="agent")
            messages.append(response.to_message())

            if not response.tool_calls:
                totals.format_errors += 1
                if totals.format_errors >= cfg.max_format_errors:
                    return finish("format_errors", step)
                messages.append({"role": "user", "content": NUDGE})
                continue

            submitted = False
            for tc in response.tool_calls:
                result = await runner.call(tc.name, tc.arguments)
                totals.tool_calls += 1
                totals.tool_errors += int(result.error)
                totals.tool_time_ms += result.duration_ms
                observation = strategy.format_observation(result.output)
                signature = call_signature(tc.name, tc.arguments)
                call_counts[signature] += 1
                repeats = call_counts[signature]
                if cfg.repeat_warning_after and repeats >= cfg.repeat_warning_after and not result.submitted:
                    # Appended when the message is created, so history is never rewritten.
                    observation += REPEAT_WARNING.format(name=tc.name, count=repeats)
                    totals.repeat_warnings += 1
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": observation})
                tracer.write(
                    {
                        "type": "tool_call",
                        "step": step,
                        "name": tc.name,
                        "arguments": tc.arguments[:2000],
                        "exit_code": result.exit_code,
                        "error": result.error,
                        "duration_ms": result.duration_ms,
                        "output_chars": len(result.output),
                        "observation_chars": len(observation),
                        "repeat_count": repeats,
                    }
                )
                submitted = submitted or result.submitted
            if submitted:
                return finish("submitted", step)
        return finish("max_steps", step)
    except ContextOverflowError as exc:
        return finish("context_overflow", step, str(exc)[:500])
    except (httpx.HTTPError, RuntimeError, RetryableStreamError) as exc:
        return finish("llm_error", step, f"{type(exc).__name__}: {exc}"[:500])
