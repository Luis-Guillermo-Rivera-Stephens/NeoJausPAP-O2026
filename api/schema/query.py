"""Queries raíz que el agente puede pedir a GraphQL."""

from typing import Optional

import strawberry
from psycopg.rows import dict_row

from api.db.db import get_connection
from api.schema.whatsapp import (
    Agency,
    Advisor,
    Conversation,
    CrmClient,
    WhatsappConnection,
    _advisor_from_row,
    _agency_from_row,
    _connection_from_row,
    _conversation_from_row,
    _crm_client_from_row,
)


def _fetch_all(sql: str, params: tuple[object, ...] = ()) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def _fetch_one(sql: str, params: tuple[object, ...]) -> Optional[dict]:
    rows = _fetch_all(sql, params)
    return rows[0] if rows else None


@strawberry.type
class Query:
    @strawberry.field
    def agencies(self, active_only: bool = True) -> list[Agency]:
        sql = "SELECT * FROM real_state_agencies"
        if active_only:
            sql += " WHERE is_active = true"
        return [_agency_from_row(row) for row in _fetch_all(sql + " ORDER BY name")]

    @strawberry.field
    def agency(self, uid: strawberry.ID) -> Optional[Agency]:
        row = _fetch_one("SELECT * FROM real_state_agencies WHERE uid = %s", (str(uid),))
        return _agency_from_row(row) if row else None

    @strawberry.field
    def advisors(self) -> list[Advisor]:
        return [_advisor_from_row(row) for row in _fetch_all("SELECT * FROM clients ORDER BY nickname")]

    @strawberry.field
    def crm_clients(
        self, agency_id: Optional[strawberry.ID] = None, limit: int = 50
    ) -> list[CrmClient]:
        safe_limit = max(1, min(limit, 200))
        sql = "SELECT * FROM crm_clients WHERE is_deleted = false"
        params: tuple[object, ...] = ()
        if agency_id is not None:
            sql += " AND agency_id = %s"
            params = (str(agency_id),)
        rows = _fetch_all(sql + " ORDER BY cat DESC LIMIT %s", (*params, safe_limit))
        return [_crm_client_from_row(row) for row in rows]

    @strawberry.field
    def crm_client(self, uid: strawberry.ID) -> Optional[CrmClient]:
        row = _fetch_one("SELECT * FROM crm_clients WHERE uid = %s AND is_deleted = false", (str(uid),))
        return _crm_client_from_row(row) if row else None

    @strawberry.field
    def connections(self, agency_id: Optional[strawberry.ID] = None) -> list[WhatsappConnection]:
        sql = "SELECT * FROM whatsapp_connection"
        params: tuple[object, ...] = ()
        if agency_id is not None:
            sql += " WHERE agency_id = %s"
            params = (str(agency_id),)
        return [_connection_from_row(row) for row in _fetch_all(sql + " ORDER BY name", params)]

    @strawberry.field
    def conversations(
        self,
        connection_id: Optional[strawberry.ID] = None,
        client_id: Optional[strawberry.ID] = None,
        limit: int = 50,
    ) -> list[Conversation]:
        safe_limit = max(1, min(limit, 200))
        clauses: list[str] = []
        params: list[object] = []
        if connection_id is not None:
            clauses.append("connection_id = %s")
            params.append(str(connection_id))
        if client_id is not None:
            clauses.append("client_id = %s")
            params.append(str(client_id))
        sql = "SELECT * FROM whatsapp_conversation"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY cat DESC LIMIT %s"
        params.append(safe_limit)
        return [_conversation_from_row(row) for row in _fetch_all(sql, tuple(params))]
