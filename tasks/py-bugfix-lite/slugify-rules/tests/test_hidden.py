import pytest

from text_utils import slugify


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello World", "hello-world"),
        ("  Héllo,  World!! ", "hello-world"),
        ("Crème brûlée", "creme-brulee"),
        ("Python 3.12 Release", "python-3-12-release"),
        ("---", ""),
        ("", ""),
        ("ÅNGSTRÖM units", "angstrom-units"),
        ("Ça va? Oui — très bien! 100%", "ca-va-oui-tres-bien-100"),
    ],
)
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_max_length():
    assert slugify("a" * 60) == "a" * 50


def test_no_trailing_hyphen_after_truncation():
    assert slugify("hello world foo", max_length=6) == "hello"
