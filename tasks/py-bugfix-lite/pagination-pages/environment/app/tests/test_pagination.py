import math

import pytest

from pagination import paginate

CASES = [(n, per_page, page) for n in range(0, 41) for per_page in (1, 3, 7, 10) for page in range(1, 4)]


@pytest.mark.parametrize("n,per_page,page", CASES)
def test_page_contents(n, per_page, page):
    items = list(range(n))
    total_pages = math.ceil(n / per_page)
    if page > max(total_pages, 1):
        with pytest.raises(ValueError):
            paginate(items, page, per_page)
        return
    result = paginate(items, page, per_page)
    assert result["items"] == items[(page - 1) * per_page : page * per_page]
    assert result["total_pages"] == total_pages
