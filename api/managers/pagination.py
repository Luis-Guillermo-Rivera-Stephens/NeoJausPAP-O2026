"""Paginación por página: offset = (page - 1) * limit."""


def page_window(page: int = 1, limit: int = 30, cap: int = 50) -> tuple[int, int, int]:
    try:
        safe_page = int(page)
    except (TypeError, ValueError):
        safe_page = 1
    try:
        safe_limit = int(limit)
    except (TypeError, ValueError):
        safe_limit = 30
    safe_page = max(1, safe_page)
    safe_limit = max(1, min(safe_limit, cap))
    return safe_page, safe_limit, (safe_page - 1) * safe_limit
