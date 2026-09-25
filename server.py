from pathlib import Path
from dotenv import load_dotenv

# Carga .env desde la carpeta donde vive server.py
load_dotenv(Path(__file__).resolve().parent / ".env")

from api.db.db import check_connection

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter
from agents import Runner

from AI.agent import agent
from api.schema.schema import schema

PUBLIC_DIR = Path(__file__).resolve().parent / "public"

app = FastAPI(title="PAP GraphQL + Agent")
app.include_router(GraphQLRouter(schema), prefix="/graphql")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    print(f"[AGENT] /chat recibido: {body.message!r}")
    result = await Runner.run(agent, body.message)
    out = result.final_output
    reply = out.response if hasattr(out, "response") else str(out)
    usage = result.context_wrapper.usage
    print(
        f"[AGENT] tokens: input={usage.input_tokens} "
        f"output={usage.output_tokens} total={usage.total_tokens} "
        f"requests={usage.requests}"
    )
    print(f"[AGENT] /chat respuesta: {reply!r}")
    return ChatResponse(reply=reply)

@app.get("/health")
async def health_check():
    return {"status": "get_connection() is working" if check_connection() else "get_connection() failed"}


@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "views" / "index.html")


app.mount("/styles", StaticFiles(directory=PUBLIC_DIR / "styles"), name="styles")
app.mount("/scripts", StaticFiles(directory=PUBLIC_DIR / "scripts"), name="scripts")
app.mount("/assets", StaticFiles(directory=PUBLIC_DIR / "assets"), name="assets")
