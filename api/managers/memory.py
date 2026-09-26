"""Historial en chats/chat_messages. El agente solo recibe ventanas de ai_memory."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from api.db.db import get_connection
from api.managers._sql import fetch_all, fetch_one, like_pattern
from api.managers.pagination import page_window

WINDOW = timedelta(hours=24)


def _advisor_id() -> str:
    row = fetch_one("SELECT uid FROM clients ORDER BY cat LIMIT 1")
    if not row:
        raise RuntimeError("No hay asesores; ai_memory.client_id no puede quedar vacío")
    return str(row["uid"])


def _owned(thread_id: str) -> Optional[dict]:
    return fetch_one(
        "SELECT uid, title, uat FROM chats WHERE uid = %s AND client_id = %s",
        (thread_id, _advisor_id()),
    )


def create_chat() -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (client_id) VALUES (%s) RETURNING uid, title, uat",
                (_advisor_id(),),
            )
            uid, title, uat = cur.fetchone()
        conn.commit()
    return {"uid": str(uid), "title": title, "uat": uat.isoformat()}


def list_chats(limit: int = 20, before: Optional[datetime] = None) -> dict:
    safe_limit = max(1, min(limit, 50))
    sql = "SELECT uid, title, uat FROM chats WHERE client_id = %s"
    params: list[object] = [_advisor_id()]
    if before is not None:
        sql += " AND uat < %s"
        params.append(before)
    sql += " ORDER BY uat DESC LIMIT %s"
    params.append(safe_limit + 1)
    rows = fetch_all(sql, tuple(params))
    has_more = len(rows) > safe_limit
    page = rows[:safe_limit]
    return {
        "chats": [
            {"uid": str(row["uid"]), "title": row["title"], "uat": row["uat"].isoformat()}
            for row in page
        ],
        "hasMore": has_more,
    }


def latest_chat_id() -> Optional[str]:
    row = fetch_one(
        "SELECT uid FROM chats WHERE client_id = %s ORDER BY uat DESC LIMIT 1",
        (_advisor_id(),),
    )
    return str(row["uid"]) if row else None


def owns(thread_id: str) -> bool:
    return _owned(thread_id) is not None


def has_title(thread_id: str) -> bool:
    row = _owned(thread_id)
    return bool(row and row["title"])


def set_title(thread_id: str, title: str) -> Optional[str]:
    text = " ".join(title.strip().strip('"').strip("'").split())
    text = text.rstrip(".").strip()[:80]
    if not text or not _owned(thread_id):
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chats
                SET title = %s, uat = CURRENT_TIMESTAMP
                WHERE uid = %s AND title IS NULL
                RETURNING title
                """,
                (text, thread_id),
            )
            row = cur.fetchone()
        conn.commit()
    if row:
        return row[0]
    owned = _owned(thread_id)
    return owned["title"] if owned else None


def get_title(thread_id: str) -> Optional[str]:
    row = _owned(thread_id)
    return row["title"] if row else None


def list_messages(thread_id: str, page: int = 1, limit: int = 30) -> dict:
    if not _owned(thread_id):
        return {"messages": [], "hasMore": False, "page": 1}
    safe_page, safe_limit, offset = page_window(page, limit)
    rows = fetch_all(
        """
        SELECT role, body, cat
        FROM chat_messages
        WHERE chat_id = %s
        ORDER BY cat DESC
        LIMIT %s OFFSET %s
        """,
        (thread_id, safe_limit + 1, offset),
    )
    has_more = len(rows) > safe_limit
    page_rows = list(reversed(rows[:safe_limit]))
    return {
        "messages": [
            {"role": row["role"], "body": row["body"], "cat": row["cat"].isoformat()}
            for row in page_rows
        ],
        "hasMore": has_more,
        "page": safe_page,
    }


def append_message(thread_id: str, role: str, body: str) -> None:
    text = body.strip()
    if not text or not _owned(thread_id):
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (chat_id, role, body)
                VALUES (%s, %s, %s)
                """,
                (thread_id, role, text),
            )
            cur.execute(
                "UPDATE chats SET uat = CURRENT_TIMESTAMP WHERE uid = %s",
                (thread_id,),
            )
        conn.commit()


def _latest(thread_id: str) -> list[dict]:
    return fetch_all(
        """
        SELECT uid, window_to, summary
        FROM ai_memory
        WHERE chat_id = %s
        ORDER BY window_to DESC
        LIMIT 2
        """,
        (thread_id,),
    )


def list_past_windows(
    q: Optional[str] = None,
    limit: int = 5,
    before: Optional[datetime] = None,
) -> list[dict]:
    """Ventanas ya cerradas del chat más reciente. La abierta no entra."""
    thread_id = latest_chat_id()
    if not thread_id:
        return []
    safe_limit = max(1, min(limit, 20))
    sql = """
        SELECT uid, window_from, window_to, summary
        FROM ai_memory
        WHERE chat_id = %s AND window_to <= now()
    """
    params: list[object] = [thread_id]
    if before is not None:
        sql += " AND window_to < %s"
        params.append(before)
    pattern = like_pattern(q)
    if pattern:
        sql += " AND summary ILIKE %s"
        params.append(pattern)
    sql += " ORDER BY window_to DESC LIMIT %s"
    params.append(safe_limit)
    return fetch_all(sql, tuple(params))


def context_for_prompt(thread_id: str) -> tuple[str, str]:
    """Última ventana cerrada y la ventana abierta. Nunca el historial de mensajes."""
    rows = _latest(thread_id)
    if not rows:
        return "", ""
    now = datetime.now(timezone.utc)
    newest = rows[0]
    if newest["window_to"] <= now:
        return newest["summary"], ""
    closed = rows[1]["summary"] if len(rows) > 1 else ""
    return closed, newest["summary"]


def save_current(thread_id: str, summary: str) -> None:
    text = summary.strip()
    if not text or not _owned(thread_id):
        return
    now = datetime.now(timezone.utc)
    rows = _latest(thread_id)
    open_row = rows[0] if rows and rows[0]["window_to"] > now else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            if open_row:
                cur.execute(
                    """
                    UPDATE ai_memory
                    SET summary = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE uid = %s
                    """,
                    (text, open_row["uid"]),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO ai_memory (client_id, chat_id, window_from, window_to, summary)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (_advisor_id(), thread_id, now, now + WINDOW, text),
                )
        conn.commit()
