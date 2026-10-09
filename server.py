from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Carga .env desde la carpeta donde vive server.py
load_dotenv(Path(__file__).resolve().parent / ".env")

from api.db.db import check_connection

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter
from agents import Runner

from AI.agent import agent
from AI.dashboard import CHAT_ID, splice
from api.db.cache import take_dashboards
from api.managers import memory as memory_mgr
from api.schema.schema import schema

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
# Pista clara de un tipo de gráfica → se precarga solo esa skill.
SKILL_WORDS = {
    "dashboard-kpi": ("kpi", "indicador"),
    "dashboard-categorias": ("pastel", "barras", "por estatus", "por asesor", "por tipo", "por fuente", "distribuci", "desglose"),
    "dashboard-tendencia": ("tendencia", "por día", "por dia", "por semana", "evoluci", "histórico", "historico", "dia", "semana"),
    "dashboard-comparativa": ("entrantes y salientes", "entrantes vs", "entrantes contra", "salientes y entrantes", "inbound", "outbound", "comparativ", "recibidos y enviados"),
}
# "reporte" pide varias series. "dashboard" a secas no: si no hay otra pista, es una sola gráfica.
REPORT_WORDS = ("reporte", "de la data")
GENERIC_WORDS = ("dashboard", "gráfica", "grafica", "gráfico", "grafico")
SKILL_KIND = {
    "dashboard-kpi": "kpi",
    "dashboard-categorias": "categorias",
    "dashboard-tendencia": "tendencia",
    "dashboard-comparativa": "comparativa",
}

app = FastAPI(title="PAP GraphQL + Agent")
app.include_router(GraphQLRouter(schema), prefix="/graphql")


class ChatRequest(BaseModel):
    message: str
    chat_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    chat_id: str
    title: str | None = None


def _parse_before(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_chat(chat_id: str) -> None:
    if not memory_mgr.owns(chat_id):
        raise HTTPException(status_code=404, detail="Chat no encontrado")


def _dashboard_skills(message: str) -> list[str]:
    text = message.lower()
    hits = [name for name, words in SKILL_WORDS.items() if any(w in text for w in words)]
    if len(hits) == 1:
        return hits
    if len(hits) > 1 or any(w in text for w in REPORT_WORDS):
        return list(SKILL_WORDS)
    if any(w in text for w in GENERIC_WORDS):
        return ["dashboard-kpi"]
    return []


def _dashboard_kind(message: str) -> str | None:
    skills = _dashboard_skills(message)
    if len(skills) == 1:
        return SKILL_KIND[skills[0]]
    if skills:
        return "reporte"
    return None


@app.get("/chats")
async def get_chats(limit: int = 20, before: str | None = None):
    return memory_mgr.list_chats(limit, _parse_before(before))


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    if body.chat_id:
        chat_id = body.chat_id
        _require_chat(chat_id)
        is_new = not memory_mgr.has_title(chat_id)
    else:
        chat_id = memory_mgr.create_chat()["uid"]
        is_new = True
    print(f"[AGENT] /chat recibido: {body.message!r}")
    memory_mgr.append_message(chat_id, "user", body.message)
    closed, current = memory_mgr.context_for_prompt(chat_id)
    parts = []
    hoy = datetime.now(ZoneInfo("America/Mexico_City"))
    parts.append(
        f"Hoy es {hoy:%Y-%m-%d} (America/Mexico_City). "
        "Para un día usa since de ese día y until del día siguiente. "
        "Para un mes, since el día 1 y until el día 1 del mes siguiente."
    )
    if is_new:
        parts.append(
            "Este chat es nuevo. Llena title con 3 a 6 palabras en español, sin comillas ni punto."
        )
    if closed:
        parts.append(f"Ventana anterior (cerrada):\n{closed}")
    if current:
        parts.append(f"Ventana actual:\n{current}")
    kind = _dashboard_kind(body.message)
    if kind:
        parts.append(
            "Es un dashboard. No uses call_graphql. "
            "kind según el campo: count o kpis → kpi; countBy → categorias; "
            "countOverTime → tendencia; countCompare → comparativa. "
            "En response, texto y {{dashboard:N}} por cada ok N."
        )
    parts.append(f"Pregunta actual:\n{body.message}")
    token = CHAT_ID.set(chat_id)
    try:
        result = await Runner.run(agent, "\n\n".join(parts))
    finally:
        CHAT_ID.reset(token)
    out = result.final_output
    try:
        stored = take_dashboards(chat_id)
    except Exception as error:
        print(f"[AGENT] dashboard redis error={error}")
        stored = []
    text = out.response if hasattr(out, "response") else str(out)
    reply = splice(text, stored)
    summary = getattr(out, "new_summary", "") or ""
    memory_mgr.save_current(chat_id, summary)
    if summary.strip():
        print(f"[AGENT] ventana actual: {summary!r}")
    memory_mgr.append_message(chat_id, "assistant", reply)
    title = None
    if is_new:
        raw = getattr(out, "title", None) or ""
        title = memory_mgr.set_title(chat_id, raw) if raw.strip() else None
    usage = result.context_wrapper.usage
    print(
        f"[AGENT] tokens: input={usage.input_tokens} "
        f"output={usage.output_tokens} total={usage.total_tokens} "
        f"requests={usage.requests}"
    )
    return ChatResponse(reply=reply, chat_id=chat_id, title=title)


@app.get("/chat/{chat_id}/history")
async def chat_history(chat_id: str, page: int = 1, limit: int = 30):
    _require_chat(chat_id)
    return memory_mgr.list_messages(chat_id, page, limit)

@app.get("/health")
async def health_check():
    return {"status": "get_connection() is working" if check_connection() else "get_connection() failed"}


@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "views" / "index.html")


app.mount("/styles", StaticFiles(directory=PUBLIC_DIR / "styles"), name="styles")
app.mount("/scripts", StaticFiles(directory=PUBLIC_DIR / "scripts"), name="scripts")
app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")
