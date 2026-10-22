"""Conteos para dashboards: count, kpis, countBy, countOverTime, countCompare.

Los mismos cinco campos viven en la raíz y dentro de cada cubeta; una cubeta
acota a sus hijos. Los resolvers son funciones compartidas: en la raíz `root`
es None y la entidad es obligatoria; en una cubeta se hereda la del padre.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

import strawberry
from graphql import GraphQLError

from api.managers.aggregates import Scope


@strawberry.enum
class CountEntity(Enum):
    CRM_CLIENTS = "CRM_CLIENTS"
    MESSAGES = "MESSAGES"
    CONVERSATIONS = "CONVERSATIONS"
    CONNECTIONS = "CONNECTIONS"


@strawberry.enum
class CountMetric(Enum):
    COUNT = "COUNT"
    COUNT_DISTINCT_CLIENTS = "COUNT_DISTINCT_CLIENTS"


@strawberry.enum(description="Dimensión de countBy. Contactos: CLIENT_STATUS, CLIENT_TYPE, LEAD_SOURCE, LOST_REASON, IS_LOST, PREFERRED_CONTACT, ADVISOR. Mensajes: DIRECTION, MESSAGE_TYPE, M_STATUS, ERROR_CODE, SENT_BY, CONNECTION, CLIENT_STATUS. Conversaciones: CONVERSATION_CATEGORY, CONNECTION, CLIENT_STATUS. Números: STATUS, IS_ACTIVE.")
class CountDim(Enum):
    CLIENT_STATUS = "CLIENT_STATUS"
    CLIENT_TYPE = "CLIENT_TYPE"
    LEAD_SOURCE = "LEAD_SOURCE"
    LOST_REASON = "LOST_REASON"
    IS_LOST = "IS_LOST"
    PREFERRED_CONTACT = "PREFERRED_CONTACT"
    ADVISOR = "ADVISOR"
    DIRECTION = "DIRECTION"
    MESSAGE_TYPE = "MESSAGE_TYPE"
    M_STATUS = "M_STATUS"
    ERROR_CODE = "ERROR_CODE"
    SENT_BY = "SENT_BY"
    CONNECTION = "CONNECTION"
    CONVERSATION_CATEGORY = "CONVERSATION_CATEGORY"
    STATUS = "STATUS"
    IS_ACTIVE = "IS_ACTIVE"


@strawberry.enum
class TimeDim(Enum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"


@strawberry.enum
class CompareDim(Enum):
    NONE = "NONE"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    CONNECTION = "CONNECTION"


@strawberry.type(description="Indicadores. null = no aplica a este corte. openWindows y unanswered son estado de ahora.")
class Kpis:
    agencies: Optional[int]
    advisors: Optional[int]
    clients: Optional[int]
    lost: Optional[int]
    connections: Optional[int]
    conversations: Optional[int]
    open_windows: Optional[int]
    unanswered: Optional[int]
    messages: Optional[int]
    inbound: Optional[int]
    outbound: Optional[int]
    con_mensaje: Optional[int]
    usuarios: Optional[int]


def _uid(value, label: str):
    if value is None:
        return None
    text = str(value)
    try:
        UUID(text)
    except ValueError:
        raise ValueError(f"{label} tiene que ser un uid. '{text}' no lo es; búscalo antes.") from None
    return text


def _filters(since, until, agency_id, client_status, direction, connection_id, client_id, advisor_id=None) -> dict:
    return {
        "since": since,
        "until": until,
        "agency_id": _uid(agency_id, "agencyId"),
        "client_status": client_status,
        "direction": direction.lower() if isinstance(direction, str) else direction,
        "connection_id": _uid(connection_id, "connectionId"),
        "client_id": _uid(client_id, "clientId"),
        "advisor_id": _uid(advisor_id, "advisorId"),
    }


def _scope(root, entity: Optional[CountEntity], default: Optional[str] = None) -> tuple[Scope, Optional[str]]:
    name = entity.name if entity is not None else None
    if root is not None:
        return root._scope, name
    name = name or default
    if name is None:
        raise GraphQLError("entity es obligatoria en la raíz")
    return Scope(name), None


def _bucket(cls, row: dict):
    extra = {k: row[k] for k in ("inbound", "outbound", "usuarios")} if cls is CompareBucket else {}
    return cls(key=row["key"], n=row["n"], _scope=row["scope"], **extra)


def count(
    root: strawberry.Parent[Optional["Bucket"]],
    entity: Optional[CountEntity] = None,
    metric: CountMetric = CountMetric.COUNT,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[strawberry.ID] = None,
    client_status: Optional[str] = None,
    direction: Optional[str] = None,
    connection_id: Optional[strawberry.ID] = None,
    client_id: Optional[strawberry.ID] = None,
    advisor_id: Optional[strawberry.ID] = None,
) -> int:
    scope, name = _scope(root, entity)
    try:
        return scope.count(name, metric.name, **_filters(since, until, agency_id, client_status, direction, connection_id, client_id, advisor_id))
    except ValueError as error:
        raise GraphQLError(str(error)) from error


def count_by(
    root: strawberry.Parent[Optional["Bucket"]],
    by: CountDim,
    entity: Optional[CountEntity] = None,
    metric: CountMetric = CountMetric.COUNT,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[strawberry.ID] = None,
    client_status: Optional[str] = None,
    direction: Optional[str] = None,
    connection_id: Optional[strawberry.ID] = None,
    client_id: Optional[strawberry.ID] = None,
    advisor_id: Optional[strawberry.ID] = None,
) -> list["Bucket"]:
    scope, name = _scope(root, entity)
    try:
        rows = scope.count_by(by.name, name, metric.name, **_filters(since, until, agency_id, client_status, direction, connection_id, client_id, advisor_id))
    except ValueError as error:
        raise GraphQLError(str(error)) from error
    return [_bucket(Bucket, row) for row in rows]


def count_over_time(
    root: strawberry.Parent[Optional["Bucket"]],
    by: TimeDim,
    entity: Optional[CountEntity] = None,
    metric: CountMetric = CountMetric.COUNT,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[strawberry.ID] = None,
    client_status: Optional[str] = None,
    direction: Optional[str] = None,
    connection_id: Optional[strawberry.ID] = None,
    client_id: Optional[strawberry.ID] = None,
    advisor_id: Optional[strawberry.ID] = None,
) -> list["Bucket"]:
    scope, name = _scope(root, entity)
    try:
        rows = scope.count_over_time(by.name, name, metric.name, **_filters(since, until, agency_id, client_status, direction, connection_id, client_id, advisor_id))
    except ValueError as error:
        raise GraphQLError(str(error)) from error
    return [_bucket(Bucket, row) for row in rows]


def count_compare(
    root: strawberry.Parent[Optional["Bucket"]],
    by: CompareDim = CompareDim.NONE,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[strawberry.ID] = None,
    client_status: Optional[str] = None,
    connection_id: Optional[strawberry.ID] = None,
    client_id: Optional[strawberry.ID] = None,
    advisor_id: Optional[strawberry.ID] = None,
) -> list["CompareBucket"]:
    scope, _ = _scope(root, None, "MESSAGES")
    try:
        rows = scope.count_compare(by.name, **_filters(since, until, agency_id, client_status, None, connection_id, client_id, advisor_id))
    except ValueError as error:
        raise GraphQLError(str(error)) from error
    return [_bucket(CompareBucket, row) for row in rows]


def kpis(
    root: strawberry.Parent[Optional["Bucket"]],
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    agency_id: Optional[strawberry.ID] = None,
    client_status: Optional[str] = None,
    connection_id: Optional[strawberry.ID] = None,
    client_id: Optional[strawberry.ID] = None,
    advisor_id: Optional[strawberry.ID] = None,
) -> Kpis:
    scope, _ = _scope(root, None, "CRM_CLIENTS")
    try:
        data = scope.kpis(**_filters(since, until, agency_id, client_status, None, connection_id, client_id, advisor_id))
    except ValueError as error:
        raise GraphQLError(str(error)) from error
    return Kpis(**data)


_FIELDS = {
    "count": (count, "Un número. Todas las filas del filtro."),
    "kpis": (kpis, "Tabla de indicadores en una sola llamada."),
    "count_by": (count_by, "Todas las cubetas de una dimensión, de mayor a menor. Sin DAY/WEEK/MONTH."),
    "count_over_time": (count_over_time, "Serie completa por DAY, WEEK o MONTH, en orden cronológico."),
    "count_compare": (count_compare, "Solo mensajes: inbound, outbound, total y usuarios por NONE, DAY, WEEK, MONTH o CONNECTION."),
}


def field(name: str):
    """Campo nuevo con el resolver compartido. Query y Bucket declaran los mismos cinco."""
    resolver, description = _FIELDS[name]
    return strawberry.field(resolver=resolver, description=description)


@strawberry.type(description="Una cubeta. Sus conteos anidados ya vienen acotados a esta cubeta (hasta dos niveles bajo la raíz).")
class Bucket:
    key: str
    n: int
    _scope: strawberry.Private[Scope]
    count: int = field("count")
    kpis: Kpis = field("kpis")
    count_by: list["Bucket"] = field("count_by")
    count_over_time: list["Bucket"] = field("count_over_time")
    count_compare: list["CompareBucket"] = field("count_compare")


@strawberry.type(description="Cubeta de countCompare.")
class CompareBucket(Bucket):
    inbound: int
    outbound: int
    usuarios: int
