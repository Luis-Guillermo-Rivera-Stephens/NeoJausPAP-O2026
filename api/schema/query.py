"""Queries raíz que el agente puede pedir a GraphQL."""

from datetime import datetime
from enum import Enum
from typing import Optional

import strawberry
from graphql import GraphQLError

from api.managers.aggregates import aggregate
from api.managers import agencies as agencies_mgr
from api.managers import advisors as advisors_mgr
from api.managers import connections as connections_mgr
from api.managers import conversations as conversations_mgr
from api.managers import crm_clients as crm_mgr
from api.managers import episodes as episodes_mgr
from api.schema.whatsapp import (
    Agency,
    Advisor,
    Conversation,
    CrmClient,
    EstadoHit,
    WhatsappConnection,
    _advisor_from_row,
    _agency_from_row,
    _connection_from_row,
    _conversation_from_row,
    _crm_client_from_row,
    _estado_from_row,
)


@strawberry.enum
class AggregateEntity(Enum):
    CRM_CLIENTS = "CRM_CLIENTS"
    MESSAGES = "MESSAGES"
    CONVERSATIONS = "CONVERSATIONS"


@strawberry.enum
class AggregateMetric(Enum):
    COUNT = "COUNT"
    COUNT_DISTINCT_CLIENTS = "COUNT_DISTINCT_CLIENTS"


@strawberry.enum
class AggregateGroup(Enum):
    NONE = "NONE"
    CLIENT_STATUS = "CLIENT_STATUS"
    DIRECTION = "DIRECTION"
    MESSAGE_TYPE = "MESSAGE_TYPE"
    M_STATUS = "M_STATUS"
    CONVERSATION_CATEGORY = "CONVERSATION_CATEGORY"
    DAY = "DAY"
    WEEK = "WEEK"
    ADVISOR = "ADVISOR"
    CONNECTION = "CONNECTION"


@strawberry.type
class AggregateBucket:
    key: str
    n: int


@strawberry.type
class Query:
    @strawberry.field
    def agencies(self, active_only: bool = True) -> list[Agency]:
        return [_agency_from_row(row) for row in agencies_mgr.list_agencies(active_only)]

    @strawberry.field
    def agency(self, uid: strawberry.ID) -> Optional[Agency]:
        row = agencies_mgr.get_agency(str(uid))
        return _agency_from_row(row) if row else None

    @strawberry.field
    def advisors(self) -> list[Advisor]:
        return [_advisor_from_row(row) for row in advisors_mgr.list_advisors()]

    @strawberry.field
    def crm_clients(
        self,
        agency_id: Optional[strawberry.ID] = None,
        limit: int = 10,
        q: Optional[str] = None,
        client_status: Optional[str] = None,
    ) -> list[CrmClient]:
        rows = crm_mgr.list_crm_clients(
            str(agency_id) if agency_id is not None else None,
            limit,
            q,
            client_status,
        )
        return [_crm_client_from_row(row) for row in rows]

    @strawberry.field
    def crm_client(self, uid: strawberry.ID) -> Optional[CrmClient]:
        row = crm_mgr.get_crm_client(str(uid))
        return _crm_client_from_row(row) if row else None

    @strawberry.field
    def connections(self, agency_id: Optional[strawberry.ID] = None) -> list[WhatsappConnection]:
        rows = connections_mgr.list_connections(str(agency_id) if agency_id is not None else None)
        return [_connection_from_row(row) for row in rows]

    @strawberry.field
    def conversations(
        self,
        connection_id: Optional[strawberry.ID] = None,
        client_id: Optional[strawberry.ID] = None,
        limit: int = 10,
        q: Optional[str] = None,
    ) -> list[Conversation]:
        rows = conversations_mgr.list_conversations(
            str(connection_id) if connection_id is not None else None,
            str(client_id) if client_id is not None else None,
            limit,
            q,
        )
        return [_conversation_from_row(row) for row in rows]

    @strawberry.field
    def buscar_estado(
        self,
        q: str,
        client_id: Optional[strawberry.ID] = None,
        limit: int = 10,
    ) -> list[EstadoHit]:
        rows = episodes_mgr.buscar_estado(
            q,
            str(client_id) if client_id is not None else None,
            limit,
        )
        return [_estado_from_row(row) for row in rows]

    @strawberry.field
    def agregado(
        self,
        entity: AggregateEntity,
        metric: AggregateMetric = AggregateMetric.COUNT,
        group_by: AggregateGroup = AggregateGroup.NONE,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        agency_id: Optional[strawberry.ID] = None,
        client_status: Optional[str] = None,
        direction: Optional[str] = None,
        connection_id: Optional[strawberry.ID] = None,
        client_id: Optional[strawberry.ID] = None,
    ) -> list[AggregateBucket]:
        try:
            rows = aggregate(
                entity.name,
                metric.name,
                group_by.name,
                since,
                until,
                str(agency_id) if agency_id is not None else None,
                client_status,
                direction,
                str(connection_id) if connection_id is not None else None,
                str(client_id) if client_id is not None else None,
            )
        except ValueError as error:
            raise GraphQLError(str(error)) from error
        return [AggregateBucket(key=row["key"], n=row["n"]) for row in rows]
