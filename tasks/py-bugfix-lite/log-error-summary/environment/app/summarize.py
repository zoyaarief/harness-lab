import json
from collections import Counter


def summarize(path):
    counts = Counter()
    with open(path) as f:
        for line in f:
            if "ERROR" in line:
                code = line.split("code=")[1].split()[0]
                counts[code] += 1
    return dict(counts)


if __name__ == "__main__":
    counts = summarize("logs/server.log")
    with open("error_counts.json", "w") as f:
        json.dump(counts, f)
