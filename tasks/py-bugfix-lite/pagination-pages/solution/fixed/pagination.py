import math


def paginate(items, page, per_page=10):
    """Return a dict describing one page of `items` (pages are 1-indexed)."""
    if per_page < 1:
        raise ValueError("per_page must be at least 1")
    total_pages = math.ceil(len(items) / per_page)
    last_page = max(total_pages, 1)
    if page < 1 or page > last_page:
        raise ValueError(f"page {page} is out of range 1..{last_page}")
    start = (page - 1) * per_page
    return {
        "page": page,
        "per_page": per_page,
        "total_items": len(items),
        "total_pages": total_pages,
        "items": items[start : start + per_page],
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
