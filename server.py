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

from AI.agent import TURN, agent
from AI.dashboard import CHAT_ID, splice
from AI.jev import classify
from api.db.cache import take_dashboards
from api.managers import memory as memory_mgr
from api.schema.schema import schema

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
_ROUTE_LINE = {
    "datos": "Ruta: datos. Resuelve con call_graphql. No uses render_dashboard, buscarEstado ni memories.",
    "dashboard": "Ruta: dashboard. El conteo va en render_dashboard.",
    "estatus": "Ruta: estatus. Llama buscarEstado(q). No pidas messages si source es episode.",
    "memoria": "Ruta: memoria. Si falta un hecho de antes, llama memories(q, limit).",
}

app = FastAPI(title="PAP GraphQL + Agent")
app.include_router(GraphQLRouter(schema), prefix="/graphql")


@app.middleware("http")
async def no_cache_assets(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith(("/scripts", "/styles")):
        response.headers["Cache-Control"] = "no-cache"
    return response


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


def _decision_prompt(decisions: dict) -> str:
    lines = ["Decisiones ya resueltas. Úsalas tal cual."]
    route = decisions.get("ruta")
    if route in _ROUTE_LINE:
        lines.append(_ROUTE_LINE[route])
    if decisions.get("since"):
        lines.append(f"since: {decisions['since']}")
        lines.append(f"until: {decisions['until']} (exclusivo). No calcules otras fechas.")
    if decisions.get("advisor_id"):
        lines.append(
            f"advisorId: {decisions['advisor_id']} ({decisions['advisor']}). No llames advisors."
        )
    if decisions.get("kind"):
        lines.append(f"kind: {decisions['kind']}")
        lines.append(f"graphic: {decisions['graphic']}")
        lines.append("Una render_dashboard con ese kind y ese graphic.")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


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
    decisions = await classify(body.message, hoy)
    hoy_line = f"Hoy es {hoy:%Y-%m-%d} (America/Mexico_City)."
    if not (decisions and decisions.get("since")):
        hoy_line += (
            " Para un día usa since de ese día y until del día siguiente. "
            "Para un mes, since el día 1 y until el día 1 del mes siguiente."
        )
    parts.append(hoy_line)
    if is_new:
        parts.append(
            "Este chat es nuevo. Llena title con 3 a 6 palabras en español, sin comillas ni punto."
        )
    if closed:
        parts.append(f"Ventana anterior (cerrada):\n{closed}")
    if current:
        parts.append(f"Ventana actual:\n{current}")
    if decisions:
        block = _decision_prompt(decisions)
        if block:
            parts.append(block)
    parts.append(f"Pregunta actual:\n{body.message}")
    token = CHAT_ID.set(chat_id)
    turn = TURN.set(decisions)
    try:
        result = await Runner.run(agent, "\n\n".join(parts))
    finally:
        TURN.reset(turn)
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
    return FileResponse(
        PUBLIC_DIR / "views" / "index.html",
        headers={"Cache-Control": "no-cache"},
    )


app.mount("/styles", StaticFiles(directory=PUBLIC_DIR / "styles"), name="styles")
app.mount("/scripts", StaticFiles(directory=PUBLIC_DIR / "scripts"), name="scripts")
app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")
