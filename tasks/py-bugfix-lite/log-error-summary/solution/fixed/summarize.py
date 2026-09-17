import json
import re
from collections import Counter

CODE_RE = re.compile(r"\bcode=(\S+)")


def summarize(path):
    counts = Counter()
    with open(path) as f:
        for line in f:
            if line[:1].isspace():
                continue
            fields = line.split()
            if len(fields) < 2 or fields[1] != "ERROR":
                continue
            match = CODE_RE.search(line)
            counts[match.group(1) if match else "UNKNOWN"] += 1
    return {"total_errors": sum(counts.values()), "by_code": dict(sorted(counts.items()))}


if __name__ == "__main__":
    summary = summarize("logs/server.log")
    with open("error_counts.json", "w") as f:
        json.dump(summary, f, indent=2)
