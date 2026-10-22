"""Una llamada a Jev antes del agente. Si no hay llave o falla, devuelve None."""

import re
from datetime import datetime, timedelta
from os import getenv
from zoneinfo import ZoneInfo

MX = ZoneInfo("America/Mexico_City")
THRESHOLD = 0.85
MODEL = "jev-latest"
# docs.typesafe.ai/models: se cobra la entrada. La salida no.
INPUT_USD_PER_MILLION = 0.042

ROUTES = ("datos", "dashboard", "estatus", "memoria")
PERIODS = (
    "hoy",
    "ayer",
    "esta_semana",
    "semana_pasada",
    "este_mes",
    "mes_pasado",
    "sin_fecha",
)
KINDS = ("kpi", "categorias", "tendencia", "comparativa", "reporte")
GRAPHIC = {
    "kpi": "bar",
    "categorias": "bar",
    "tendencia": "line",
    "comparativa": "stacked",
    "reporte": "bar",
}


def period_bounds(now: datetime, period: str) -> tuple[str, str] | None:
    """since y until (until exclusivo) en America/Mexico_City. None si no hay corte."""
    if period == "sin_fecha" or period not in PERIODS:
        return None
    local = now.astimezone(MX) if now.tzinfo else now.replace(tzinfo=MX)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "hoy":
        since, until = start, start + timedelta(days=1)
    elif period == "ayer":
        since, until = start - timedelta(days=1), start
    elif period == "esta_semana":
        monday = start - timedelta(days=start.weekday())
        since, until = monday, monday + timedelta(days=7)
    elif period == "semana_pasada":
        monday = start - timedelta(days=start.weekday())
        since, until = monday - timedelta(days=7), monday
    elif period == "este_mes":
        since = start.replace(day=1)
        until = (since + timedelta(days=32)).replace(day=1)
    else:
        this_month = start.replace(day=1)
        since = (this_month - timedelta(days=1)).replace(day=1)
        until = this_month
    return since.isoformat(timespec="seconds"), until.isoformat(timespec="seconds")


def _log_usage(response) -> None:
    usage = response.usage
    cost = usage.input_tokens * INPUT_USD_PER_MILLION / 1_000_000
    print(
        f"[JEV] tokens: input={usage.input_tokens} "
        f"output={usage.output_tokens} cost_usd={cost:.8f} model={response.model}"
    )


def _pick(answer, allowed: tuple[str, ...] | set[str]) -> str | None:
    if answer is None or answer.confidence < THRESHOLD or answer.choice not in allowed:
        return None
    return answer.choice


def match_advisor(text: str, rows: list[dict]) -> tuple[str, str] | None:
    """Un solo nickname presente en el texto. Cero o varios: None."""
    found: list[tuple[str, str]] = []
    for row in rows:
        nick = (row.get("nickname") or "").strip()
        if not nick:
            continue
        if re.search(rf"(?<!\w){re.escape(nick)}(?!\w)", text, re.IGNORECASE):
            found.append((nick, str(row["uid"])))
    if len(found) != 1:
        return None
    return found[0]


def advisor_in_text(text: str) -> tuple[str, str] | None:
    from api.managers import advisors as advisors_mgr

    return match_advisor(text, advisors_mgr.list_advisors())


def _rewrite(query: str, rows: list[dict]) -> str:
    rewritten = query
    for row in rows:
        nick = (row.get("nickname") or "").strip()
        if not nick:
            continue
        rewritten = re.sub(
            rf'(advisorId:\s*"){re.escape(nick)}(")',
            rf"\1{row['uid']}\2",
            rewritten,
            flags=re.IGNORECASE,
        )
    return rewritten


def rewrite_advisor_ids(query: str) -> str:
    """Si el modelo puso un nickname en advisorId, lo cambia por el uid."""
    from api.managers import advisors as advisors_mgr

    return _rewrite(query, advisors_mgr.list_advisors())


def _advisor_criteria() -> tuple[dict[str, str], dict[str, str]]:
    from api.managers import advisors as advisors_mgr

    criteria = {"ninguno": "No nombra a un asesor"}
    uids: dict[str, str] = {}
    for row in advisors_mgr.list_advisors():
        nickname = (row.get("nickname") or "").strip()
        if not nickname or nickname == "ninguno" or nickname in criteria:
            continue
        criteria[nickname] = "Asesor de la inmobiliaria"
        uids[nickname] = str(row["uid"])
    return criteria, uids


async def classify(message: str, now: datetime | None = None) -> dict | None:
    text = (message or "").strip()
    if not text or not getenv("TYPESAFE_API_KEY", "").strip():
        if text:
            print("[JEV] sin TYPESAFE_API_KEY")
        return None
    try:
        from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy

        advisor_criteria, advisor_uids = _advisor_criteria()
        questions = {
            "ruta": Choice(
                instructions="Qué tiene que hacer el sistema con este mensaje",
                criteria={
                    "datos": "Cifra, lista, contacto, conversación o mensaje concreto",
                    "dashboard": "Gráfica, KPI, tendencia, comparación o reporte visual",
                    "estatus": "Qué pasó, seguimiento o estado de un caso",
                    "memoria": "Algo dicho antes en este chat, no en WhatsApp",
                },
            ),
            "periodo": Choice(
                instructions="Qué rango de fechas pide. sin_fecha si no pide fechas",
                criteria={
                    "hoy": "El día de hoy",
                    "ayer": "El día anterior",
                    "esta_semana": "La semana en curso, de lunes a hoy",
                    "semana_pasada": "La semana anterior completa",
                    "este_mes": "El mes en curso",
                    "mes_pasado": "El mes anterior completo",
                    "sin_fecha": "No pide un rango de fechas",
                },
            ),
            "asesor": Choice(
                instructions="Qué asesor nombra. ninguno si no nombra a uno",
                criteria=advisor_criteria,
            ),
            "kind": Choice(
                instructions="Si pide una gráfica, de qué tipo. Si no pide gráfica, kpi",
                criteria={
                    "kpi": "Un número o un tablero de indicadores",
                    "categorias": "Reparto por estatus, asesor, tipo o fuente",
                    "tendencia": "Evolución por día o por semana",
                    "comparativa": "Entrantes contra salientes",
                    "reporte": "Varias series en una sola gráfica",
                },
            ),
        }
        async with AsyncTypeSafeClient(
            model=MODEL,
            timeout=8.0,
            retry=RetryPolicy(max_retries=0),
        ) as client:
            response = await client.system_one(state=text, questions=questions)
        _log_usage(response)
        out: dict[str, str] = {}
        route = _pick(response.choices.get("ruta"), ROUTES)
        if route:
            out["ruta"] = route
        period = _pick(response.choices.get("periodo"), PERIODS)
        if period:
            bounds = period_bounds(now or datetime.now(MX), period)
            if bounds:
                out["since"], out["until"] = bounds
        advisor = _pick(response.choices.get("asesor"), set(advisor_criteria))
        if advisor and advisor != "ninguno":
            out["advisor"] = advisor
            out["advisor_id"] = advisor_uids[advisor]
        if route == "dashboard":
            kind = _pick(response.choices.get("kind"), KINDS)
            if kind:
                out["kind"] = kind
                out["graphic"] = GRAPHIC[kind]
        if not out:
            print("[JEV] sin decisiones sobre el umbral")
            return None
        print(f"[JEV] {out}")
        return out
    except Exception as error:
        print(f"[JEV] skip {error}")
        return None


if __name__ == "__main__":
    class _Answer:
        def __init__(self, choice: str, confidence: float) -> None:
            self.choice = choice
            self.confidence = confidence

    now = datetime(2026, 10, 15, 15, tzinfo=MX)
    assert period_bounds(now, "hoy") == ("2026-10-15T00:00:00-06:00", "2026-10-16T00:00:00-06:00")
    assert period_bounds(now, "ayer") == ("2026-10-14T00:00:00-06:00", "2026-10-15T00:00:00-06:00")
    assert period_bounds(now, "esta_semana") == ("2026-10-12T00:00:00-06:00", "2026-10-19T00:00:00-06:00")
    assert period_bounds(now, "semana_pasada") == ("2026-10-05T00:00:00-06:00", "2026-10-12T00:00:00-06:00")
    assert period_bounds(now, "este_mes") == ("2026-10-01T00:00:00-06:00", "2026-11-01T00:00:00-06:00")
    assert period_bounds(now, "mes_pasado") == ("2026-09-01T00:00:00-06:00", "2026-10-01T00:00:00-06:00")
    assert period_bounds(now, "sin_fecha") is None
    jan = datetime(2026, 1, 15, tzinfo=MX)
    assert period_bounds(jan, "mes_pasado") == ("2025-12-01T00:00:00-06:00", "2026-01-01T00:00:00-06:00")
    assert _pick(_Answer("hoy", 0.9), PERIODS) == "hoy"
    assert _pick(_Answer("hoy", 0.84), PERIODS) is None
    assert _pick(_Answer("otro", 0.99), PERIODS) is None
    rows = [
        {"nickname": "jsalas", "uid": "c0000000-0000-4000-8000-000000000002"},
        {"nickname": "rgomez", "uid": "c0000000-0000-4000-8000-000000000001"},
    ]
    assert match_advisor("desglosa el rendimiento de jsalas", rows)[0] == "jsalas"
    assert match_advisor("hola", rows) is None
    assert match_advisor("compara jsalas y rgomez", rows) is None
    swapped = _rewrite('query { crmClients(advisorId: "jsalas") { uid } }', rows)
    assert "c0000000-0000-4000-8000-000000000002" in swapped
    assert "jsalas" not in swapped
    print("ok")
