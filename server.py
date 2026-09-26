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
from api.managers import memory as memory_mgr
from api.schema.schema import schema

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

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


@app.post("/chats")
async def create_chat():
    return memory_mgr.create_chat()


@app.get("/chats")
async def get_chats(limit: int = 20, before: str | None = None):
    return memory_mgr.list_chats(limit, _parse_before(before))


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    is_new = not body.chat_id
    if is_new:
        chat_id = memory_mgr.create_chat()["uid"]
    else:
        _require_chat(body.chat_id)
        chat_id = body.chat_id
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
    parts.append(f"Pregunta actual:\n{body.message}")
    result = await Runner.run(agent, "\n\n".join(parts))
    out = result.final_output
    reply = out.response if hasattr(out, "response") else str(out)
    summary = getattr(out, "new_summary", "") or ""
    if summary.strip():
        memory_mgr.save_current(chat_id, summary)
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
    print(f"[AGENT] /chat respuesta: {reply!r}")
    return ChatResponse(reply=reply, chat_id=chat_id, title=title)


@app.get("/chat/history")
async def chat_history(chatId: str, limit: int = 30, before: str | None = None):
    _require_chat(chatId)
    return memory_mgr.list_messages(chatId, limit, _parse_before(before))

@app.get("/health")
async def health_check():
    return {"status": "get_connection() is working" if check_connection() else "get_connection() failed"}


@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "views" / "index.html")


app.mount("/styles", StaticFiles(directory=PUBLIC_DIR / "styles"), name="styles")
app.mount("/scripts", StaticFiles(directory=PUBLIC_DIR / "scripts"), name="scripts")
app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")
