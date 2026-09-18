"""Tools the agent can call, and the executor interface they run through.

Commands never run on the host: the Harbor adapter's executor sends them into the
task container via `environment.exec`.
"""

import base64
import json
import shlex
import time
from dataclasses import dataclass
from typing import Any, Protocol

from harness_lab.config import ToolSetName


@dataclass
class ExecOutput:
    output: str
    exit_code: int


class Executor(Protocol):
    async def run(self, command: str, timeout_sec: int) -> ExecOutput: ...


@dataclass
class ToolResult:
    output: str
    duration_ms: float
    exit_code: int | None = None
    submitted: bool = False
    error: bool = False


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


BASH = _fn(
    "bash",
    "Run a bash command in the task's working directory. Each call starts a fresh shell: "
    "`cd` and environment variables do not persist, so chain commands with `&&`. "
    "Returns the exit code and combined stdout/stderr.",
    {"command": {"type": "string", "description": "The command to run."}},
    ["command"],
)
VIEW_FILE = _fn(
    "view_file",
    "Show a file with line numbers. For a directory or a missing path, lists what is there instead.",
    {
        "path": {"type": "string"},
        "start_line": {"type": "integer", "description": "First line to show (default 1)."},
        "end_line": {"type": "integer", "description": "Last line to show (default start_line + 199)."},
    },
    ["path"],
)
EDIT_FILE = _fn(
    "edit_file",
    "Replace one exact occurrence of old_str with new_str in a file. old_str must match exactly "
    "once, including whitespace. To create or overwrite a whole file, pass an empty old_str.",
    {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
    ["path", "old_str", "new_str"],
)
SUBMIT = _fn(
    "submit",
    "Call this once the task is complete. Your work is then graded; you cannot continue after.",
    {},
    [],
)


def tool_specs(tool_set: ToolSetName) -> list[dict[str, Any]]:
    if tool_set == "bash":
        return [BASH, SUBMIT]
    return [BASH, VIEW_FILE, EDIT_FILE, SUBMIT]


# Runs inside the container. Reads a base64 JSON payload so file contents never need shell quoting.
_EDIT_SCRIPT = r"""
import base64, json, os, sys
p = json.loads(base64.b64decode(sys.argv[1]))
path, old, new = p["path"], p["old_str"], p["new_str"]
if old == "":
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    open(path, "w").write(new)
    print(f"Wrote {len(new.splitlines())} lines to {path}")
    sys.exit(0)
if not os.path.isfile(path):
    print(f"Error: {path} does not exist"); sys.exit(1)
text = open(path).read()
count = text.count(old)
if count != 1:
    print(f"Error: old_str appears {count} times in {path}; it must appear exactly once. "
          "Include more surrounding lines to make it unique." if count else
          f"Error: old_str was not found in {path}. View the file and copy the text exactly.")
    sys.exit(1)
open(path, "w").write(text.replace(old, new, 1))
line = text[: text.index(old)].count("\n") + 1
print(f"Edited {path} at line {line}")
"""


class ToolRunner:
    def __init__(self, executor: Executor, tool_set: ToolSetName, command_timeout_sec: int):
        self.executor = executor
        self.allowed = {spec["function"]["name"] for spec in tool_specs(tool_set)}
        self.timeout = command_timeout_sec

    async def call(self, name: str, raw_arguments: str) -> ToolResult:
        start = time.perf_counter()
        try:
            args = json.loads(raw_arguments) if raw_arguments.strip() else {}
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            return self._error(f"Error: could not parse tool arguments as JSON ({exc}).", start)

        if name not in self.allowed:
            return self._error(f"Error: unknown tool '{name}'. Available: {sorted(self.allowed)}.", start)
        if name == "submit":
            return ToolResult("Submitted.", self._ms(start), submitted=True)

        try:
            command = self._command_for(name, args)
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(f"Error: bad arguments for {name}: {exc}", start)

        result = await self.executor.run(command, self.timeout)
        output = result.output if result.output.strip() else "(no output)"
        if name == "bash":
            output = f"exit_code: {result.exit_code}\n{output}"
        return ToolResult(output, self._ms(start), exit_code=result.exit_code, error=result.exit_code != 0)

    def _command_for(self, name: str, args: dict[str, Any]) -> str:
        if name == "bash":
            return str(args["command"])
        if name == "view_file":
            start = max(1, int(args.get("start_line") or 1))
            end = int(args.get("end_line") or start + 199)
            path = shlex.quote(str(args["path"]))
            return (
                f"if [ -f {path} ]; then nl -ba -- {path} | sed -n '{start},{end}p'; "
                f"elif [ -d {path} ]; then echo 'Error:' {path} 'is a directory, not a file. Its contents:'; "
                f"ls -la -- {path}; exit 1; "
                f"else echo 'Error:' {path} 'does not exist. Contents of its parent directory:'; "
                f"ls -la -- \"$(dirname -- {path})\" 2>/dev/null | head -50; exit 1; fi"
            )
        if name == "edit_file":
            payload = {k: str(args[k]) for k in ("path", "old_str", "new_str")}
            encoded = base64.b64encode(json.dumps(payload).encode()).decode()
            return f"python3 -c {shlex.quote(_EDIT_SCRIPT)} {encoded}"
        raise ValueError(f"no command for tool {name}")

    def _error(self, message: str, start: float) -> ToolResult:
        return ToolResult(message, self._ms(start), error=True)

    @staticmethod
    def _ms(start: float) -> float:
        return (time.perf_counter() - start) * 1000
