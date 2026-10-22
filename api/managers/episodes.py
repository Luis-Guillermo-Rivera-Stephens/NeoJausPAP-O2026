from typing import Optional

from api.managers._sql import clamp_limit, fetch_all, like_pattern

_EPISODE_SEARCH = """
SELECT
    'episode' AS source,
    e.conversation_id,
    trim(c.first_name || ' ' || coalesce(c.first_last_name, '')) AS client_name,
    c.client_status::text AS client_status,
    e.summary AS text,
    e.cat,
    e.window_from,
    e.window_to
FROM whatsapp_conversation_episode e
JOIN whatsapp_conversation wc ON wc.uid = e.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id AND c.is_deleted = false
WHERE (
    e.summary ILIKE %s
    OR e.key_topics::text ILIKE %s
    OR c.first_name ILIKE %s
    OR coalesce(c.first_last_name, '') ILIKE %s
    OR coalesce(c.preferred_name, '') ILIKE %s
    OR c.client_status::text ILIKE %s
)
"""

_MESSAGE_SEARCH = """
SELECT
    'message' AS source,
    m.conversation_id,
    trim(c.first_name || ' ' || coalesce(c.first_last_name, '')) AS client_name,
    c.client_status::text AS client_status,
    coalesce(m.content->>'body', m.content->>'caption', m.content->>'transcription', '') AS text,
    m.cat,
    NULL::timestamptz AS window_from,
    NULL::timestamptz AS window_to
FROM whatsapp_message m
JOIN whatsapp_conversation wc ON wc.uid = m.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id AND c.is_deleted = false
WHERE coalesce(m.content->>'body', m.content->>'caption', m.content->>'transcription', '') ILIKE %s
"""


def list_by_conversation(
    conversation_id: str,
    limit: int = 5,
    q: Optional[str] = None,
) -> list[dict]:
    safe_limit = clamp_limit(limit, default=5)
    sql = "SELECT * FROM whatsapp_conversation_episode WHERE conversation_id = %s"
    params: list[object] = [conversation_id]
    pattern = like_pattern(q)
    if pattern:
        sql += " AND (summary ILIKE %s OR key_topics::text ILIKE %s)"
        params.extend([pattern, pattern])
    sql += " ORDER BY window_to DESC LIMIT %s"
    params.append(safe_limit)
    return fetch_all(sql, tuple(params))


def buscar_estado(
    q: str,
    client_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """Episodios primero. Si no hay coincidencias, mensajes de la conversación."""
    pattern = like_pattern(q)
    if not pattern:
        return []
    safe_limit = clamp_limit(limit)
    episode_sql = _EPISODE_SEARCH
    params: list[object] = [pattern] * 6
    if client_id:
        episode_sql += " AND wc.client_id = %s"
        params.append(client_id)
    episode_sql += " ORDER BY e.window_to DESC LIMIT %s"
    params.append(safe_limit)
    episodes = fetch_all(episode_sql, tuple(params))
    if episodes:
        return episodes

    message_sql = _MESSAGE_SEARCH
    msg_params: list[object] = [pattern]
    if client_id:
        message_sql += " AND wc.client_id = %s"
        msg_params.append(client_id)
    message_sql += " ORDER BY m.cat DESC LIMIT %s"
    msg_params.append(safe_limit)
    return fetch_all(message_sql, tuple(msg_params))
