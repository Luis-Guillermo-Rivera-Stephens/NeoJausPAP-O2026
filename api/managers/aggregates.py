"""Conteos cerrados para dashboards.

Entidades, dimensiones, métricas y filtros salen de listas blancas; el texto del
agente nunca llega al SQL. Una cubeta puede anidar otro conteo: cada nivel
anidado es UN solo GROUP BY (dimensiones del padre + la del hijo) que se reparte
entre las cubetas hermanas, no una query por cubeta.
"""

from typing import Optional

from api.managers._sql import fetch_all, fetch_one

TZ = "America/Mexico_City"
MAX_BUCKETS = 500
MAX_DIMS = 3  # raíz + dos niveles anidados

_STATUSES = {"new", "contacted", "active", "closed", "lost", "inactive", "archived"}
_DIRECTIONS = {"inbound", "outbound"}

# sql: FROM + joins. where: condición base. time: columna de `cat`.
# aliases: alias de tabla disponibles (deciden qué dimensiones y filtros aplican).
_ENTITIES = {
    "CRM_CLIENTS": {
        "sql": "FROM crm_clients c LEFT JOIN clients adv ON adv.uid = c.assigned_to",
        "where": "c.is_deleted = false",
        "time": "c.cat",
        "aliases": {"c", "adv"},
        "filters": {
            "agency_id": "c.agency_id",
            "client_status": "c.client_status::text",
            "client_id": "c.uid",
        },
    },
    "CONVERSATIONS": {
        "sql": """FROM whatsapp_conversation wc
            JOIN whatsapp_connection w ON w.uid = wc.connection_id
            JOIN crm_clients c ON c.uid = wc.client_id
            LEFT JOIN clients adv ON adv.uid = c.assigned_to""",
        "where": "c.is_deleted = false",
        "time": "wc.cat",
        "aliases": {"wc", "w", "c", "adv"},
        "filters": {
            "agency_id": "wc.agency_id",
            "client_status": "c.client_status::text",
            "connection_id": "wc.connection_id",
            "client_id": "wc.client_id",
        },
    },
    "MESSAGES": {
        "sql": """FROM whatsapp_message m
            JOIN whatsapp_conversation wc ON wc.uid = m.conversation_id
            JOIN whatsapp_connection w ON w.uid = wc.connection_id
            JOIN crm_clients c ON c.uid = wc.client_id
            LEFT JOIN clients adv ON adv.uid = c.assigned_to
            LEFT JOIN clients s ON s.uid = m.sent_by""",
        "where": "c.is_deleted = false",
        "time": "m.cat",
        "aliases": {"m", "wc", "w", "c", "adv", "s"},
        "filters": {
            "agency_id": "wc.agency_id",
            "client_status": "c.client_status::text",
            "direction": "m.direction",
            "connection_id": "wc.connection_id",
            "client_id": "wc.client_id",
        },
    },
    "CONNECTIONS": {
        "sql": "FROM whatsapp_connection w",
        "where": "true",
        "time": "w.cat",
        "aliases": {"w"},
        "filters": {"agency_id": "w.agency_id", "connection_id": "w.uid"},
    },
}

# alias, expresión de la etiqueta, expresión del id (None = la misma), WHERE extra.
_DIMS = {
    "CLIENT_STATUS": ("c", "c.client_status::text", None, None),
    "CLIENT_TYPE": ("c", "c.client_type::text", None, None),
    "LEAD_SOURCE": ("c", "c.lead_source", None, None),
    "LOST_REASON": ("c", "c.lost_reason::text", None, None),
    "IS_LOST": ("c", "CASE WHEN c.is_lost THEN 'perdidos' ELSE 'vigentes' END", None, None),
    "PREFERRED_CONTACT": ("c", "c.preferred_contact_method::text", None, None),
    "ADVISOR": ("adv", "adv.nickname", "adv.uid::text", None),
    "DIRECTION": ("m", "m.direction", None, None),
    "MESSAGE_TYPE": ("m", "m.message_type", None, None),
    "M_STATUS": ("m", "m.m_status", None, None),
    "ERROR_CODE": ("m", "m.error_code", None, "m.error_code IS NOT NULL"),
    "SENT_BY": ("s", "s.nickname", "s.uid::text", "m.sent_by IS NOT NULL"),
    "CONNECTION": ("w", "w.name", "w.uid::text", None),
    "CONVERSATION_CATEGORY": ("wc", "wc.conversation_category", None, None),
    "STATUS": ("w", "w.status", None, None),
    "IS_ACTIVE": ("w", "CASE WHEN w.is_active THEN 'activos' ELSE 'inactivos' END", None, None),
}
TIME_DIMS = ("DAY", "WEEK")

# unanswered: el último mensaje de la conversación lo escribió el contacto.
_LAST_MESSAGE = """LEFT JOIN LATERAL (
        SELECT m.direction FROM whatsapp_message m
        WHERE m.conversation_id = wc.uid ORDER BY m.cat DESC LIMIT 1
    ) last ON true"""


def _spec(entity: str) -> dict:
    spec = _ENTITIES.get(entity)
    if spec is None:
        raise ValueError(f"entity no permitida: {entity}")
    return spec


def _day(column: str) -> str:
    return f"to_char({column} AT TIME ZONE '{TZ}', 'YYYY-MM-DD')"


def _week(column: str) -> str:
    return f"to_char(date_trunc('week', {column} AT TIME ZONE '{TZ}'), 'YYYY-MM-DD')"


def _dim(entity: str, name: str) -> dict:
    spec = _spec(entity)
    if name in TIME_DIMS:
        column = spec["time"]
        expr = _day(column) if name == "DAY" else _week(column)
        return {"name": name, "alias": column.split(".")[0], "key": expr, "id": expr, "where": None}
    if name not in _DIMS:
        raise ValueError(f"dimensión no permitida: {name}")
    alias, key, ident, where = _DIMS[name]
    if alias not in spec["aliases"]:
        raise ValueError(f"{name} no aplica a {entity}")
    return {"name": name, "alias": alias, "key": key, "id": ident or key, "where": where}


def _metric(entity: str, metric: str) -> str:
    if metric == "COUNT":
        return "count(*)::int"
    if metric == "COUNT_DISTINCT_CLIENTS":
        if "c" not in _spec(entity)["aliases"]:
            raise ValueError(f"COUNT_DISTINCT_CLIENTS no aplica a {entity}")
        return "count(DISTINCT c.uid)::int"
    raise ValueError(f"metric no permitida: {metric}")


def _where(entity: str, filters: dict) -> tuple[list[str], list[object]]:
    spec = _spec(entity)
    clauses: list[str] = []
    params: list[object] = []
    for name, value in filters.items():
        if value is None:
            continue
        if name == "since":
            clauses.append(f"{spec['time']} >= %s")
        elif name == "until":
            clauses.append(f"{spec['time']} < %s")
        else:
            column = spec["filters"].get(name)
            if column is None:
                raise ValueError(f"{name} no aplica a {entity}")
            if name == "client_status" and value not in _STATUSES:
                raise ValueError(f"clientStatus no válido: {value}")
            if name == "direction" and value not in _DIRECTIONS:
                raise ValueError(f"direction no válida: {value}")
            clauses.append(f"{column} = %s")
        params.append(value)
    return clauses, params


def _query(
    entity: str,
    dims: list[dict],
    filters: dict,
    measures: dict[str, str],
    measure_params: tuple[object, ...] = (),
    extra_from: str = "",
    time_order: bool = False,
) -> list[dict]:
    """Un GROUP BY sobre todas las dimensiones (padre + hijo). Filas: i0,k0,i1,k1,...,medidas."""
    spec = _spec(entity)
    if len(dims) > MAX_DIMS:
        raise ValueError(f"máximo {MAX_DIMS} niveles de agrupación")
    for dim in dims:
        if dim["alias"] not in spec["aliases"]:
            raise ValueError(f"{dim['name']} no se puede cruzar con {entity}")

    select: list[str] = []
    group: list[str] = []
    for i, dim in enumerate(dims):
        select.append(f"coalesce({dim['id']}, 'sin_valor') AS i{i}")
        select.append(f"coalesce({dim['key']}, 'sin_valor') AS k{i}")
        group += [str(len(select) - 1), str(len(select))]
    select += [f"{expr} AS {name}" for name, expr in measures.items()]

    clauses, params = _where(entity, filters)
    where = [spec["where"], *clauses, *(d["where"] for d in dims if d["where"])]
    sql = f"SELECT {', '.join(select)} {spec['sql']} {extra_from} WHERE {' AND '.join(where)}"
    if group:
        sql += " GROUP BY " + ", ".join(group)
        last = len(dims) - 1
        order = [f"k{i}" for i in range(last)]
        order.append(f"k{last} ASC" if time_order or "n" not in measures else f"n DESC, k{last} ASC")
        sql += " ORDER BY " + ", ".join(order)
        if len(dims) == 1:
            sql += f" LIMIT {MAX_BUCKETS}"
    return fetch_all(sql, (*measure_params, *params))


def _range(column: str, since, until) -> tuple[str, list[object]]:
    parts: list[str] = []
    params: list[object] = []
    if since is not None:
        parts.append(f"{column} >= %s")
        params.append(since)
    if until is not None:
        parts.append(f"{column} < %s")
        params.append(until)
    return (" AND ".join(parts) or "true"), params


class Scope:
    """Lo que una cubeta hereda: entidad, dimensiones del padre, filtros y una caché
    compartida con sus hermanas. La raíz es un Scope sin dimensiones."""

    def __init__(self, entity: str, dims=(), filters=None, path=(), cache=None):
        self.entity = entity
        self.dims = list(dims)
        self.filters = dict(filters or {})
        self.path = tuple(path)
        self.cache = cache if cache is not None else {}

    def _merge(self, filters: dict) -> dict:
        merged = dict(self.filters)
        for name, value in filters.items():
            if value is None:
                continue
            if name in merged and merged[name] != value:
                raise ValueError(f"{name} contradice el filtro del nivel superior")
            merged[name] = value
        return merged

    def _rows(
        self, entity, child_dims, filters, measures,
        measure_params=(), extra_from="", time_order=False, strip_time=False,
    ):
        """Filas de esta cubeta. La query corre una vez para todas las hermanas."""
        merged = self._merge(filters)
        if strip_time:
            # kpis mete el rango en cada FILTER: no va en el WHERE.
            merged = {k: v for k, v in merged.items() if k not in ("since", "until")}
        sig = (
            entity,
            tuple(d["key"] for d in child_dims),
            tuple(sorted((k, str(v)) for k, v in merged.items())),
            tuple(measures.items()),
            tuple(str(p) for p in measure_params),
            extra_from,
        )
        if sig not in self.cache:
            rows = _query(entity, self.dims + child_dims, merged, measures, measure_params, extra_from, time_order)
            grouped: dict[tuple, list[dict]] = {}
            width = len(self.dims)
            for row in rows:
                grouped.setdefault(tuple(row[f"i{i}"] for i in range(width)), []).append(row)
            self.cache[sig] = (grouped, merged, {})
        grouped, merged, child_cache = self.cache[sig]
        return grouped.get(self.path, [])[:MAX_BUCKETS], merged, child_cache

    def _bucket(self, entity, dim, row, merged, child_cache) -> dict:
        level = len(self.dims)
        scope = Scope(entity, self.dims + [dim], merged, self.path + (row[f"i{level}"],), child_cache)
        return {**row, "key": row[f"k{level}"], "scope": scope}

    def count(self, entity: Optional[str] = None, metric: str = "COUNT", **filters) -> int:
        entity = entity or self.entity
        rows, _, _ = self._rows(entity, [], filters, {"n": _metric(entity, metric)})
        return rows[0]["n"] if rows else 0

    def count_by(self, by: str, entity: Optional[str] = None, metric: str = "COUNT", **filters) -> list[dict]:
        if by in TIME_DIMS:
            raise ValueError("DAY y WEEK van en countOverTime")
        return self._series(by, entity, metric, filters, time_order=False)

    def count_over_time(self, by: str, entity: Optional[str] = None, metric: str = "COUNT", **filters) -> list[dict]:
        if by not in TIME_DIMS:
            raise ValueError("countOverTime solo acepta DAY o WEEK")
        return self._series(by, entity, metric, filters, time_order=True)

    def _series(self, by, entity, metric, filters, time_order) -> list[dict]:
        entity = entity or self.entity
        dim = _dim(entity, by)
        rows, merged, child_cache = self._rows(entity, [dim], filters, {"n": _metric(entity, metric)}, time_order=time_order)
        return [self._bucket(entity, dim, row, merged, child_cache) for row in rows]

    def count_compare(self, by: str = "NONE", **filters) -> list[dict]:
        """Solo mensajes: entrantes, salientes, total y contactos distintos que escribieron."""
        entity = "MESSAGES"
        measures = {
            "inbound": "(count(*) FILTER (WHERE m.direction = 'inbound'))::int",
            "outbound": "(count(*) FILTER (WHERE m.direction = 'outbound'))::int",
            "n": "count(*)::int",
            "usuarios": "(count(DISTINCT c.uid) FILTER (WHERE m.direction = 'inbound'))::int",
        }
        if by == "NONE":
            rows, merged, child_cache = self._rows(entity, [], filters, measures)
            row = rows[0] if rows else {"inbound": 0, "outbound": 0, "n": 0, "usuarios": 0}
            return [{**row, "key": "total", "scope": Scope(entity, self.dims, merged, self.path, child_cache)}]
        if by not in (*TIME_DIMS, "CONNECTION"):
            raise ValueError("countCompare acepta NONE, DAY, WEEK o CONNECTION")
        dim = _dim(entity, by)
        rows, merged, child_cache = self._rows(entity, [dim], filters, measures, time_order=by in TIME_DIMS)
        return [self._bucket(entity, dim, row, merged, child_cache) for row in rows]

    def kpis(self, **filters) -> dict:
        """Tabla de indicadores. None = ese indicador no aplica a este corte."""
        merged = self._merge(filters)
        since, until = merged.get("since"), merged.get("until")
        out: dict[str, Optional[int]] = {}

        def block(entity: str, measures: dict[str, tuple[str, list[object]]], extra_from: str = "") -> None:
            exprs = {name: f"({expr})::int" for name, (expr, _) in measures.items()}
            params = tuple(p for _, ps in measures.values() for p in ps)
            try:
                rows, _, _ = self._rows(entity, [], filters, exprs, params, extra_from, strip_time=True)
            except ValueError:
                rows = []
            row = rows[0] if rows else {}
            for name in measures:
                out[name] = row.get(name)

        cat, cat_p = _range("c.cat", since, until)
        lost, lost_p = _range("c.lost_at", since, until)
        block("CRM_CLIENTS", {
            "clients": (f"count(*) FILTER (WHERE {cat})", cat_p),
            "lost": (f"count(*) FILTER (WHERE c.is_lost AND {lost})", lost_p),
        })
        conv, conv_p = _range("wc.cat", since, until)
        block("CONVERSATIONS", {
            "conversations": (f"count(*) FILTER (WHERE {conv})", conv_p),
            "open_windows": ("count(*) FILTER (WHERE wc.window_expires_at > now())", []),
            "unanswered": ("count(*) FILTER (WHERE last.direction = 'inbound')", []),
        }, extra_from=_LAST_MESSAGE)
        msg, msg_p = _range("m.cat", since, until)
        block("MESSAGES", {
            "messages": (f"count(*) FILTER (WHERE {msg})", msg_p),
            "inbound": (f"count(*) FILTER (WHERE {msg} AND m.direction = 'inbound')", msg_p),
            "outbound": (f"count(*) FILTER (WHERE {msg} AND m.direction = 'outbound')", msg_p),
            "con_mensaje": (f"count(DISTINCT c.uid) FILTER (WHERE {msg})", msg_p),
            "usuarios": (f"count(DISTINCT c.uid) FILTER (WHERE {msg} AND m.direction = 'inbound')", msg_p),
        })
        block("CONNECTIONS", {"connections": ("count(*) FILTER (WHERE w.is_active)", [])})

        # Agencias y asesores son inventario: solo en la raíz, solo por agencia.
        out["agencies"] = out["advisors"] = None
        if not self.dims:
            agency = merged.get("agency_id")
            where, params = (" AND uid = %s", (agency,)) if agency else ("", ())
            row = fetch_one(f"SELECT count(*)::int AS n FROM real_state_agencies WHERE is_active{where}", params)
            out["agencies"] = row["n"] if row else 0
            where, params = (" WHERE agency_id = %s", (agency,)) if agency else ("", ())
            row = fetch_one(f"SELECT count(*)::int AS n FROM clients{where}", params)
            out["advisors"] = row["n"] if row else 0
        return out
