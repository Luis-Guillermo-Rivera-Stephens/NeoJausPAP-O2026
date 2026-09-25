from typing import Optional

from api.managers._sql import clamp_limit, fetch_all, like_pattern


def list_by_conversation(
    conversation_id: str,
    limit: int = 10,
    q: Optional[str] = None,
) -> list[dict]:
    safe_limit = clamp_limit(limit)
    sql = "SELECT * FROM whatsapp_message WHERE conversation_id = %s"
    params: list[object] = [conversation_id]
    pattern = like_pattern(q)
    if pattern:
        sql += " AND coalesce(content->>'body', content->>'caption', content->>'transcription', '') ILIKE %s"
        params.append(pattern)
    sql += " ORDER BY cat DESC LIMIT %s"
    params.append(safe_limit)
    return fetch_all(sql, tuple(params))
