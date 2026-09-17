"""Tipos y resolvers Strawberry para el dominio inmobiliario/WhatsApp."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from psycopg.rows import dict_row
from strawberry.scalars import JSON

from api.db.db import get_connection


def _one(sql: str, params: tuple[object, ...]) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def _many(sql: str, params: tuple[object, ...] = ()) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


@strawberry.type
class Agency:
    uid: strawberry.ID
    name: str
    timezone: str
    is_active: bool
    cat: datetime
    uat: datetime

    @strawberry.field
    def connections(self) -> list[Annotated["WhatsappConnection", strawberry.lazy("api.schema.whatsapp")]]:
        rows = _many("SELECT * FROM whatsapp_connection WHERE agency_id = %s ORDER BY name", (str(self.uid),))
        return [_connection_from_row(row) for row in rows]


@strawberry.type
class Advisor:
    uid: strawberry.ID
    nickname: str
    first_name: Optional[str]
    first_last_name: Optional[str]
    email: Optional[str]
    phone_number: Optional[str]


@strawberry.type
class CrmClient:
    uid: strawberry.ID
    first_name: str
    first_last_name: Optional[str]
    preferred_name: Optional[str]
    primary_email: Optional[str]
    primary_phone: Optional[str]
    phone_country_code: str
    preferred_contact_method: Optional[str]
    client_status: Optional[str]
    client_type: Optional[str]
    lead_source: Optional[str]
    tags: list[str]
    comments: Optional[str]
    wa_id: Optional[str]
    wa_profile_name: Optional[str]
    is_lost: bool
    lost_reason: Optional[str]
    lost_at: Optional[datetime]
    cat: datetime
    _agency_id: strawberry.Private[str]
    _assigned_to: strawberry.Private[str]

    @strawberry.field
    def agency(self) -> Optional[Annotated[Agency, strawberry.lazy("api.schema.whatsapp")]]:
        row = _one("SELECT * FROM real_state_agencies WHERE uid = %s", (self._agency_id,))
        return _agency_from_row(row) if row else None

    @strawberry.field
    def assigned_to(self) -> Optional[Annotated[Advisor, strawberry.lazy("api.schema.whatsapp")]]:
        row = _one("SELECT * FROM clients WHERE uid = %s", (self._assigned_to,))
        return _advisor_from_row(row) if row else None

    @strawberry.field
    def conversations(self) -> list[Annotated["Conversation", strawberry.lazy("api.schema.whatsapp")]]:
        rows = _many("SELECT * FROM whatsapp_conversation WHERE client_id = %s ORDER BY cat DESC", (str(self.uid),))
        return [_conversation_from_row(row) for row in rows]


@strawberry.type
class WhatsappConnection:
    uid: strawberry.ID
    phone_e164: Optional[str]
    display_phone: Optional[str]
    name: Optional[str]
    status: str
    is_active: bool
    cat: datetime
    _agency_id: strawberry.Private[str]

    @strawberry.field
    def conversations(self) -> list[Annotated["Conversation", strawberry.lazy("api.schema.whatsapp")]]:
        rows = _many("SELECT * FROM whatsapp_conversation WHERE connection_id = %s ORDER BY cat DESC", (str(self.uid),))
        return [_conversation_from_row(row) for row in rows]


@strawberry.type
class Conversation:
    uid: strawberry.ID
    conversation_category: Optional[str]
    window_expires_at: Optional[datetime]
    last_read_at: Optional[datetime]
    cat: datetime
    _client_id: strawberry.Private[str]
    _connection_id: strawberry.Private[str]

    @strawberry.field
    def client(self) -> Optional[Annotated[CrmClient, strawberry.lazy("api.schema.whatsapp")]]:
        row = _one("SELECT * FROM crm_clients WHERE uid = %s", (self._client_id,))
        return _crm_client_from_row(row) if row else None

    @strawberry.field
    def connection(self) -> Optional[Annotated[WhatsappConnection, strawberry.lazy("api.schema.whatsapp")]]:
        row = _one("SELECT * FROM whatsapp_connection WHERE uid = %s", (self._connection_id,))
        return _connection_from_row(row) if row else None

    @strawberry.field
    def messages(self, limit: int = 50) -> list[Annotated["Message", strawberry.lazy("api.schema.whatsapp")]]:
        safe_limit = max(1, min(limit, 200))
        rows = _many("SELECT * FROM whatsapp_message WHERE conversation_id = %s ORDER BY cat DESC LIMIT %s", (str(self.uid), safe_limit))
        return [_message_from_row(row) for row in rows]

    @strawberry.field
    def episodes(self) -> list[Annotated["ConversationEpisode", strawberry.lazy("api.schema.whatsapp")]]:
        rows = _many("SELECT * FROM whatsapp_conversation_episode WHERE conversation_id = %s ORDER BY window_to DESC", (str(self.uid),))
        return [_episode_from_row(row) for row in rows]


@strawberry.type
class Message:
    uid: strawberry.ID
    direction: str
    message_type: Optional[str]
    content: Optional[JSON]
    body: Optional[str]
    m_status: Optional[str]
    error_code: Optional[str]
    wamid: Optional[str]
    cat: datetime


@strawberry.type
class ConversationEpisode:
    uid: strawberry.ID
    window_from: datetime
    window_to: datetime
    summary: str
    key_topics: JSON
    model: str
    cost_usd_micros: int
    cat: datetime


def _agency_from_row(row: dict) -> Agency:
    return Agency(uid=str(row["uid"]), name=row["name"], timezone=row["timezone"], is_active=row["is_active"], cat=row["cat"], uat=row["uat"])


def _advisor_from_row(row: dict) -> Advisor:
    return Advisor(uid=str(row["uid"]), nickname=row["nickname"], first_name=row["first_name"], first_last_name=row["first_last_name"], email=row["email"], phone_number=row["phone_number"])


def _crm_client_from_row(row: dict) -> CrmClient:
    return CrmClient(uid=str(row["uid"]), first_name=row["first_name"], first_last_name=row["first_last_name"], preferred_name=row["preferred_name"], primary_email=row["primary_email"], primary_phone=row["primary_phone"], phone_country_code=row["phone_country_code"], preferred_contact_method=row["preferred_contact_method"], client_status=row["client_status"], client_type=row["client_type"], lead_source=row["lead_source"], tags=row["tags"] or [], comments=row["comments"], wa_id=row["wa_id"], wa_profile_name=row["wa_profile_name"], is_lost=row["is_lost"], lost_reason=row["lost_reason"], lost_at=row["lost_at"], cat=row["cat"], _agency_id=str(row["agency_id"]), _assigned_to=str(row["assigned_to"]))


def _connection_from_row(row: dict) -> WhatsappConnection:
    return WhatsappConnection(uid=str(row["uid"]), phone_e164=row["phone_e164"], display_phone=row["display_phone"], name=row["name"], status=row["status"], is_active=row["is_active"], cat=row["cat"], _agency_id=str(row["agency_id"]))


def _conversation_from_row(row: dict) -> Conversation:
    return Conversation(uid=str(row["uid"]), conversation_category=row["conversation_category"], window_expires_at=row["window_expires_at"], last_read_at=row["last_read_at"], cat=row["cat"], _client_id=str(row["client_id"]), _connection_id=str(row["connection_id"]))


def _message_from_row(row: dict) -> Message:
    content = row["content"]
    body = content.get("body") if isinstance(content, dict) else None
    return Message(uid=str(row["uid"]), direction=row["direction"], message_type=row["message_type"], content=content, body=body, m_status=row["m_status"], error_code=row["error_code"], wamid=row["wamid"], cat=row["cat"])


def _episode_from_row(row: dict) -> ConversationEpisode:
    return ConversationEpisode(uid=str(row["uid"]), window_from=row["window_from"], window_to=row["window_to"], summary=row["summary"], key_topics=row["key_topics"], model=row["model"], cost_usd_micros=row["cost_usd_micros"], cat=row["cat"])
