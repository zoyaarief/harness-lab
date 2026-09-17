import argparse
import re
from collections import Counter

WORD_RE = re.compile(r"[a-z']+")


def count_words(text, min_length=1, stopwords=frozenset()):
    counts = Counter()
    for raw in WORD_RE.findall(text.lower()):
        word = raw.strip("'")
        if word and len(word) >= min_length and word not in stopwords:
            counts[word] += 1
    return counts


def load_stopwords(path):
    with open(path) as f:
        return {line.strip().lower() for line in f if line.strip()}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count word frequencies in a text file.")
    parser.add_argument("path")
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--stopwords")
    args = parser.parse_args(argv)
    stopwords = load_stopwords(args.stopwords) if args.stopwords else frozenset()
    with open(args.path) as f:
        counts = count_words(f.read(), args.min_length, stopwords)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if args.top is not None:
        ranked = ranked[: max(args.top, 0)]
    for word, n in ranked:
        print(f"{word}\t{n}")


if __name__ == "__main__":
    main()
