def paginate(items, page, per_page=10):
    """Return a dict describing one page of `items` (pages are 1-indexed)."""
    total_pages = len(items) // per_page
    start = page * per_page
    end = start + per_page
    return {
        "page": page,
        "per_page": per_page,
        "total_items": len(items),
        "total_pages": total_pages,
        "items": items[start:end],
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
