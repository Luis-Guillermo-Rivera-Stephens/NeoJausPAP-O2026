import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from api.managers import episodes as episodes_mgr

_MODEL = os.getenv("AI_MODEL", "gemini-3.6-flash")
_PROMPT = (
    "Resume los mensajes de WhatsApp en español en 2 o 3 oraciones y extrae de 1 a 5 temas clave "
    "(sustantivos cortos en minúsculas, ej: precio, disponibilidad, visita, credito). "
    "Si se menciona un activo o inmueble concreto, incluye su nombre o identificador exacto "
    "como uno de los temas; no inventes uno si no aparece. "
    "Si viene un resumen actual, intégralo con los mensajes nuevos. "
    'Responde SOLO JSON con las llaves "summary" (string) y "topics" (lista de strings).'
)


class EpisodeExtract(BaseModel):
    summary: str
    topics: list[str] = Field(default_factory=list)


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=os.getenv("AI_BASE_URL"),
            api_key=os.getenv("AI_API_KEY"),
        )
    return _client


async def extract_episode(messages: list[dict], current_summary: str | None = None) -> EpisodeExtract:
    lines = [f"[{m['cat']}] {m['direction']}: {m['body']}" for m in messages]
    user = "\n".join(lines)
    if current_summary:
        user = f"Resumen actual:\n{current_summary}\n\nMensajes nuevos:\n{user}"
    resp = await _get_client().chat.completions.create(
        model=_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    return EpisodeExtract.model_validate_json(raw)


async def process_pending() -> int:
    rows = episodes_mgr.list_pending()
    print(f"[EPISODES] pendientes: {len(rows)} conversaciones")
    done = 0
    for row in rows:
        cid = str(row["conversation_id"])
        try:
            out = await extract_episode(row["messages"], row.get("current_summary"))
            episodes_mgr.upsert_current(
                cid,
                out.summary.strip(),
                out.topics,
                row["window_from"],
                row["last_cat"],
                _MODEL,
            )
            done += 1
        except Exception as error:
            print(f"[EPISODES] error conv={cid}: {error}")
    return done


if __name__ == "__main__":
    from api.db.db import close_pool

    try:
        n = asyncio.run(process_pending())
        print(f"[EPISODES] procesadas: {n}")
    finally:
        close_pool()
