"""Sanity-check py-bugfix-lite without Docker.

For every task: the visible and hidden tests must FAIL on the shipped code and PASS
after the reference fix is applied. Runs on the host because it only executes the
task authors' own code, never model output.

    uv run python scripts/check_tasks.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tasks" / "py-bugfix-lite"


def pytest(app: Path, target: str) -> bool:
    env = {**os.environ, "PYTHONPATH": str(app)}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", target],
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode == 0


def check(task_dir: Path) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        app = Path(tmp) / "app"
        shutil.copytree(task_dir / "environment" / "app", app)
        build = app / "_build.py"
        if build.exists():
            subprocess.run([sys.executable, "_build.py"], cwd=app, check=True)
            build.unlink()
        hidden = Path(tmp) / "tests" / "test_hidden.py"
        hidden.parent.mkdir()
        shutil.copy(task_dir / "tests" / "test_hidden.py", hidden)

        if pytest(app, "tests"):
            problems.append("visible tests pass on buggy code")
        if pytest(app, str(hidden)):
            problems.append("hidden tests pass on buggy code")

        shutil.copytree(task_dir / "solution" / "fixed", app, dirs_exist_ok=True)
        if not pytest(app, "tests"):
            problems.append("visible tests fail on the reference fix")
        if not pytest(app, str(hidden)):
            problems.append("hidden tests fail on the reference fix")
    return problems


def main() -> int:
    failures = 0
    for task_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        problems = check(task_dir)
        failures += bool(problems)
        print(f"{'FAIL' if problems else 'ok  '}  {task_dir.name}" + (f": {'; '.join(problems)}" if problems else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
