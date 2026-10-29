from datetime import datetime, timezone
from typing import Optional

from api.db.cache import end_of_day
from api.db.db import get_connection
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
    OR EXISTS (
        SELECT 1 FROM whatsapp_episode_topic et
        JOIN whatsapp_key_topic t ON t.uid = et.topic_id
        WHERE et.episode_id = e.uid AND t.name ILIKE %s
    )
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
        sql += """ AND (
            summary ILIKE %s
            OR EXISTS (
                SELECT 1 FROM whatsapp_episode_topic et
                JOIN whatsapp_key_topic t ON t.uid = et.topic_id
                WHERE et.episode_id = whatsapp_conversation_episode.uid AND t.name ILIKE %s
            )
        )"""
        params.extend([pattern, pattern])
    sql += " ORDER BY window_to DESC LIMIT %s"
    params.append(safe_limit)
    return fetch_all(sql, tuple(params))


def list_topics(episode_id: str) -> list[dict]:
    return fetch_all(
        """
        SELECT t.uid, t.name
        FROM whatsapp_episode_topic et
        JOIN whatsapp_key_topic t ON t.uid = et.topic_id
        WHERE et.episode_id = %s
        ORDER BY t.name
        """,
        (episode_id,),
    )


def search_topics(q: Optional[str] = None, limit: int = 10) -> list[dict]:
    safe_limit = clamp_limit(limit)
    pattern = like_pattern(q)
    if pattern:
        return fetch_all(
            "SELECT uid, name FROM whatsapp_key_topic WHERE name ILIKE %s ORDER BY name LIMIT %s",
            (pattern, safe_limit),
        )
    return fetch_all(
        "SELECT uid, name FROM whatsapp_key_topic ORDER BY name LIMIT %s",
        (safe_limit,),
    )


def list_by_topic(topic_id: str, limit: int = 10) -> list[dict]:
    return fetch_all(
        """
        SELECT e.*
        FROM whatsapp_episode_topic et
        JOIN whatsapp_conversation_episode e ON e.uid = et.episode_id
        WHERE et.topic_id = %s
        ORDER BY e.window_to DESC
        LIMIT %s
        """,
        (topic_id, clamp_limit(limit)),
    )


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


def list_pending() -> list[dict]:
    return fetch_all(
        """
        SELECT m.conversation_id,
               min(m.cat) AS window_from,
               max(m.cat) AS last_cat,
               max(e.open_summary) AS current_summary,
               json_agg(
                   json_build_object(
                       'direction', m.direction,
                       'cat', m.cat,
                       'body', coalesce(m.content->>'body', m.content->>'caption', m.content->>'transcription', '')
                   ) ORDER BY m.cat
               ) AS messages
        FROM whatsapp_message m
        LEFT JOIN LATERAL (
            SELECT max(window_to) AS window_to,
                   max(summary) FILTER (WHERE window_to > now()) AS open_summary
            FROM whatsapp_conversation_episode e
            WHERE e.conversation_id = m.conversation_id
        ) e ON true
        WHERE m.cat > COALESCE(e.window_to, '-infinity'::timestamptz)
          AND coalesce(m.content->>'body', m.content->>'caption', m.content->>'transcription', '') <> ''
        GROUP BY m.conversation_id
        """
    )


def upsert_current(
    conversation_id: str,
    summary: str,
    topics: list[str],
    window_from: datetime,
    last_cat: datetime,
    model: str,
) -> str:
    now = datetime.now(timezone.utc)
    eod = end_of_day(now)
    clean = list(dict.fromkeys(t.strip().lower()[:64] for t in topics if t and t.strip()))[:8]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT uid, window_to FROM whatsapp_conversation_episode
                WHERE conversation_id = %s AND window_to > now()
                ORDER BY window_to DESC LIMIT 1
                """,
                (conversation_id,),
            )
            open_row = cur.fetchone()
            if open_row:
                episode_id = str(open_row[0])
                window_to = max(open_row[1], last_cat, eod)
                cur.execute(
                    """
                    UPDATE whatsapp_conversation_episode
                    SET summary = %s, window_to = %s, model = %s
                    WHERE uid = %s
                    """,
                    (summary, window_to, model, episode_id),
                )
            else:
                window_to = max(last_cat, eod)
                cur.execute(
                    """
                    INSERT INTO whatsapp_conversation_episode (
                        conversation_id, window_from, window_to, summary, model, cost_usd_micros
                    ) VALUES (%s, %s, %s, %s, %s, 0)
                    RETURNING uid
                    """,
                    (conversation_id, window_from, window_to, summary, model),
                )
                episode_id = str(cur.fetchone()[0])

            cur.execute(
                "DELETE FROM whatsapp_episode_topic WHERE episode_id = %s",
                (episode_id,),
            )
            if clean:
                cur.executemany(
                    "INSERT INTO whatsapp_key_topic (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                    [(name,) for name in clean],
                )
                cur.executemany(
                    """
                    INSERT INTO whatsapp_episode_topic (episode_id, topic_id)
                    SELECT %s, uid FROM whatsapp_key_topic WHERE name = %s
                    ON CONFLICT DO NOTHING
                    """,
                    [(episode_id, name) for name in clean],
                )
        conn.commit()
    return episode_id

