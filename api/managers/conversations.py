from typing import Optional

from api.managers._sql import clamp_limit, fetch_all, like_pattern


def list_conversations(
    connection_id: Optional[str] = None,
    client_id: Optional[str] = None,
    limit: int = 10,
    q: Optional[str] = None,
) -> list[dict]:
    safe_limit = clamp_limit(limit)
    clauses: list[str] = []
    params: list[object] = []
    if connection_id is not None:
        clauses.append("connection_id = %s")
        params.append(connection_id)
    if client_id is not None:
        clauses.append("client_id = %s")
        params.append(client_id)
    pattern = like_pattern(q)
    if pattern:
        clauses.append(
            """(
                EXISTS (
                    SELECT 1 FROM crm_clients c
                    WHERE c.uid = whatsapp_conversation.client_id
                      AND (
                        c.first_name ILIKE %s
                        OR coalesce(c.first_last_name, '') ILIKE %s
                        OR coalesce(c.preferred_name, '') ILIKE %s
                      )
                )
                OR EXISTS (
                    SELECT 1 FROM whatsapp_conversation_episode e
                    WHERE e.conversation_id = whatsapp_conversation.uid
                      AND (e.summary ILIKE %s OR e.key_topics::text ILIKE %s)
                )
                OR EXISTS (
                    SELECT 1 FROM whatsapp_message m
                    WHERE m.conversation_id = whatsapp_conversation.uid
                      AND coalesce(m.content->>'body', m.content->>'caption', m.content->>'transcription', '') ILIKE %s
                )
            )"""
        )
        params.extend([pattern] * 6)
    sql = "SELECT * FROM whatsapp_conversation"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY cat DESC LIMIT %s"
    params.append(safe_limit)
    return fetch_all(sql, tuple(params))


def list_by_client(client_id: str, limit: int = 10) -> list[dict]:
    return fetch_all(
        "SELECT * FROM whatsapp_conversation WHERE client_id = %s ORDER BY cat DESC LIMIT %s",
        (client_id, clamp_limit(limit)),
    )


def list_by_connection(connection_id: str, limit: int = 10) -> list[dict]:
    return fetch_all(
        "SELECT * FROM whatsapp_conversation WHERE connection_id = %s ORDER BY cat DESC LIMIT %s",
        (connection_id, clamp_limit(limit)),
    )
