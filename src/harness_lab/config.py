"""Harness configuration: every architectural knob the experiments vary lives here."""

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

import yaml

ContextStrategyName = Literal["full", "truncate", "rolling", "compaction"]
ToolSetName = Literal["bash", "bash+edit"]


@dataclass
class HarnessConfig:
    variant: str = "full"

    # --- architecture knobs -------------------------------------------------
    # full:       keep every message verbatim
    # truncate:   cap each tool output when it is added; history is never rewritten
    # rolling:    elide all but the last few tool outputs on every call (rewrites history)
    # compaction: keep everything until the context passes a threshold, then summarize
    context_strategy: ContextStrategyName = "full"
    tool_set: ToolSetName = "bash+edit"
    reasoning: bool = False

    # --- limits ---------------------------------------------------------------
    max_steps: int = 30
    max_output_tokens: int = 1024
    max_context_tokens: int = 30_000
    max_format_errors: int = 3
    command_timeout_sec: int = 60

    # --- strategy parameters ------------------------------------------------
    obs_hard_cap_chars: int = 16_000  # applies to every strategy, as a safety net
    truncate_obs_chars: int = 2_000
    rolling_keep_last: int = 3
    compaction_threshold_tokens: int = 12_000

    # --- sampling -------------------------------------------------------------
    temperature: float = 0.7
    top_p: float = 0.8
    extra_body: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None, **overrides: Any) -> "HarnessConfig":
        data: dict[str, Any] = {}
        if path:
            data = yaml.safe_load(Path(path).read_text()) or {}
        data.update({k: v for k, v in overrides.items() if v is not None})
        known = {f.name: f for f in fields(cls)}
        unknown = set(data) - set(known)
        if unknown:
            raise ValueError(f"Unknown harness config keys: {sorted(unknown)}")
        cfg = cls(**data)
        cfg._coerce()
        return cfg

    def _coerce(self) -> None:
        # Values from `harbor run --ak key=value` arrive as strings.
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, str) or f.type in (str, "str"):
                continue
            if f.type in (int, "int"):
                setattr(self, f.name, int(value))
            elif f.type in (float, "float"):
                setattr(self, f.name, float(value))
            elif f.type in (bool, "bool"):
                setattr(self, f.name, value.strip().lower() in {"1", "true", "yes", "on"})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
