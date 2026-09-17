import json

from harness_lab.config import HarnessConfig
from harness_lab.llm import CallStats, LLMResponse, ToolCall
from harness_lab.loop import run_agent
from harness_lab.tools import ExecOutput
from harness_lab.tracing import Tracer


class FakeExecutor:
    def __init__(self, output="x" * 50):
        self.output = output
        self.commands = []

    async def run(self, command, timeout_sec):
        self.commands.append(command)
        return ExecOutput("/app" if command == "pwd" else self.output, 0)


class ScriptedLLM:
    """Returns scripted responses and records every request it receives."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    async def chat(self, messages, tools, **kwargs):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools, **kwargs})
        content, calls = self.script.pop(0)
        prompt_tokens = (len(json.dumps(tools)) + sum(len(json.dumps(m)) for m in messages)) // 3
        stats = CallStats(prompt_tokens=prompt_tokens, cached_tokens=0, completion_tokens=10, e2e_ms=5.0)
        return LLMResponse(content, "", calls, stats)


def bash(i, cmd="ls"):
    return ToolCall(f"c{i}", "bash", json.dumps({"command": cmd}))


SUBMIT = ToolCall("s", "submit", "{}")


async def test_runs_tools_until_submit():
    llm = ScriptedLLM([("", [bash(1)]), ("", [bash(2, "pytest")]), ("done", [SUBMIT])])
    executor = FakeExecutor()
    tracer = Tracer(None, {})
    result = await run_agent("fix it", executor, llm, HarnessConfig(), tracer)

    assert result.stop_reason == "submitted" and result.steps == 3
    assert executor.commands == ["pwd", "ls", "pytest"]
    assert result.totals.llm_calls == 3 and result.totals.tool_calls == 3
    assert "/app" in llm.requests[0]["messages"][0]["content"]
    assert llm.requests[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    last = llm.requests[-1]["messages"]
    assert [m["role"] for m in last] == ["system", "user", "assistant", "tool", "assistant", "tool"]
    types = [r["type"] for r in tracer.records]
    assert types[0] == "run_start" and types[-1] == "run_end" and types.count("llm_call") == 3


async def test_nudges_when_no_tool_call_then_gives_up():
    llm = ScriptedLLM([("thinking...", []), ("still thinking", [])])
    result = await run_agent("t", FakeExecutor(), llm, HarnessConfig(max_format_errors=2), Tracer(None, {}))
    assert result.stop_reason == "format_errors"
    assert llm.requests[1]["messages"][-1]["role"] == "user"


async def test_max_steps():
    llm = ScriptedLLM([("", [bash(i)]) for i in range(3)])
    result = await run_agent("t", FakeExecutor(), llm, HarnessConfig(max_steps=3), Tracer(None, {}))
    assert result.stop_reason == "max_steps" and result.steps == 3


async def test_full_history_is_append_only():
    """Each request must extend the previous one exactly: the cache-friendly property."""
    llm = ScriptedLLM([("", [bash(i)]) for i in range(4)] + [("", [SUBMIT])])
    await run_agent("t", FakeExecutor(), llm, HarnessConfig(context_strategy="full"), Tracer(None, {}))
    for prev, cur in zip(llm.requests, llm.requests[1:]):
        assert cur["messages"][: len(prev["messages"])] == prev["messages"]


async def test_compaction_replaces_history_with_summary():
    # ~2k tokens per observation: over the 4k threshold after two tool steps, not after one.
    script = [("", [bash(0)]), ("", [bash(1)]), ("SUMMARY: found the bug", []), ("", [SUBMIT])]
    llm = ScriptedLLM(script)
    cfg = HarnessConfig(context_strategy="compaction", compaction_threshold_tokens=4000)
    tracer = Tracer(None, {})
    result = await run_agent("the task", FakeExecutor("y" * 6000), llm, cfg, tracer)

    assert result.stop_reason == "submitted" and result.steps == 3
    assert result.totals.compactions == 1
    summary_request = next(r for r in llm.requests if "summary" in r["messages"][-1]["content"].lower())
    assert summary_request["messages"][-1]["role"] == "user"
    after = llm.requests[-1]["messages"]
    assert len(after) == 2 and "SUMMARY: found the bug" in after[1]["content"]
    assert [r["kind"] for r in tracer.records if r["type"] == "llm_call"].count("compaction") == 1


async def test_null_extra_body_key_is_dropped():
    llm = ScriptedLLM([("", [SUBMIT])])
    cfg = HarnessConfig(extra_body={"chat_template_kwargs": None, "seed": 1})
    await run_agent("t", FakeExecutor(), llm, cfg, Tracer(None, {}))
    assert llm.requests[0]["extra_body"] == {"seed": 1}
