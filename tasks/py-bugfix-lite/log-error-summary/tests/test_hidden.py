import json
import re
import subprocess
import sys
from collections import Counter

from summarize import summarize


def reference(path):
    counts = Counter()
    with open(path) as f:
        for line in f:
            if line[:1].isspace():
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "ERROR":
                match = re.search(r"\bcode=(\S+)", line)
                counts[match.group(1) if match else "UNKNOWN"] += 1
    return {"total_errors": sum(counts.values()), "by_code": dict(counts)}


def test_function_matches_reference():
    assert summarize("logs/server.log") == reference("logs/server.log")


def test_script_writes_json():
    subprocess.run([sys.executable, "summarize.py"], check=True, timeout=60)
    with open("error_counts.json") as f:
        assert json.load(f) == reference("logs/server.log")


def test_tricky_lines(tmp_path):
    path = tmp_path / "tricky.log"
    path.write_text(
        '2026-01-01T00:00:00Z ERROR request_id=1 code=E_X msg="a"\n'
        "    at something code=E_TRACE ERROR\n"
        '2026-01-01T00:00:01Z INFO  request_id=2 msg="ERROR code=E_FAKE"\n'
        '2026-01-01T00:00:02Z ERROR request_id=3 msg="no code"\n'
        "2026-01-01T00:00:03Z ERROR request_id=4 code=E_X\n"
    )
    assert summarize(path) == {"total_errors": 3, "by_code": {"E_X": 2, "UNKNOWN": 1}}
