from datetime import datetime
from pathlib import Path

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
from AI.tools import load_skill
from api.managers import memory as memory_mgr
from api.schema.schema import schema

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
# Pista clara de un tipo de gráfica → se precarga solo esa skill.
SKILL_WORDS = {
    "dashboard-kpi": ("kpi", "indicador"),
    "dashboard-categorias": ("pastel", "barras", "por estatus", "por asesor", "por tipo", "por fuente", "distribuci", "desglose"),
    "dashboard-tendencia": ("tendencia", "por día", "por dia", "por semana", "evoluci", "histórico", "historico"),
    "dashboard-comparativa": ("entrantes y salientes", "entrantes vs", "entrantes contra", "salientes y entrantes", "inbound", "outbound", "comparativ", "recibidos y enviados"),
}
# Sin pista de tipo, o con varias: reporte completo con las cuatro skills.
REPORT_WORDS = ("dashboard", "reporte", "de la data", "gráfica", "grafica", "gráfico", "grafico")

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
    if hits or any(w in text for w in REPORT_WORDS):
        return list(SKILL_WORDS)
    return []


def _dashboard_prompt(skills: list[str]) -> str:
    loaded = "\n\n".join(load_skill(name) for name in skills)
    if len(skills) == 1:
        return (
            f"Skill {skills[0]} (ya cargada, no llames read_skill). "
            f"response debe ser el dashboard en Markdown con este formato:\n{loaded}"
        )
    return (
        "Reporte completo. Skills ya cargadas (no llames read_skill). Una sola query GraphQL "
        "con campos hermanos (kpis, countBy, countOverTime, countCompare) y un bloque por serie, "
        f"cada uno con el formato de su skill:\n{loaded}"
    )


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
    if is_new:
        parts.append(
            "Este chat es nuevo. Llena title con 3 a 6 palabras en español, sin comillas ni punto."
        )
    if closed:
        parts.append(f"Ventana anterior (cerrada):\n{closed}")
    if current:
        parts.append(f"Ventana actual:\n{current}")
    skills = _dashboard_skills(body.message)
    if skills:
        parts.append(_dashboard_prompt(skills))
    parts.append(f"Pregunta actual:\n{body.message}")
    result = await Runner.run(agent, "\n\n".join(parts))
    out = result.final_output
    reply = out.response if hasattr(out, "response") else str(out)
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
