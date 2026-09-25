"""Lecturas Postgres compartidas por los managers."""

from typing import Optional

from psycopg.rows import dict_row

from api.db.db import get_connection


def fetch_all(sql: str, params: tuple[object, ...] = ()) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def fetch_one(sql: str, params: tuple[object, ...] = ()) -> Optional[dict]:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def clamp_limit(limit: int, default: int = 10, cap: int = 50) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, cap))


def like_pattern(q: Optional[str]) -> Optional[str]:
    text = (q or "").strip()
    if not text:
        return None
    return f"%{text}%"
