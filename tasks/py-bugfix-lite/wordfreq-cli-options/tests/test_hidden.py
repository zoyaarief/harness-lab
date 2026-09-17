from wordfreq import count_words, main


def run(capsys, *args):
    main(list(args))
    return capsys.readouterr().out.strip().splitlines()


def test_full_output_sorted(capsys):
    assert run(capsys, "data/sample.txt") == [
        "hat\t4", "the\t4", "a\t3", "and\t2", "cat\t2", "is\t2",
        "bat\t1", "blue\t1", "cat's\t1", "dog's\t1", "don't\t1",
        "forget\t1", "quoted\t1", "red\t1", "words\t1",
    ]


def test_top(capsys):
    assert run(capsys, "data/sample.txt", "--top", "3") == ["hat\t4", "the\t4", "a\t3"]


def test_top_zero(capsys):
    assert run(capsys, "data/sample.txt", "--top", "0") == []


def test_min_length(capsys):
    got = run(capsys, "data/sample.txt", "--min-length", "4", "--top", "3")
    assert got == ["blue\t1", "cat's\t1", "dog's\t1"]


def test_stopwords(capsys):
    got = run(capsys, "data/sample.txt", "--stopwords", "data/stopwords.txt", "--top", "3")
    assert got == ["hat\t4", "cat\t2", "bat\t1"]


def test_apostrophes_in_count_words():
    assert count_words("'hello' ''world'' it's") == {"hello": 1, "world": 1, "it's": 1}
