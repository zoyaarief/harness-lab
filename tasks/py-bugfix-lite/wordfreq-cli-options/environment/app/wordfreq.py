import argparse
import re
from collections import Counter

WORD_RE = re.compile(r"[a-z']+")


def count_words(text):
    return Counter(WORD_RE.findall(text.lower()))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Count word frequencies in a text file.")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    with open(args.path) as f:
        counts = count_words(f.read())
    for word, n in counts.most_common():
        print(f"{word}\t{n}")


if __name__ == "__main__":
    main()
