"""Tipos y resolvers Strawberry: superficie mínima para el agente."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

import strawberry
from strawberry.scalars import JSON

from api.managers import advisors as advisors_mgr
from api.managers import agencies as agencies_mgr
from api.managers import connections as connections_mgr
from api.managers import conversations as conversations_mgr
from api.managers import crm_clients as crm_mgr
from api.managers import episodes as episodes_mgr
from api.managers import messages as messages_mgr


@strawberry.type
class Agency:
    uid: strawberry.ID
    is_active: bool


@strawberry.type
class Advisor:
    uid: strawberry.ID
    nickname: str
    first_name: Optional[str]
    first_last_name: Optional[str]
    email: Optional[str]
    phone_number: Optional[str]
    agency_id: Optional[strawberry.ID]


@strawberry.type
class CrmClient:
    uid: strawberry.ID
    first_name: str
    first_last_name: Optional[str]
    preferred_name: Optional[str]
    primary_email: Optional[str]
    primary_phone: Optional[str]
    phone_country_code: str
    client_status: Optional[str]
    wa_id: Optional[str]
    wa_profile_name: Optional[str]
    cat: datetime
    agency_id: strawberry.ID
    _assigned_to: strawberry.Private[str]

    @strawberry.field
    def agency(self) -> Optional[Annotated[Agency, strawberry.lazy("api.schema.whatsapp")]]:
        row = agencies_mgr.get_agency(str(self.agency_id))
        return _agency_from_row(row) if row else None

    @strawberry.field
    def assigned_to(self) -> Optional[Annotated[Advisor, strawberry.lazy("api.schema.whatsapp")]]:
        row = advisors_mgr.get_advisor(self._assigned_to)
        return _advisor_from_row(row) if row else None

    @strawberry.field
    def conversations(
        self, limit: int = 10
    ) -> list[Annotated["Conversation", strawberry.lazy("api.schema.whatsapp")]]:
        rows = conversations_mgr.list_by_client(str(self.uid), limit)
        return [_conversation_from_row(row) for row in rows]


@strawberry.type
class WhatsappConnection:
    uid: strawberry.ID
    phone_e164: Optional[str]
    name: Optional[str]
    is_active: bool
    agency_id: strawberry.ID

    @strawberry.field
    def conversations(
        self, limit: int = 10
    ) -> list[Annotated["Conversation", strawberry.lazy("api.schema.whatsapp")]]:
        rows = conversations_mgr.list_by_connection(str(self.uid), limit)
        return [_conversation_from_row(row) for row in rows]


@strawberry.type
class Conversation:
    uid: strawberry.ID
    agency_id: strawberry.ID
    conversation_category: Optional[str]
    window_expires_at: Optional[datetime]
    last_read_at: Optional[datetime]
    cat: datetime
    _client_id: strawberry.Private[str]
    _connection_id: strawberry.Private[str]

    @strawberry.field
    def client(self) -> Optional[Annotated[CrmClient, strawberry.lazy("api.schema.whatsapp")]]:
        row = crm_mgr.get_crm_client(self._client_id)
        return _crm_client_from_row(row) if row else None

    @strawberry.field
    def connection(self) -> Optional[Annotated[WhatsappConnection, strawberry.lazy("api.schema.whatsapp")]]:
        row = connections_mgr.get_connection(self._connection_id)
        return _connection_from_row(row) if row else None

    @strawberry.field
    def messages(
        self, limit: int = 10, q: Optional[str] = None
    ) -> list[Annotated["Message", strawberry.lazy("api.schema.whatsapp")]]:
        rows = messages_mgr.list_by_conversation(str(self.uid), limit, q)
        return [_message_from_row(row) for row in rows]

    @strawberry.field
    def episodes(
        self, limit: int = 5, q: Optional[str] = None
    ) -> list[Annotated["ConversationEpisode", strawberry.lazy("api.schema.whatsapp")]]:
        rows = episodes_mgr.list_by_conversation(str(self.uid), limit, q)
        return [_episode_from_row(row) for row in rows]


@strawberry.type
class Message:
    uid: strawberry.ID
    direction: str
    message_type: Optional[str]
    body: Optional[str]
    m_status: Optional[str]
    cat: datetime


@strawberry.type
class EstadoHit:
    source: str
    conversation_id: strawberry.ID
    client_name: str
    client_status: Optional[str]
    text: str
    cat: datetime
    window_from: Optional[datetime]
    window_to: Optional[datetime]


@strawberry.type
class ConversationEpisode:
    uid: strawberry.ID
    window_from: datetime
    window_to: datetime
    summary: str
    key_topics: JSON
    cat: datetime


def _agency_from_row(row: dict) -> Agency:
    return Agency(uid=str(row["uid"]), is_active=row["is_active"])


def _advisor_from_row(row: dict) -> Advisor:
    agency_id = row.get("agency_id")
    return Advisor(
        uid=str(row["uid"]),
        nickname=row["nickname"],
        first_name=row["first_name"],
        first_last_name=row["first_last_name"],
        email=row["email"],
        phone_number=row["phone_number"],
        agency_id=str(agency_id) if agency_id else None,
    )


def _crm_client_from_row(row: dict) -> CrmClient:
    return CrmClient(
        uid=str(row["uid"]),
        first_name=row["first_name"],
        first_last_name=row["first_last_name"],
        preferred_name=row["preferred_name"],
        primary_email=row["primary_email"],
        primary_phone=row["primary_phone"],
        phone_country_code=row["phone_country_code"],
        client_status=row["client_status"],
        wa_id=row["wa_id"],
        wa_profile_name=row["wa_profile_name"],
        cat=row["cat"],
        agency_id=str(row["agency_id"]),
        _assigned_to=str(row["assigned_to"]),
    )


def _connection_from_row(row: dict) -> WhatsappConnection:
    return WhatsappConnection(
        uid=str(row["uid"]),
        phone_e164=row["phone_e164"],
        name=row["name"],
        is_active=row["is_active"],
        agency_id=str(row["agency_id"]),
    )


def _conversation_from_row(row: dict) -> Conversation:
    return Conversation(
        uid=str(row["uid"]),
        agency_id=str(row["agency_id"]),
        conversation_category=row["conversation_category"],
        window_expires_at=row["window_expires_at"],
        last_read_at=row["last_read_at"],
        cat=row["cat"],
        _client_id=str(row["client_id"]),
        _connection_id=str(row["connection_id"]),
    )


def _message_from_row(row: dict) -> Message:
    content = row["content"]
    body = content.get("body") if isinstance(content, dict) else None
    return Message(
        uid=str(row["uid"]),
        direction=row["direction"],
        message_type=row["message_type"],
        body=body,
        m_status=row["m_status"],
        cat=row["cat"],
    )


def _estado_from_row(row: dict) -> EstadoHit:
    return EstadoHit(
        source=row["source"],
        conversation_id=str(row["conversation_id"]),
        client_name=row["client_name"],
        client_status=row["client_status"],
        text=row["text"] or "",
        cat=row["cat"],
        window_from=row["window_from"],
        window_to=row["window_to"],
    )


def _episode_from_row(row: dict) -> ConversationEpisode:
    return ConversationEpisode(
        uid=str(row["uid"]),
        window_from=row["window_from"],
        window_to=row["window_to"],
        summary=row["summary"],
        key_topics=row["key_topics"],
        cat=row["cat"],
    )
