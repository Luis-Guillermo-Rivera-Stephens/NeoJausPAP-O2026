# Flujo del servicio PAP

El cliente **solo** habla con el agente (`POST /chat`). GraphQL **no** es una entrada del cliente: solo el agente lo usa vía `call_graphql` → `schema.execute_sync`.

```text
Cliente (test.py)
    │
    ▼
POST /chat          [AGENT]
    │
    ▼
Runner.run (openai-agents)
    │
    ▼
gpt-4o-mini (OpenAI)
    │
    ▼
call_graphql        [AGENT]
    │
    ▼
schema.execute_sync [API]
    │
    ▼
Query resolvers     [API]
    │
    ▼
Managers            [API]
    │
    ▼
db.json
```

Retorno: `db.json` → managers → resolvers → tool → Runner → `/chat` → cliente.

---

## Camino del cliente

1. Cliente hace `POST /chat` con `{ "message": "..." }`.
2. `Runner.run(agent, message)`.
3. El LLM decide si usa `call_graphql`.
4. La tool ejecuta la query GraphQL.
5. Se loguean tokens y se devuelve el reply al cliente.

## Camino de la API (solo el agente)

1. `call_graphql` → `schema.execute_sync`.
2. Resolvers en `Query` / tipos.
3. Managers leen `db.json`.
4. El JSON vuelve a la tool / LLM.

El cliente **nunca** llama a GraphQL.

---

## Secuencia con logs

| Paso | Prefijo   | Qué ocurre                                      |
|------|-----------|-------------------------------------------------|
| 1    | `[AGENT]` | `/chat` recibido (desde cliente)                |
| 2    | `[AGENT]` | Runner + LLM (`gpt-4o-mini`)                    |
| 3    | `[AGENT]` | `call_graphql` → query                          |
| 4    | `[API]`   | `Query.clients` / `service` / `appointments`…   |
| 5    | `[API]`   | Managers → `db.json` (+ relaciones anidadas)    |
| 6    | `[AGENT]` | `call_graphql` ← ok \| errores                  |
| 7    | `[AGENT]` | tokens: input / output / total / requests       |
| 8    | `[AGENT]` | `/chat` respuesta → cliente                     |

---

## Capas del código

| Capa           | Archivos                         | Rol                                      |
|----------------|----------------------------------|------------------------------------------|
| Entrada cliente| `server.py` → `/chat`            | Único endpoint que usa el cliente        |
| Agente         | `AI/agent.py`, `AI/tools.py`     | Único consumidor de GraphQL              |
| API interna    | `api/schema/*`, `api/managers/*` | Schema, resolvers, managers, `db.json`   |

---

## Comunicación Cliente ↔ Agente ↔ API

```text
Cliente ──► /chat ──► Agent ──► call_graphql / schema.execute_sync ──► Managers ──► db.json
```

No hay camino `Cliente → GraphQL`. El Agent es el único que toca GraphQL.
