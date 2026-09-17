from text_utils import slugify


def test_basic_title():
    assert slugify("Hello World") == "hello-world"


def test_punctuation_and_spaces():
    assert slugify("  Hello,  World!! ") == "hello-world"
