# OpenAI Agents SDK (`openai-agents`)

Documentación práctica del paquete Python **openai-agents** (import: `agents`).  
Versión de referencia del proyecto: la instalada en `requirements.txt` (`openai-agents`).

Docs oficiales: https://openai.github.io/openai-agents-python/

---

## 1. Qué es

El SDK orquesta un **agente** (LLM + instrucciones + tools + reglas de salida) mediante un **Runner** que:

1. Llama al modelo.
2. Ejecuta tools / handoffs si el modelo los pide.
3. Repite hasta un **output final** o hasta `max_turns`.

No es solo “chat completion”: el SDK gestiona el loop de tool-calling por ti.

```text
Usuario → Runner.run(agent, input)
              ↓
         LLM (con tools)
              ↓
         ¿tool call? → ejecuta tool → vuelve al LLM
         ¿handoff?   → cambia de agente
         ¿output final? → RunResult.final_output
```

---

## 2. Instalación y configuración

```bash
pip install openai-agents python-dotenv
```

Variables de entorno típicas:

```env
OPENAI_API_KEY=sk-...
```

```python
from dotenv import load_dotenv
load_dotenv()
```

El SDK usa la **Responses API** de OpenAI por defecto para modelos OpenAI.

---

## 3. Crear un agente

```python
from agents import Agent

agent = Agent(
    name="Asistente",
    instructions="Eres un asistente útil. Responde en español y sé conciso.",
    model="gpt-4o-mini",
)
```

### Parámetros importantes de `Agent`

| Parámetro | Obligatorio | Descripción |
|-----------|-------------|-------------|
| `name` | sí | Nombre legible del agente. |
| `instructions` | recomendado | System prompt (str o función dinámica). |
| `model` | no | Modelo LLM (str o implementación `Model`). |
| `model_settings` | no | `ModelSettings` (`temperature`, `tool_choice`, etc.). |
| `tools` | no | Lista de tools que el agente puede llamar. |
| `output_type` | no | Tipo estructurado de salida (Pydantic, dataclass, etc.). |
| `handoffs` | no | Agentes a los que puede transferir la conversación. |
| `handoff_description` | no | Descripción corta cuando este agente es objetivo de handoff / tool. |
| `input_guardrails` / `output_guardrails` | no | Validaciones de entrada/salida. |
| `tool_use_behavior` | no | Cómo tratar el resultado de las tools. |
| `hooks` | no | Callbacks del ciclo de vida del agente. |
| `mcp_servers` | no | Servidores MCP que aportan tools. |
| `reset_tool_choice` | no | Reinicia `tool_choice` tras un tool call (default `True`). |

> **Nota:** El system prompt va en `instructions`, no en un campo `description`.  
> Para describir el agente en handoffs usa `handoff_description`.

### Instrucciones dinámicas

```python
from agents import Agent, RunContextWrapper

def instructions(ctx: RunContextWrapper[dict], agent: Agent) -> str:
    return f"Ayuda al usuario {ctx.context['name']}. Sé breve."

agent = Agent(name="Dinámico", instructions=instructions)
```

### Clonar un agente

```python
otro = agent.clone(
    name="Versión formal",
    instructions="Responde de forma formal.",
)
```

---

## 4. Correr un agente (`Runner`)

```python
from agents import Agent, Runner
import asyncio

agent = Agent(
    name="Asistente",
    instructions="Responde en una sola frase.",
    model="gpt-4o-mini",
)

async def main():
    result = await Runner.run(agent, "¿Qué es GraphQL?")
    print(result.final_output)

asyncio.run(main())
```

### Tres formas de ejecutar

| Método | Uso |
|--------|-----|
| `await Runner.run(...)` | Async, resultado completo. |
| `Runner.run_sync(...)` | Sync (envuelve `.run()`). |
| `Runner.run_streamed(...)` | Async + eventos en streaming. |

### Input aceptado

- `str` → se trata como mensaje de usuario.
- Lista de items (formato Responses API).
- `RunState` para reanudar una corrida pausada.

### Loop interno (resumen)

1. Llama al LLM del agente actual.
2. Si hay **output final** del tipo esperado y sin tool calls → termina.
3. Si hay **tool calls** → las ejecuta, agrega resultados y vuelve al paso 1.
4. Si hay **handoff** → cambia de agente y continúa.
5. Si se supera `max_turns` → lanza `MaxTurnsExceeded`.

```python
result = await Runner.run(agent, "Hola", max_turns=10)
```

### Streaming

```python
result = Runner.run_streamed(agent, "Explica recursion")

async for event in result.stream_events():
    # filtrar según event.type según necesites
    print(event.type)

print(result.final_output)
```

### Contexto (dependency injection)

Cualquier objeto Python que quieras compartir con tools/hooks:

```python
from dataclasses import dataclass
from agents import Agent, Runner, function_tool, RunContextWrapper

@dataclass
class AppContext:
    user_id: str

@function_tool
def whoami(ctx: RunContextWrapper[AppContext]) -> str:
    return f"Usuario: {ctx.context.user_id}"

agent = Agent[AppContext](
    name="Ctx",
    instructions="Usa whoami si te preguntan quién soy.",
    tools=[whoami],
)

result = await Runner.run(
    agent,
    "¿Quién soy?",
    context=AppContext(user_id="u-123"),
)
```

---

## 5. Outputs (salida del agente)

### Texto plano (default)

Sin `output_type`, `result.final_output` es un `str`.

```python
result = await Runner.run(agent, "Di hola")
print(result.final_output)  # str
```

### Output estructurado (`output_type`)

Fuerza *structured outputs*. Ideal con Pydantic:

```python
from pydantic import BaseModel
from agents import Agent, Runner

class RespuestaGraphQL(BaseModel):
    ok: bool
    resumen: str
    campos: list[str]

agent = Agent(
    name="Extractor",
    instructions="Extrae un resumen estructurado de la petición GraphQL del usuario.",
    output_type=RespuestaGraphQL,
    model="gpt-4o-mini",
)

result = await Runner.run(agent, "Quiero users { id name }")
data: RespuestaGraphQL = result.final_output
print(data.resumen, data.campos)
```

También admite dataclasses, TypedDict, listas, etc. (vía TypeAdapter de Pydantic).

### Resultado completo (`RunResult`)

Lo más usado:

| Campo / API | Qué es |
|-------------|--------|
| `final_output` | Salida final tipada (`str` o tu `output_type`). |
| `final_output_as(Tipo)` | Cast/validación al tipo deseado. |
| Historial de items | Mensajes, tool calls, handoffs del run. |

### Cuidado: `output_type` + tools

Si el modelo genera de inmediato un JSON válido del `output_type`, el Runner puede **terminar sin llamar tools**.  
Para forzar una tool:

```python
from agents import Agent, ModelSettings

agent = Agent(
    name="Con tool obligatoria",
    instructions="Siempre llama call_graphql antes de responder.",
    tools=[call_graphql],
    output_type=RespuestaGraphQL,
    model_settings=ModelSettings(tool_choice="call_graphql"),  # o "required"
)
```

---

## 6. Tools

Las tools son acciones que el modelo puede invocar (APIs, DB, cálculos, etc.).

Categorías principales:

1. **Function tools** — funciones Python (`@function_tool` / `@tool`).
2. **Agents as tools** — otro `Agent` expuesto como tool.
3. **Hosted tools** — WebSearch, FileSearch, CodeInterpreter, etc. (corren en OpenAI).
4. **Local runtime** — shell/computer/apply-patch según el caso.
5. **MCP** — tools remotas vía `mcp_servers`.

### 6.1 Function tools (lo más común)

```python
from agents import function_tool

@function_tool
def call_graphql(query: str) -> str:
    """Ejecuta una query GraphQL y devuelve la respuesta en texto/JSON."""
    # aquí harías HTTP a tu API
    return '{"data": {"users": []}}'
```

El SDK:

- Genera el **JSON Schema** de parámetros desde la firma.
- Usa el **docstring** como descripción de la tool (importante para que el modelo sepa cuándo usarla).
- Ejecuta la función cuando el LLM la invoca.

#### Con opciones

```python
@function_tool(
    name_override="consultar_graphql",
    description_override="Llama al endpoint GraphQL del backend PAP.",
    strict_mode=True,
)
def call_graphql(query: str) -> str:
    ...
```

Opciones útiles:

| Opción | Uso |
|--------|-----|
| `name_override` | Nombre expuesto al modelo. |
| `description_override` | Descripción de la tool. |
| `strict_mode` | Schema estricto (default `True`). |
| `is_enabled` | bool o callback para habilitar/deshabilitar. |
| `needs_approval` | Requiere aprobación humana antes de ejecutar. |
| `timeout` | Timeout de ejecución. |
| `failure_error_function` | Cómo reportar errores al modelo. |

También existe el decorador moderno `from agents.decorators import tool` (equivalente conceptual).

#### Tool con contexto

Si el primer parámetro tipado es `RunContextWrapper[...]`, el SDK lo inyecta y **no** lo expone al modelo como argumento:

```python
@function_tool
async def call_graphql(
    ctx: RunContextWrapper[AppContext],
    query: str,
) -> str:
    ...
```

### 6.2 Registrar tools en el agente

```python
agent = Agent(
    name="GraphQL Agent",
    instructions=(
        "Eres un agente que consulta una API GraphQL. "
        "Usa call_graphql cuando necesites datos reales."
    ),
    tools=[call_graphql],
    model="gpt-4o-mini",
)
```

### 6.3 Comportamiento tras usar tools (`tool_use_behavior`)

| Valor | Efecto |
|-------|--------|
| `"run_llm_again"` (default) | Ejecuta tools → el LLM ve el resultado y responde. |
| `"stop_on_first_tool"` | El output de la primera tool es el `final_output`. |
| `StopAtTools(stop_at_tool_names=[...])` | Para si se llama alguna de esas tools. |
| Función custom | Devuelve `ToolsToFinalOutputResult` para decidir si terminar. |

```python
from agents import Agent
from agents.agent import StopAtTools

agent = Agent(
    name="Stop",
    tools=[call_graphql],
    tool_use_behavior=StopAtTools(stop_at_tool_names=["call_graphql"]),
)
```

### 6.4 Forzar uso de tools (`tool_choice`)

```python
from agents import ModelSettings

ModelSettings(tool_choice="auto")       # el modelo decide
ModelSettings(tool_choice="required")   # debe usar alguna tool
ModelSettings(tool_choice="none")       # no usar tools
ModelSettings(tool_choice="call_graphql")  # esa tool específica
```

### 6.5 Agente como tool

Un agente especializado se invoca sin ceder el control (a diferencia de handoff):

```python
especialista = Agent(
    name="GraphQL Expert",
    instructions="Especialista en armar queries GraphQL.",
)

orquestador = Agent(
    name="Orquestador",
    instructions="Si el usuario pide GraphQL, usa al experto.",
    tools=[
        especialista.as_tool(
            tool_name="graphql_expert",
            tool_description="Arma y valida queries GraphQL.",
        )
    ],
)
```

### 6.6 Hosted tools (ejemplo)

```python
from agents import Agent, WebSearchTool

agent = Agent(
    name="Buscador",
    tools=[WebSearchTool()],
)
```

---

## 7. Handoffs (multi-agente)

Transferencia de la conversación a otro agente (ese otro toma el control):

```python
booking = Agent(name="Booking", instructions="Gestiona reservas.")
refunds = Agent(name="Refunds", instructions="Gestiona reembolsos.")

triage = Agent(
    name="Triage",
    instructions=(
        "Si es reserva → booking. Si es reembolso → refunds. "
        "Si no, responde tú."
    ),
    handoffs=[booking, refunds],
)
```

Patrones típicos:

- **Manager + agents-as-tools**: el orquestador retiene el control.
- **Handoffs**: el especialista asume la conversación.

---

## 8. Ejemplo mínimo alineado al PAP

```python
# tools.py
from agents import function_tool

@function_tool
def call_graphql(query: str) -> str:
    """Ejecuta una query/mutation GraphQL contra la API del proyecto."""
    return '{"data": {}}'


# agent.py
import asyncio
from agents import Agent, Runner
from tools import call_graphql

agent = Agent(
    name="GraphQL Agent",
    instructions=(
        "Ayudas a consultar la API GraphQL del proyecto. "
        "Cuando necesites datos, usa la tool call_graphql."
    ),
    tools=[call_graphql],
    model="gpt-4o-mini",
)

async def main():
    result = await Runner.run(
        agent,
        "Trae la lista de usuarios con id y name",
    )
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. Checklist rápido

1. `OPENAI_API_KEY` configurada.
2. Crear `Agent(name=..., instructions=..., model=..., tools=...)`.
3. Definir tools con `@function_tool` + docstring claro.
4. Ejecutar con `Runner.run` / `run_sync` / `run_streamed`.
5. Leer `result.final_output`.
6. Si necesitas JSON tipado → `output_type=MiModeloPydantic`.
7. Si el modelo no llama tools → `ModelSettings(tool_choice=...)` o mejores instructions.

---

## 10. Referencias

- Agents: https://openai.github.io/openai-agents-python/agents/
- Running: https://openai.github.io/openai-agents-python/running_agents/
- Tools: https://openai.github.io/openai-agents-python/tools/
- Results: https://openai.github.io/openai-agents-python/results/
- Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- Handoffs: https://openai.github.io/openai-agents-python/handoffs/
