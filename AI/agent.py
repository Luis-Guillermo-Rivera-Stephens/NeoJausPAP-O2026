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

from AI.tools import call_graphql, read_skill, render_dashboard, ver_dashboard
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
Datos sueltos: call_graphql. Dashboards: render_dashboard, nunca call_graphql. Campos en camelCase. Si falla, corrige y reintenta. Responde en español, conciso.

Tu salida siempre tiene estos campos:
- response: el mensaje que ve el usuario. Solo la respuesta a la pregunta actual. No incluyas la memoria, ni digas que estás guardando contexto.
- new_summary: relato en prosa de la ventana actual (24 h). Cuenta qué preguntó el usuario, qué respondiste y los hechos que salieron de la API (nombres, uids, estatus, cifras, temas, preguntas y respuestas del contacto). Si el prompt trae "Ventana actual", incorpórala y añade lo nuevo; no borres hechos de esta ventana. No copies "Ventana anterior (cerrada)": esa ya está guardada y se vuelve a inyectar sola.
- title: solo si el prompt dice que el chat es nuevo. 3 a 6 palabras en español, sin comillas ni punto. Si el chat ya tiene id, déjalo vacío.
- errors: lista vacía si las herramientas respondieron bien. Si una falló y no pudiste corregirla, una frase por fallo.
Cada query pide SOLO lo necesario para responder: campos concretos, filtros (q, clientId, clientStatus) y el limit más bajo que alcance. No pidas listas enteras, ni relaciones anidadas, ni campos que no vas a usar en la respuesta.
Si el pedido encaja con una skill que no sea dashboard, usa read_skill (sin name lista; con name lee el SKILL.md) y sigue esas instrucciones.

Reglas del dominio (el SDL no las dice):
- uid es la PK. cat es created at. No existe createdAt ni id.
- La fecha de hoy viene al inicio del prompt, en America/Mexico_City. Los cortes de since/until salen de esa fecha. No inventes otro año.
- advisors son los asesores (tabla clients). Quien escribe por WhatsApp es crmClients, no advisors.
- El texto de un mensaje es body. No hay content en GraphQL.
- direction: inbound (lo escribió el contacto) | outbound (lo escribió el asesor).
- Límites bajos (default 10, máximo 50). Usa q para filtrar por texto; no listes todo.
- Dashboard: una render_dashboard por gráfica. Tú solo armas la query; el server pinta. No leas skills ni copies la tabla en response. En response intercala texto y la línea {{dashboard:N}}. El ok trae pico, mínimo y total: con eso cierra un insight corto. Si necesitas un día, una categoría o una comparación que no esté en ese resumen, llama ver_dashboard(N) una vez y usa esos números. new_summary: una frase por gráfica.
  El kind es el campo de la query, no al revés:
  - kpi → `kpis { agencies advisors clients lost connections conversations openWindows unanswered messages inbound outbound conMensaje usuarios }` o `count(entity, metric)`.
  - categorias → `countBy(entity, by) { key n }`.
  - tendencia → `countOverTime(entity, by: DAY o WEEK) { key n }`. Un día, el mínimo o el máximo salen de esta serie; no pidas otra query para eso.
  - comparativa → `countCompare(by: NONE, DAY, WEEK o CONNECTION) { key inbound outbound n usuarios }`.
  - reporte → dos o más de esos campos, hermanos, en una sola query.
  entity: CRM_CLIENTS, MESSAGES, CONVERSATIONS, CONNECTIONS. metric: COUNT o COUNT_DISTINCT_CLIENTS. Filtros: since, until (until exclusivo), agencyId, clientStatus, direction (solo mensajes), connectionId, clientId. Pide siempre key y n. No uses crmClients, messages ni conversations.
- Estatus, seguimiento o "qué pasó": llama buscarEstado(q). Busca en episodios y solo baja a mensajes si no hay coincidencia. No pidas messages si source es episode.
- clientStatus de un contacto: crmClients(q, clientStatus), no mensajes.
- El prompt ya trae la ventana cerrada más reciente y la actual. Si falta un hecho de antes, llama memories(q, limit). Solo devuelve relatos de ai_memory ya cerrados, no el chat completo. Para seguir hacia atrás, pasa before con el windowTo más viejo que ya leíste.

Schema GraphQL exacto:
"""

agent = Agent(
    name="GraphQL Agent",
    instructions=_RULES + schema.as_str(),
    tools=[call_graphql, read_skill, render_dashboard, ver_dashboard],
    model=OpenAIChatCompletionsModel(model=model_name, openai_client=client),
    output_type=AiResponse,
)
