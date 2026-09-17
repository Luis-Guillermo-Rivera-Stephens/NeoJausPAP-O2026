from pathlib import Path
from dotenv import load_dotenv

# Carga .env desde la carpeta donde vive server.py
load_dotenv(Path(__file__).resolve().parent / ".env")

from api.db.db import check_connection

from fastapi import FastAPI
from pydantic import BaseModel
from strawberry.fastapi import GraphQLRouter
from agents import Runner

from AI.agent import agent
from api.schema.schema import schema

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
    reply = str(result.final_output)
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
