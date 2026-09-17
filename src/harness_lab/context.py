"""Context strategies: how the harness keeps the conversation within budget.

The strategies differ in one property that matters for inference cost: whether
earlier messages ever change. A server can only reuse cached KV for the longest
prefix that is byte-for-byte identical to a previous request, so any rewrite of
old history forces the server to recompute everything after the rewrite.

  full        never rewrites history                       -> cache-friendly, largest prompts
  truncate    shortens each tool output once, on insert    -> cache-friendly, smaller prompts
  rolling     elides old tool outputs on every call        -> smaller prompts, cache-hostile
  compaction  replaces history with a summary when large   -> one cache miss per compaction
"""

from typing import Any

from harness_lab.config import HarnessConfig

COMPACTION_PROMPT = (
    "Your context is getting long. Write a concise summary of the work so far so you can "
    "continue without the full history. Include: the task goal, what you have learned about "
    "the code (file paths, key functions, root cause), every change you have made, commands "
    "that failed and why, and the exact next steps. Do not call any tools."
)


def cap_text(text: str, limit: int) -> str:
    """Keep the head and tail of `text` within `limit` characters."""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n[... {omitted} characters omitted ...]\n{text[-tail:]}"


class ContextStrategy:
    name = "full"

    def __init__(self, cfg: HarnessConfig):
        self.cfg = cfg

    def format_observation(self, text: str) -> str:
        return cap_text(text, self.cfg.obs_hard_cap_chars)

    def render(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return messages

    def should_compact(self, estimated_prompt_tokens: int) -> bool:
        return False


class TruncateStrategy(ContextStrategy):
    name = "truncate"

    def format_observation(self, text: str) -> str:
        return cap_text(text, min(self.cfg.truncate_obs_chars, self.cfg.obs_hard_cap_chars))


class RollingWindowStrategy(ContextStrategy):
    name = "rolling"

    def render(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tool_positions = [i for i, m in enumerate(messages) if m["role"] == "tool"]
        keep = set(tool_positions[-self.cfg.rolling_keep_last :]) if self.cfg.rolling_keep_last > 0 else set()
        rendered = []
        for i, message in enumerate(messages):
            if message["role"] == "tool" and i not in keep:
                size = len(message.get("content") or "")
                message = {**message, "content": f"[output of an earlier tool call elided ({size} chars)]"}
            rendered.append(message)
        return rendered


class CompactionStrategy(ContextStrategy):
    name = "compaction"

    def should_compact(self, estimated_prompt_tokens: int) -> bool:
        return estimated_prompt_tokens > self.cfg.compaction_threshold_tokens


STRATEGIES: dict[str, type[ContextStrategy]] = {
    cls.name: cls for cls in (ContextStrategy, TruncateStrategy, RollingWindowStrategy, CompactionStrategy)
}


def make_strategy(cfg: HarnessConfig) -> ContextStrategy:
    try:
        return STRATEGIES[cfg.context_strategy](cfg)
    except KeyError:
        raise ValueError(f"Unknown context strategy {cfg.context_strategy!r}; choose from {sorted(STRATEGIES)}")
