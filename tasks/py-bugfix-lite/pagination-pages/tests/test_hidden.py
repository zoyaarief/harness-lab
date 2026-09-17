import pytest

from pagination import paginate


def test_middle_page():
    assert paginate(list(range(25)), 2, 10) == {
        "page": 2,
        "per_page": 10,
        "total_items": 25,
        "total_pages": 3,
        "items": list(range(10, 20)),
        "has_next": True,
        "has_prev": True,
    }


def test_last_partial_page():
    result = paginate(list(range(25)), 3, 10)
    assert result["items"] == [20, 21, 22, 23, 24]
    assert result["has_next"] is False and result["has_prev"] is True


def test_exact_multiple():
    result = paginate(list(range(20)), 2, 10)
    assert result["total_pages"] == 2 and result["has_next"] is False


def test_empty_list():
    result = paginate([], 1, 10)
    assert result["items"] == [] and result["total_pages"] == 0
    assert result["has_next"] is False and result["has_prev"] is False


@pytest.mark.parametrize("page", [0, -1, 4])
def test_out_of_range(page):
    with pytest.raises(ValueError):
        paginate(list(range(25)), page, 10)


def test_empty_list_page_two():
    with pytest.raises(ValueError):
        paginate([], 2, 10)


@pytest.mark.parametrize("per_page", [0, -5])
def test_bad_per_page(per_page):
    with pytest.raises(ValueError):
        paginate([1, 2], 1, per_page)


def test_first_page():
    result = paginate(["a", "b", "c"], 1, 2)
    assert result["items"] == ["a", "b"]
    assert result["has_prev"] is False and result["has_next"] is True
