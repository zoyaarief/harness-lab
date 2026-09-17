"""Append-only JSONL trace: one line per model call, tool call, and run summary."""

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


class Tracer:
    def __init__(self, path: Path | None, run_meta: dict[str, Any]):
        self.path = path
        self.run_meta = run_meta
        self.records: list[dict[str, Any]] = []
        self._t0 = time.perf_counter()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.write({"type": "run_start", **run_meta})

    def write(self, record: dict[str, Any]) -> None:
        record = {"t_run_s": round(time.perf_counter() - self._t0, 3), "wall": time.time(), **record}
        self.records.append(record)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(record, default=_default) + "\n")


def _default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return str(value)
