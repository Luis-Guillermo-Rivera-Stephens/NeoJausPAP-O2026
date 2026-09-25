"""Agregaciones cerradas. El GROUP BY sale de una lista blanca, no del texto del agente."""

from datetime import datetime
from typing import Optional

from api.managers._sql import fetch_all

_STATUSES = {"new", "contacted", "active", "closed", "lost", "inactive", "archived"}
_DIRECTIONS = {"inbound", "outbound"}

_FROM = {
    "CRM_CLIENTS": """
        FROM crm_clients c
        LEFT JOIN clients adv ON adv.uid = c.assigned_to
        WHERE c.is_deleted = false
    """,
    "MESSAGES": """
        FROM whatsapp_message m
        JOIN whatsapp_conversation wc ON wc.uid = m.conversation_id
        JOIN whatsapp_connection w ON w.uid = wc.connection_id
        JOIN crm_clients c ON c.uid = wc.client_id AND c.is_deleted = false
        WHERE true
    """,
    "CONVERSATIONS": """
        FROM whatsapp_conversation wc
        JOIN whatsapp_connection w ON w.uid = wc.connection_id
        JOIN crm_clients c ON c.uid = wc.client_id AND c.is_deleted = false
        WHERE true
    """,
}

_TIME = {
    "CRM_CLIENTS": "c.cat",
    "MESSAGES": "m.cat",
    "CONVERSATIONS": "wc.cat",
}

_METRIC = {
    "COUNT": "count(*)::int",
    "COUNT_DISTINCT_CLIENTS": "count(DISTINCT c.uid)::int",
}


def _day(column: str) -> str:
    return f"to_char({column} AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD')"


def _week(column: str) -> str:
    return (
        "to_char(date_trunc('week', "
        f"{column} AT TIME ZONE 'America/Mexico_City'), 'YYYY-MM-DD')"
    )


def _groups(entity: str) -> dict[str, Optional[str]]:
    column = _TIME[entity]
    common = {"NONE": None, "DAY": _day(column), "WEEK": _week(column), "CLIENT_STATUS": "c.client_status::text"}
    if entity == "CRM_CLIENTS":
        return {**common, "ADVISOR": "adv.nickname"}
    if entity == "MESSAGES":
        return {
            **common,
            "DIRECTION": "m.direction",
            "MESSAGE_TYPE": "m.message_type",
            "M_STATUS": "m.m_status",
            "CONNECTION": "w.name",
        }
    return {**common, "CONVERSATION_CATEGORY": "wc.conversation_category", "CONNECTION": "w.name"}


def aggregate(
    entity: str,
    metric: str = "COUNT",
    group_by: str = "NONE",
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[str] = None,
    client_status: Optional[str] = None,
    direction: Optional[str] = None,
    connection_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> list[dict]:
    if entity not in _FROM:
        raise ValueError(f"entity no permitida: {entity}")
    if metric not in _METRIC:
        raise ValueError(f"metric no permitida: {metric}")
    groups = _groups(entity)
    if group_by not in groups:
        raise ValueError(f"groupBy {group_by} no aplica a {entity}")
    if client_status and client_status not in _STATUSES:
        raise ValueError(f"clientStatus no válido: {client_status}")
    if direction and direction not in _DIRECTIONS:
        raise ValueError(f"direction no válida: {direction}")
    if direction and entity != "MESSAGES":
        raise ValueError("direction solo aplica a MESSAGES")
    if connection_id and entity == "CRM_CLIENTS":
        raise ValueError("connectionId no aplica a CRM_CLIENTS")

    expr = groups[group_by]
    key_sql = f"coalesce({expr}, 'sin_valor')" if expr else "'total'"
    sql = f"SELECT {key_sql} AS key, {_METRIC[metric]} AS n {_FROM[entity]}"
    params: list[object] = []
    time_col = _TIME[entity]

    if since is not None:
        sql += f" AND {time_col} >= %s"
        params.append(since)
    if until is not None:
        sql += f" AND {time_col} < %s"
        params.append(until)
    if agency_id:
        column = "c.agency_id" if entity == "CRM_CLIENTS" else "wc.agency_id"
        sql += f" AND {column} = %s"
        params.append(agency_id)
    if client_status:
        sql += " AND c.client_status::text = %s"
        params.append(client_status)
    if direction:
        sql += " AND m.direction = %s"
        params.append(direction)
    if connection_id:
        sql += " AND wc.connection_id = %s"
        params.append(connection_id)
    if client_id:
        column = "c.uid" if entity == "CRM_CLIENTS" else "wc.client_id"
        sql += f" AND {column} = %s"
        params.append(client_id)

    sql += " GROUP BY 1"
    if group_by in {"DAY", "WEEK"}:
        sql += " ORDER BY 1 ASC"
    else:
        sql += " ORDER BY n DESC, 1 ASC"
    sql += " LIMIT 120"
    return fetch_all(sql, tuple(params))
