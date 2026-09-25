from pathlib import Path
import os

from dotenv import load_dotenv

# Antes de importar el schema: eso abre el pool de Postgres al importar.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from openai import AsyncOpenAI

from AI.tools import call_graphql, read_skill
from AI.output import AiResponse
from api.schema.schema import schema

api_key = os.getenv("AI_API_KEY")
base_url = os.getenv("AI_BASE_URL")
model_name = os.getenv("AI_MODEL", "gemini-3.6-flash")

if not api_key:
    raise RuntimeError("Falta AI_API_KEY en el .env")

client = AsyncOpenAI(base_url=base_url, api_key=api_key)
# Gemini (y otros compatibles) hablan Chat Completions, no Responses API.
set_default_openai_api("chat_completions")
set_default_openai_client(client, use_for_tracing=False)
set_tracing_disabled(disabled=True)

_RULES = """\
Consultas la API solo con call_graphql. Campos en camelCase. Si falla, corrige y reintenta. Responde en español, conciso.
Cada query pide SOLO lo necesario para responder: campos concretos, filtros (q, clientId, clientStatus) y el limit más bajo que alcance. No pidas listas enteras, ni relaciones anidadas, ni campos que no vas a usar en la respuesta.
Si el pedido encaja con una skill (p. ej. dashboard/gráfica), usa read_skill (sin name lista; con name lee el SKILL.md) y sigue esas instrucciones.

Reglas del dominio (el SDL no las dice):
- uid es la PK. cat es created at. No existe createdAt ni id.
- advisors son los asesores (tabla clients). Quien escribe por WhatsApp es crmClients, no advisors.
- El texto de un mensaje es body. No hay content en GraphQL.
- direction: inbound (lo escribió el contacto) | outbound (lo escribió el asesor).
- Límites bajos (default 10, máximo 50). Usa q para filtrar por texto; no listes todo.
- Dashboard, gráfica o KPI: read_skill markdown-dashboards y usa agregado. Eso cuenta en la base; no bajes filas para sumarlas.
- Estatus, seguimiento o "qué pasó": llama buscarEstado(q). Busca en episodios y solo baja a mensajes si no hay coincidencia. No pidas messages si source es episode.
- clientStatus de un contacto: crmClients(q, clientStatus), no mensajes.

Schema GraphQL exacto:
"""

agent = Agent(
    name="GraphQL Agent",
    instructions=_RULES + schema.as_str(),
    tools=[call_graphql, read_skill],
    model=OpenAIChatCompletionsModel(model=model_name, openai_client=client),
    output_type=AiResponse,
)
