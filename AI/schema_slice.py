"""Catálogo GraphQL minificado por ruta de Jev. Sin ruta: SDL completo."""

_FILTERS = (
    "filtros: since until agencyId connectionId clientId advisorId "
    "(uids) clientStatus direction. since/until ISO; until exclusivo. "
    "direction solo \"inbound\"|\"outbound\"."
)
_ENTITY = "entity: CRM_CLIENTS | MESSAGES | CONVERSATIONS | CONNECTIONS"
_METRIC = "metric: COUNT | COUNT_DISTINCT_CLIENTS"
_BUCKET = "Bucket { key n }"
_KPIS = (
    "Kpis { agencies advisors clients lost connections conversations "
    "openWindows unanswered messages inbound outbound conMensaje usuarios }"
)
_DIM = (
    "CountDim: CLIENT_STATUS CLIENT_TYPE LEAD_SOURCE LOST_REASON IS_LOST "
    "PREFERRED_CONTACT ADVISOR DIRECTION MESSAGE_TYPE M_STATUS ERROR_CODE "
    "SENT_BY CONNECTION CONVERSATION_CATEGORY STATUS IS_ACTIVE"
)
_TIME = "TimeDim: DAY | WEEK | MONTH"
_COMPARE = "CompareDim: NONE | DAY | WEEK | MONTH | CONNECTION"
_COMPARE_BUCKET = "CompareBucket { key inbound outbound n usuarios }"

_KPI = f"""\
count(entity, metric, {_FILTERS}): Int
kpis({_FILTERS} sin direction): {_KPIS}
{_ENTITY}
{_METRIC}
"""

_CATEGORIAS = f"""\
countBy(by, entity, metric, {_FILTERS}): [{_BUCKET}]
{_DIM}
{_ENTITY}
{_METRIC}
"""

_TENDENCIA = f"""\
countOverTime(by, entity, metric, {_FILTERS}): [{_BUCKET}]
{_TIME}
{_ENTITY}
{_METRIC}
"""

_COMPARATIVA = f"""\
countCompare(by, {_FILTERS} sin direction): [{_COMPARE_BUCKET}]
{_COMPARE}
"""

_COUNTS = "\n".join((_KPI, _CATEGORIAS, _TENDENCIA, _COMPARATIVA))

_DASHBOARD = {
    "kpi": _KPI,
    "categorias": _CATEGORIAS,
    "tendencia": _TENDENCIA,
    "comparativa": _COMPARATIVA,
    "reporte": _COUNTS,
}

_CRM = (
    "CrmClient { uid firstName firstLastName preferredName primaryEmail "
    "primaryPhone phoneCountryCode clientStatus waId waProfileName cat agencyId "
    "agency { uid isActive } assignedTo { uid nickname } }"
)
_TOPICS = (
    "topics(q, limit, minScore): [KeyTopic { uid name episodes(limit) { "
    "uid summary windowFrom windowTo conversation { uid conversationCategory "
    "client { uid firstName firstLastName preferredName clientStatus primaryPhone } } } }]"
)

_DATOS = f"""\
advisors: [Advisor {{ uid nickname firstName firstLastName }}]
crmClients(agencyId, limit, q, clientStatus, advisorId): [{_CRM}]
crmClient(uid): {_CRM}
connections(agencyId): [WhatsappConnection {{ uid phoneE164 name isActive agencyId }}]
conversations(connectionId, clientId, limit, q, conversationCategory): [Conversation {{
  uid agencyId conversationCategory windowExpiresAt lastReadAt cat
  client {{ uid firstName firstLastName preferredName clientStatus primaryPhone }}
  connection {{ uid phoneE164 name }}
  messages(limit, q) {{ uid direction messageType body mStatus cat }}
  episodes(limit, q) {{ uid summary windowFrom windowTo }}
}}]
{_TOPICS}
"""

_ESTATUS = f"""\
buscarEstado(q, clientId, limit): [EstadoHit {{
  clientId source conversationId clientName clientStatus text cat windowFrom windowTo
}}]
crmClient(uid): {_CRM}
{_TOPICS}
"""

_MEMORIA = """\
memories(q, limit, before): [MemoryWindow { uid windowFrom windowTo summary }]
"""

_ROOT = {
    "datos": _DATOS,
    "estatus": _ESTATUS,
    "memoria": _MEMORIA,
}


def _body(decisions: dict) -> str:
    route = decisions["ruta"]
    if route == "dashboard":
        kind = decisions.get("kind")
        return _DASHBOARD.get(kind) or _COUNTS
    return _ROOT[route]


def schema_for_prompt(decisions: dict | None) -> str:
    """Slice minificado si hay ruta conocida; si no, SDL completo."""
    from api.schema.schema import schema

    full = schema.as_str()
    route = (decisions or {}).get("ruta")
    kind = (decisions or {}).get("kind") or "-"
    if route not in ("dashboard", "datos", "estatus", "memoria"):
        text = "Schema GraphQL exacto:\n" + full
        print(f"[SLICE] ruta=none kind={kind} chars={len(text)} full={len(full)}")
        return text
    text = "Schema GraphQL (slice):\n" + _body(decisions)
    print(f"[SLICE] ruta={route} kind={kind} chars={len(text)} full={len(full)}")
    return text


if __name__ == "__main__":
    from api.schema.schema import schema

    full = schema.as_str()
    cases = (
        ({"ruta": "dashboard", "kind": "kpi"}, "kpis"),
        ({"ruta": "dashboard", "kind": "categorias"}, "countBy"),
        ({"ruta": "dashboard", "kind": "tendencia"}, "countOverTime"),
        ({"ruta": "dashboard", "kind": "comparativa"}, "countCompare"),
        ({"ruta": "dashboard", "kind": "reporte"}, "countBy"),
        ({"ruta": "dashboard"}, "kpis"),
        ({"ruta": "datos"}, "crmClients"),
        ({"ruta": "estatus"}, "buscarEstado"),
        ({"ruta": "memoria"}, "memories"),
    )
    for decisions, needle in cases:
        text = schema_for_prompt(decisions)
        assert needle in text, (decisions, needle)
        assert len(text) < len(full), (decisions, len(text), len(full))
    exact = schema_for_prompt(None)
    assert exact.startswith("Schema GraphQL exacto:")
    assert len(exact) > len(full)
    print("ok")
