from harness_lab.config import HarnessConfig
from harness_lab.context import cap_text, make_strategy


def conversation(n_tools: int) -> list[dict]:
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
    for i in range(n_tools):
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
        messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"output {i} " * 10})
    return messages


def test_cap_text_keeps_head_and_tail():
    text = "".join(str(i % 10) for i in range(1000))
    capped = cap_text(text, 100)
    assert capped.startswith(text[:66]) and capped.endswith(text[-34:])
    assert "900 characters omitted" in capped
    assert cap_text("short", 100) == "short"


def test_full_never_rewrites_history():
    strategy = make_strategy(HarnessConfig(context_strategy="full"))
    messages = conversation(5)
    assert strategy.render(messages) is messages


def test_truncate_caps_at_insert_time_only():
    strategy = make_strategy(HarnessConfig(context_strategy="truncate", truncate_obs_chars=50))
    assert len(strategy.format_observation("x" * 500)) < 120
    messages = conversation(5)
    assert strategy.render(messages) == messages


def test_rolling_elides_all_but_last_k_without_mutating():
    strategy = make_strategy(HarnessConfig(context_strategy="rolling", rolling_keep_last=2))
    messages = conversation(5)
    original = [dict(m) for m in messages]
    rendered = strategy.render(messages)
    tool_contents = [m["content"] for m in rendered if m["role"] == "tool"]
    assert all("elided" in c for c in tool_contents[:3])
    assert tool_contents[3:] == ["output 3 " * 10, "output 4 " * 10]
    assert messages == original


def test_rolling_rewrites_the_prefix_as_the_run_grows():
    """The property that makes rolling cache-hostile: turn k's prompt is not a prefix of turn k+1's."""
    strategy = make_strategy(HarnessConfig(context_strategy="rolling", rolling_keep_last=2))
    before = strategy.render(conversation(3))
    after = strategy.render(conversation(4))
    assert after[: len(before)] != before


def test_compaction_threshold():
    strategy = make_strategy(HarnessConfig(context_strategy="compaction", compaction_threshold_tokens=1000))
    assert not strategy.should_compact(999)
    assert strategy.should_compact(1001)
