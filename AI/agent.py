from contextvars import ContextVar
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
Datos sueltos: call_graphql. Dashboards: render_dashboard para el conteo. Si hace falta un uid, primero call_graphql. Campos en camelCase. Si falla, corrige y reintenta. Responde en español, conciso.

Tu salida siempre tiene estos campos:
- response: el mensaje que ve el usuario. Solo la respuesta a la pregunta actual. No incluyas la memoria, ni digas que estás guardando contexto.
- new_summary: relato del hilo de esta ventana (24 h), no una lista de datos. En orden: qué preguntó el usuario, qué se respondió y los hechos que salieron (cifras, fechas, estatus). Si el prompt trae "Ventana actual", consérvala entera y añade lo nuevo al final; no la reemplaces por el último dato. No copies "Ventana anterior (cerrada)".
  Dentro de esas frases, cada asesor, contacto, número o conversación que vino de la API va con el uuid que devolvió la llamada, entre llaves: {uuid/nombre}. Asesor: nickname. Contacto: preferred_name o first_name. Número: name o phone_e164. Conversación: conversation_category. Agencia: solo el uid, sin inventar nombre. Si esta llamada no trajo el uid, deja el nombre sin llaves. No inventes un uid. Si la ventana ya trae {uid/nombre}, reutiliza ese uid y no vuelvas a buscarlo.
  Incorrecto: "El cliente más reciente de rgomez es Ana Ortiz". Correcto: "El usuario preguntó el cliente más reciente de Gómez. Es {a1b2c3d4-0000-4000-8000-000000000010/Ana Ortiz}, alta 2026-07-05, del asesor {c0000000-0000-4000-8000-000000000001/rgomez}".
  La respuesta al usuario no lleva llaves ni uids.
- title: solo si el prompt dice que el chat es nuevo. 3 a 6 palabras en español, sin comillas ni punto. Si el chat ya tiene id, déjalo vacío.
- errors: lista vacía si las herramientas respondieron bien. Si una falló y no pudiste corregirla, una frase por fallo.
Cada query pide SOLO lo necesario para responder: campos concretos, filtros (q, clientId, clientStatus) y el limit más bajo que alcance. No pidas listas enteras, ni relaciones anidadas, ni campos que no vas a usar en la respuesta.
Si el pedido encaja con una skill que no sea dashboard, usa read_skill (sin name lista; con name lee el SKILL.md) y sigue esas instrucciones.

Reglas del dominio (el SDL no las dice):
- uid es la PK. cat es created at. No existe createdAt ni id.
- La fecha de hoy viene al inicio del prompt, en America/Mexico_City. Los cortes de since/until salen de esa fecha. No inventes otro año.
- Clientes de un asesor: si la ventana ya trae {uid/nickname} de ese asesor, usa ese uid y no llames advisors. Si no está, `{ advisors { uid nickname } }` y luego `crmClients(advisorId: ese-uid, limit: 1) { uid cat firstName preferredName }`. Viene ordenado por cat descendente: limit 1 es el más reciente. No pases clientStatus: null. No subas el limit para filtrar tú, ni pidas assignedTo si ya filtraste por advisorId.
- El texto de un mensaje es body. No hay content en GraphQL.
- Límites bajos (default 10, máximo 50). Usa q para filtrar por texto; no listes todo.
- Dashboard: una render_dashboard por gráfica. Tú solo armas la query; el server pinta con Chart.js. No leas skills, no escribas ```chart ni ```mermaid, no copies la tabla. En response intercala texto y la línea {{dashboard:N}}. El ok trae pico, mínimo y total: con eso cierra un insight corto. Si necesitas un día, una categoría o una comparación que no esté en ese resumen, llama ver_dashboard(N) una vez y usa esos números. En new_summary añade una frase de la gráfica al relato; no borres el hilo.
  Si el usuario solo pide otro dibujo, repite la misma query y los mismos filtros y cambia graphic.
  graphic (el dibujo, no el kind): bar (default); pie solo categorias; line o area en tendencia, o en un reporte de varios countOverTime (una sola gráfica, una serie por alias); stacked o scatter solo comparativa. Heatmap no existe: dilo y ofrece bar o stacked.
  El kind es el campo de la query, no al revés:
  - kpi → `kpis { agencies advisors clients lost connections conversations openWindows unanswered messages inbound outbound conMensaje usuarios }` o `count(entity: MESSAGES, metric: COUNT)`.
  - categorias → `countBy(entity: MESSAGES, by: ADVISOR) { key n }`.
  - tendencia → `countOverTime(entity: MESSAGES, by: DAY) { key n }` o `by: WEEK`. Un día, el mínimo o el máximo salen de esta serie; no pidas otra query para eso.
  - comparativa → `countCompare(by: DAY) { key inbound outbound n usuarios }`. by también puede ser NONE, WEEK o CONNECTION.
  - reporte → dos o más de esos campos, hermanos, en una sola query, cada uno con sus subcampos.
  Enums, sin comillas y en MAYÚSCULAS: entity (CRM_CLIENTS, MESSAGES, CONVERSATIONS, CONNECTIONS), metric (COUNT, COUNT_DISTINCT_CLIENTS), by.
  Strings, con comillas y en minúsculas: direction solo "inbound" o "outbound" (solo en mensajes; inbound lo escribió el contacto). clientStatus solo "new", "contacted", "active", "closed", "lost", "inactive", "archived". since y until son strings ISO; until es exclusivo.
  También puedes filtrar por agencyId, connectionId, clientId y advisorId. Los cuatro son uids, nunca un nickname.
  Si nombran a un asesor (rgomez) y la ventana no trae ya {uid/rgomez} con el uid real, llama `{ advisors { uid nickname } }`, toma ese uid y pásalo en advisorId. Si el token ya está, reutilízalo y no llames advisors. clientId es el contacto (crmClients), no el asesor. No pongas "rgomez" en clientId ni en advisorId.
  Comparar dos asesores día a día: UNA render_dashboard, kind reporte, graphic line. Dos countOverTime hermanos con alias, cada uno con su advisorId y by: DAY. El server junta las series en una sola línea. No hagas un dashboard por persona. No es countCompare.
  Correcto: `countOverTime(entity: MESSAGES, by: DAY, advisorId: "el-uid", since: "2026-09-01T00:00:00-06:00", until: "2026-10-01T00:00:00-06:00") { key n }`.
  Incorrecto, no lo envíes: `countBy(by: ADVISOR)` sin `{ key n }`; `direction: INBOUND` sin comillas; `direction: "INBOUND"` en mayúsculas; `crmClients`, `messages` o `conversations` como campo de conteo.
- Estatus, seguimiento o "qué pasó": llama buscarEstado(q). Busca en episodios y solo baja a mensajes si no hay coincidencia. No pidas messages si source es episode.
- clientStatus de un contacto: crmClients(q, clientStatus), no mensajes.
- El prompt ya trae la ventana cerrada más reciente y la actual. Si falta un hecho de antes, llama memories(q, limit). Solo devuelve relatos de ai_memory ya cerrados, no el chat completo. Para seguir hacia atrás, pasa before con el windowTo más viejo que ya leíste.

Schema GraphQL exacto:
"""

# Sin ruta de Jev se usa _RULES entero. Con ruta, solo el bloque de esa ruta.
TURN: ContextVar[dict | None] = ContextVar("jev_turn", default=None)

_CORE = """\
Campos en camelCase. Si una herramienta falla, corrige y reintenta. Responde en español, conciso.

Tu salida siempre tiene estos campos:
- response: el mensaje que ve el usuario. Solo la respuesta a la pregunta actual. No incluyas la memoria, ni digas que estás guardando contexto.
- new_summary: relato del hilo de esta ventana (24 h), no una lista de datos. En orden: qué preguntó el usuario, qué se respondió y los hechos que salieron (cifras, fechas, estatus). Si el prompt trae "Ventana actual", consérvala entera y añade lo nuevo al final; no la reemplaces por el último dato. No copies "Ventana anterior (cerrada)".
  Dentro de esas frases, cada asesor, contacto, número o conversación que vino de la API va con el uuid que devolvió la llamada, entre llaves: {uuid/nombre}. Asesor: nickname. Contacto: preferred_name o first_name. Número: name o phone_e164. Conversación: conversation_category. Agencia: solo el uid, sin inventar nombre. Si esta llamada no trajo el uid, deja el nombre sin llaves. No inventes un uid. Si la ventana ya trae {uid/nombre}, reutiliza ese uid y no vuelvas a buscarlo.
  Incorrecto: "El cliente más reciente de rgomez es Ana Ortiz". Correcto: "El usuario preguntó el cliente más reciente de Gómez. Es {a1b2c3d4-0000-4000-8000-000000000010/Ana Ortiz}, alta 2026-07-05, del asesor {c0000000-0000-4000-8000-000000000001/rgomez}".
  La respuesta al usuario no lleva llaves ni uids.
- title: solo si el prompt dice que el chat es nuevo. 3 a 6 palabras en español, sin comillas ni punto. Si el chat ya tiene id, déjalo vacío.
- errors: lista vacía si las herramientas respondieron bien. Si una falló y no pudiste corregirla, una frase por fallo.
Cada query pide SOLO lo necesario para responder: campos concretos, filtros (q, clientId, clientStatus) y el limit más bajo que alcance. No pidas listas enteras, ni relaciones anidadas, ni campos que no vas a usar en la respuesta.
Si el pedido encaja con una skill que no sea dashboard, usa read_skill (sin name lista; con name lee el SKILL.md) y sigue esas instrucciones.

Reglas del dominio (el SDL no las dice):
- uid es la PK. cat es created at. No existe createdAt ni id.
- El texto de un mensaje es body. No hay content en GraphQL.
- Límites bajos (default 10, máximo 50). Usa q para filtrar por texto; no listes todo.
"""

_ADVISOR = """\
- Clientes de un asesor: si la ventana ya trae {uid/nickname} de ese asesor, usa ese uid y no llames advisors. Si no está, `{ advisors { uid nickname } }` y luego `crmClients(advisorId: ese-uid, limit: 1) { uid cat firstName preferredName }`. Viene ordenado por cat descendente: limit 1 es el más reciente. No pases clientStatus: null. No subas el limit para filtrar tú, ni pidas assignedTo si ya filtraste por advisorId.
- Si nombran a un asesor y la ventana no trae ya {uid/nickname} con el uid real, llama `{ advisors { uid nickname } }`, toma ese uid y pásalo en advisorId. clientId es el contacto (crmClients), no el asesor. No pongas el nickname en clientId ni en advisorId.
"""

_DATES = """\
- La fecha de hoy viene al inicio del prompt, en America/Mexico_City. Los cortes de since/until salen de esa fecha. No inventes otro año.
"""

_DATES_DONE = """\
- since y until ya vienen en el mensaje. No calcules otras fechas. No inventes otro año.
"""

_ADVISOR_DONE = """\
- advisorId ya viene en el mensaje. No llames advisors. clientId es el contacto, no el asesor.
"""

_DASHBOARD = """\
- Dashboard: una render_dashboard por gráfica. Tú solo armas la query; el server pinta con Chart.js. No leas skills, no escribas ```chart ni ```mermaid, no copies la tabla. En response intercala texto y la línea {{dashboard:N}}. El ok trae pico, mínimo y total: con eso cierra un insight corto. Si necesitas un día, una categoría o una comparación que no esté en ese resumen, llama ver_dashboard(N) una vez y usa esos números. En new_summary añade una frase de la gráfica al relato; no borres el hilo.
  Enums, sin comillas y en MAYÚSCULAS: entity (CRM_CLIENTS, MESSAGES, CONVERSATIONS, CONNECTIONS), metric (COUNT, COUNT_DISTINCT_CLIENTS), by.
  Strings, con comillas y en minúsculas: direction solo "inbound" o "outbound" (solo en mensajes; inbound lo escribió el contacto). since y until son strings ISO; until es exclusivo.
  También puedes filtrar por agencyId, connectionId, clientId y advisorId. Los cuatro son uids, nunca un nickname.
  Incorrecto, no lo envíes: `countBy(by: ADVISOR)` sin `{ key n }`; `direction: INBOUND` sin comillas; `direction: "INBOUND"` en mayúsculas; `crmClients`, `messages` o `conversations` como campo de conteo.
"""

_KIND = {
    "kpi": "- kind kpi. Query: `kpis { agencies advisors clients lost connections conversations openWindows unanswered messages inbound outbound conMensaje usuarios }` o `count(entity: MESSAGES, metric: COUNT)`.",
    "categorias": "- kind categorias. Query: `countBy(entity: MESSAGES, by: ADVISOR) { key n }`.",
    "tendencia": "- kind tendencia. Query: `countOverTime(entity: MESSAGES, by: DAY) { key n }` o `by: WEEK`. Un día, el mínimo o el máximo salen de esta serie.",
    "comparativa": "- kind comparativa. Query: `countCompare(by: DAY) { key inbound outbound n usuarios }`. by también puede ser NONE, WEEK o CONNECTION.",
    "reporte": "- kind reporte. Dos o más campos de conteo, hermanos, en una sola query, cada uno con sus subcampos.",
}

_KIND_ALL = """\
  El kind es el campo de la query, no al revés:
  - kpi → `kpis { agencies advisors clients lost connections conversations openWindows unanswered messages inbound outbound conMensaje usuarios }` o `count(entity: MESSAGES, metric: COUNT)`.
  - categorias → `countBy(entity: MESSAGES, by: ADVISOR) { key n }`.
  - tendencia → `countOverTime(entity: MESSAGES, by: DAY) { key n }` o `by: WEEK`. Un día, el mínimo o el máximo salen de esta serie; no pidas otra query para eso.
  - comparativa → `countCompare(by: DAY) { key inbound outbound n usuarios }`. by también puede ser NONE, WEEK o CONNECTION.
  - reporte → dos o más de esos campos, hermanos, en una sola query, cada uno con sus subcampos.
  graphic: bar (default); pie solo categorias; line o area en tendencia, o en un reporte de varios countOverTime; stacked o scatter solo comparativa. Heatmap no existe.
  Comparar dos asesores día a día: UNA render_dashboard, kind reporte, graphic line. Dos countOverTime hermanos con alias, cada uno con su advisorId y by: DAY.
"""

_ESTATUS = """\
- Estatus, seguimiento o "qué pasó": llama buscarEstado(q). Busca en episodios y solo baja a mensajes si no hay coincidencia. No pidas messages si source es episode.
- clientStatus de un contacto: crmClients(q, clientStatus), no mensajes.
"""

_MEMORIA = """\
- El prompt ya trae la ventana cerrada más reciente y la actual. Si falta un hecho de antes, llama memories(q, limit). Solo devuelve relatos de ai_memory ya cerrados, no el chat completo. Para seguir hacia atrás, pasa before con el windowTo más viejo que ya leíste.
"""

_DATOS = """\
- Resuelve con call_graphql. No uses render_dashboard.
- clientStatus de un contacto: crmClients(q, clientStatus), no mensajes. No pases clientStatus: null.
"""


def instructions_for(decisions: dict | None) -> str:
    tail = "Schema GraphQL exacto:\n" + schema.as_str()
    if not decisions or "ruta" not in decisions:
        text = _RULES
        if decisions and decisions.get("since"):
            text = text.replace(
                "La fecha de hoy viene al inicio del prompt, en America/Mexico_City. Los cortes de since/until salen de esa fecha. No inventes otro año.",
                "since y until ya vienen en el mensaje. No calcules otras fechas. No inventes otro año.",
            )
        if decisions and decisions.get("advisor_id"):
            text = text.replace(
                "Si no está, `{ advisors { uid nickname } }` y luego `crmClients(advisorId: ese-uid, limit: 1) { uid cat firstName preferredName }`.",
                "advisorId ya viene en el mensaje. Úsalo. No llames advisors.",
            )
            text = text.replace(
                "llama `{ advisors { uid nickname } }`, toma ese uid y pásalo en advisorId. Si el token ya está, reutilízalo y no llames advisors.",
                "usa el advisorId del mensaje. No llames advisors.",
            )
        return text + schema.as_str()
    route = decisions["ruta"]
    parts = [_CORE, decisions.get("since") and _DATES_DONE or _DATES]
    if decisions.get("advisor_id"):
        parts.append(_ADVISOR_DONE)
    elif route in ("datos", "dashboard"):
        parts.append(_ADVISOR)
    if route == "datos":
        parts.append(_DATOS)
    elif route == "dashboard":
        parts.append(_DASHBOARD)
        kind = decisions.get("kind")
        parts.append(_KIND[kind] if kind in _KIND else _KIND_ALL)
        if kind:
            parts.append(f"- Usa graphic {decisions['graphic']}. No elijas otro kind ni otro graphic.")
    elif route == "estatus":
        parts.append(_ESTATUS)
    elif route == "memoria":
        parts.append(_MEMORIA)
    parts.append(tail)
    return "\n".join(parts)


def _instructions(_ctx, _agent) -> str:
    return instructions_for(TURN.get())


agent = Agent(
    name="GraphQL Agent",
    instructions=_instructions,
    tools=[call_graphql, read_skill, render_dashboard, ver_dashboard],
    model=OpenAIChatCompletionsModel(model=model_name, openai_client=client),
    output_type=AiResponse,
)
