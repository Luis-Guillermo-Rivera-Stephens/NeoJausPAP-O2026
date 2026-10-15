"""Una llamada a Jev antes del agente. Si no hay llave o falla, devuelve None."""

from datetime import datetime, timedelta
from os import getenv
from zoneinfo import ZoneInfo

MX = ZoneInfo("America/Mexico_City")
THRESHOLD = 0.85
MODEL = "jev-latest"

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


def _pick(answer, allowed: tuple[str, ...] | set[str]) -> str | None:
    if answer is None or answer.confidence < THRESHOLD or answer.choice not in allowed:
        return None
    return answer.choice


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
    print("ok")
