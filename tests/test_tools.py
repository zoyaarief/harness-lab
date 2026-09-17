import asyncio
import json

import pytest

from harness_lab.tools import ExecOutput, ToolRunner, tool_specs


class LocalExecutor:
    """Runs the harness's own generated commands in a temp dir (never model output)."""

    def __init__(self, cwd):
        self.cwd = cwd
        self.commands = []

    async def run(self, command, timeout_sec):
        self.commands.append(command)
        proc = await asyncio.create_subprocess_shell(
            command, cwd=self.cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout_sec)
        return ExecOutput(out.decode(), proc.returncode)


@pytest.fixture
def runner(tmp_path):
    return ToolRunner(LocalExecutor(tmp_path), "bash+edit", command_timeout_sec=10)


def test_tool_sets():
    assert [t["function"]["name"] for t in tool_specs("bash")] == ["bash", "submit"]
    assert [t["function"]["name"] for t in tool_specs("bash+edit")] == ["bash", "view_file", "edit_file", "submit"]


async def test_bash_reports_exit_code(runner):
    result = await runner.call("bash", json.dumps({"command": "echo hi && exit 3"}))
    assert result.output == "exit_code: 3\nhi\n"
    assert result.exit_code == 3 and result.error


async def test_bad_json_and_unknown_tool(runner):
    assert (await runner.call("bash", "{not json")).error
    result = await runner.call("delete_everything", "{}")
    assert result.error and "unknown tool" in result.output


async def test_bash_only_tool_set_rejects_edit(tmp_path):
    runner = ToolRunner(LocalExecutor(tmp_path), "bash", command_timeout_sec=10)
    result = await runner.call("edit_file", json.dumps({"path": "a", "old_str": "", "new_str": "x"}))
    assert result.error and "unknown tool" in result.output


async def test_submit(runner):
    result = await runner.call("submit", "")
    assert result.submitted and not result.error


async def test_edit_file_create_replace_and_ambiguity(runner, tmp_path):
    special = "quote ' and \" and $HOME and `backticks`\n"
    create = await runner.call("edit_file", json.dumps({"path": "pkg/mod.py", "old_str": "", "new_str": "a = 1\na = 1\n"}))
    assert not create.error
    ambiguous = await runner.call("edit_file", json.dumps({"path": "pkg/mod.py", "old_str": "a = 1", "new_str": "b"}))
    assert ambiguous.error and "appears 2 times" in ambiguous.output
    missing = await runner.call("edit_file", json.dumps({"path": "pkg/mod.py", "old_str": "zzz", "new_str": "b"}))
    assert missing.error and "not found" in missing.output
    replace = await runner.call(
        "edit_file", json.dumps({"path": "pkg/mod.py", "old_str": "a = 1\na = 1\n", "new_str": special})
    )
    assert not replace.error and "line 1" in replace.output
    assert (tmp_path / "pkg" / "mod.py").read_text() == special


async def test_view_file_numbers_lines(runner, tmp_path):
    (tmp_path / "f.txt").write_text("".join(f"line {i}\n" for i in range(1, 11)))
    result = await runner.call("view_file", json.dumps({"path": "f.txt", "start_line": 3, "end_line": 4}))
    assert result.output.split("\n")[:2] == ["     3\tline 3", "     4\tline 4"]
    missing = await runner.call("view_file", json.dumps({"path": "nope.txt"}))
    assert "file not found" in missing.output
