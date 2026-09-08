# Strawberry GraphQL

Documentación práctica de **strawberry-graphql** (integración con **FastAPI**), alineada al stack del proyecto (`strawberry-graphql[fastapi]`, `fastapi`, `uvicorn`).

Docs oficiales: https://strawberry.rocks/docs/

---

## 1. Qué es Strawberry

Strawberry es una librería **code-first** de GraphQL para Python:

- Defines tipos, queries y mutations con clases y type hints.
- Strawberry genera el schema GraphQL.
- Con FastAPI se expone en un solo endpoint (típicamente `/graphql`).

```text
@strawberry.type / field / mutation
            ↓
    strawberry.Schema(...)
            ↓
    GraphQLRouter → FastAPI → POST /graphql
```

Sin Strawberry (o similar), FastAPI solo hace REST: no interpreta el lenguaje GraphQL.

---

## 2. Instalación

```bash
pip install "strawberry-graphql[fastapi]" fastapi uvicorn
```

Arranque típico:

```bash
uvicorn api.main:app --reload
```

---

## 3. Conceptos GraphQL (imprescindibles)

| Concepto | Rol |
|----------|-----|
| **Schema** | Contrato: qué se puede leer/escribir. |
| **Type** | Forma de un objeto (`User`, `Post`). |
| **Query** | Lecturas (equivalente a GET). |
| **Mutation** | Escrituras (crear/actualizar/borrar). |
| **Subscription** | Eventos en tiempo real (WebSocket/SSE). |
| **Field / resolver** | Función que calcula un campo. |
| **Input** | Objeto de entrada para args complejos. |
| **Enum / Union / Interface** | Modelado avanzado de tipos. |

El cliente pide exactamente los campos que necesita en un documento GraphQL; no hay una URL distinta por recurso.

---

## 4. Hello World con FastAPI

```python
# api/main.py
import strawberry
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class Query:
    @strawberry.field
    def hello(self, name: str = "mundo") -> str:
        return f"Hola, {name}"

schema = strawberry.Schema(query=Query)

graphql_app = GraphQLRouter(schema)
app = FastAPI(title="PAP GraphQL")
app.include_router(graphql_app, prefix="/graphql")
```

Abre el IDE en: `http://127.0.0.1:8000/graphql`

Query de prueba:

```graphql
query {
  hello(name: "ITESO")
}
```

---

## 5. Tipos (`@strawberry.type`)

```python
import strawberry
from typing import Optional

@strawberry.type
class User:
    id: int
    name: str
    email: str
    active: bool = True
```

### Campos con lógica (resolvers)

Si un campo no es un atributo simple, define un método/resolver:

```python
@strawberry.type
class User:
    id: int
    name: str

    @strawberry.field
    def display_name(self) -> str:
        return self.name.upper()
```

### Relaciones entre tipos

```python
POSTS = {
    1: {"id": 1, "title": "Intro GraphQL", "author_id": 1},
}

@strawberry.type
class Post:
    id: int
    title: str
    author_id: int

@strawberry.type
class User:
    id: int
    name: str

    @strawberry.field
    def posts(self) -> list[Post]:
        return [
            Post(**p)
            for p in POSTS.values()
            if p["author_id"] == self.id
        ]
```

En GraphQL el cliente puede pedir la relación en una sola query:

```graphql
{
  user(id: 1) {
    name
    posts { title }
  }
}
```

---

## 6. Query (lecturas)

```python
USERS = {
    1: {"id": 1, "name": "Ana", "email": "ana@iteso.mx"},
}

@strawberry.type
class Query:
    @strawberry.field
    def users(self) -> list[User]:
        return [User(**u) for u in USERS.values()]

    @strawberry.field
    def user(self, id: int) -> Optional[User]:
        data = USERS.get(id)
        return User(**data) if data else None
```

Reglas prácticas:

- `Query` es obligatorio en el schema.
- Cada `@strawberry.field` dentro de `Query` es una operación raíz de lectura.
- Usa `Optional[...]` cuando puede no haber resultado.

---

## 7. Mutation (escrituras)

```python
@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_user(self, name: str, email: str) -> User:
        new_id = max(USERS.keys(), default=0) + 1
        USERS[new_id] = {"id": new_id, "name": name, "email": email}
        return User(**USERS[new_id])

    @strawberry.mutation
    def delete_user(self, id: int) -> bool:
        return USERS.pop(id, None) is not None
```

```python
schema = strawberry.Schema(query=Query, mutation=Mutation)
```

Ejemplo de llamada:

```graphql
mutation {
  createUser(name: "Luis", email: "luis@iteso.mx") {
    id
    name
    email
  }
}
```

> GraphQL convierte `create_user` (Python) a `createUser` (schema) por defecto (camelCase).

---

## 8. Input types

Para no pasar muchos argumentos sueltos:

```python
@strawberry.input
class CreateUserInput:
    name: str
    email: str

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_user(self, input: CreateUserInput) -> User:
        new_id = max(USERS.keys(), default=0) + 1
        USERS[new_id] = {
            "id": new_id,
            "name": input.name,
            "email": input.email,
        }
        return User(**USERS[new_id])
```

```graphql
mutation {
  createUser(input: { name: "Ana", email: "ana@iteso.mx" }) {
    id
  }
}
```

---

## 9. Enums, Optional, listas

```python
from enum import Enum
import strawberry

@strawberry.enum
class Role(Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"

@strawberry.type
class User:
    id: int
    name: str
    role: Role
    tags: list[str]
    nickname: Optional[str] = None
```

Tipos comunes en anotaciones:

| Python | GraphQL |
|--------|---------|
| `str`, `int`, `float`, `bool` | escalares |
| `Optional[T]` / `T \| None` | `T` nullable |
| `list[T]` | `[T!]!` (según nullability) |
| `Enum` + `@strawberry.enum` | enum |

---

## 10. `Info` y context (auth, DB, etc.)

Los resolvers pueden recibir `info: strawberry.Info` para acceder al contexto de la request.

```python
import strawberry
from fastapi import Request
from strawberry.fastapi import GraphQLRouter

async def get_context(request: Request):
    return {
        "request": request,
        "user_id": request.headers.get("X-User-Id"),
    }

@strawberry.type
class Query:
    @strawberry.field
    def me(self, info: strawberry.Info) -> Optional[str]:
        return info.context.get("user_id")

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema, context_getter=get_context)
```

Casos típicos del context:

- sesión de base de datos
- usuario autenticado / JWT
- clients HTTP
- `BackgroundTasks` de FastAPI

---

## 11. Integración FastAPI (`GraphQLRouter`)

```python
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    graphql_ide="graphiql",   # "graphiql" | "apollo-sandbox" | "pathfinder" | None
    allow_queries_via_get=True,
)

app.include_router(graphql_app, prefix="/graphql")
```

Opciones clave:

| Opción | Descripción |
|--------|-------------|
| `schema` | `strawberry.Schema(...)` (obligatorio). |
| `context_getter` | Dependency de FastAPI que arma `info.context`. |
| `graphql_ide` | IDE embebido; `None` lo desactiva (producción). |
| `allow_queries_via_get` | Permite queries por GET. |
| `subscription_protocols` | Protocolos WS/SSE para subscriptions. |

---

## 12. Schema completo (plantilla)

```python
import strawberry
from typing import Optional
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

USERS: dict[int, dict] = {}

@strawberry.type
class User:
    id: int
    name: str
    email: str

@strawberry.input
class CreateUserInput:
    name: str
    email: str

@strawberry.type
class Query:
    @strawberry.field
    def users(self) -> list[User]:
        return [User(**u) for u in USERS.values()]

    @strawberry.field
    def user(self, id: int) -> Optional[User]:
        data = USERS.get(id)
        return User(**data) if data else None

@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_user(self, input: CreateUserInput) -> User:
        new_id = max(USERS.keys(), default=0) + 1
        USERS[new_id] = {
            "id": new_id,
            "name": input.name,
            "email": input.email,
        }
        return User(**USERS[new_id])

schema = strawberry.Schema(query=Query, mutation=Mutation)

app = FastAPI()
app.include_router(GraphQLRouter(schema), prefix="/graphql")
```

---

## 13. Cómo llama el cliente

### Desde el playground

```graphql
query ListUsers {
  users {
    id
    name
  }
}
```

### Por HTTP (curl)

```bash
curl -X POST http://127.0.0.1:8000/graphql \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"{ users { id name } }\"}"
```

### Con variables

```graphql
query GetUser($id: Int!) {
  user(id: $id) {
    id
    name
    email
  }
}
```

```json
{
  "query": "query GetUser($id: Int!) { user(id: $id) { id name email } }",
  "variables": { "id": 1 }
}
```

Forma del body estándar:

```json
{
  "query": "...",
  "variables": {},
  "operationName": "GetUser"
}
```

Respuesta típica:

```json
{
  "data": {
    "user": { "id": 1, "name": "Ana", "email": "ana@iteso.mx" }
  }
}
```

Si hay error:

```json
{
  "data": null,
  "errors": [{ "message": "..." }]
}
```

---

## 14. Errores

Lanza excepciones de Strawberry / GraphQL para mensajes controlados:

```python
from graphql import GraphQLError

@strawberry.field
def user(self, id: int) -> User:
    data = USERS.get(id)
    if not data:
        raise GraphQLError(f"User {id} no existe")
    return User(**data)
```

Buenas prácticas:

- No filtres stack traces ni secretos al cliente.
- Valida inputs en mutations (email, longitudes, permisos).
- Distingue “no encontrado” vs “no autorizado”.

---

## 15. Async resolvers

Strawberry soporta `async def` en fields/mutations (útil con DB async o HTTP):

```python
@strawberry.field
async def users(self) -> list[User]:
    # await db.fetch_all(...)
    return [User(**u) for u in USERS.values()]
```

---

## 16. Subscriptions (visión rápida)

Para eventos en tiempo real:

```python
import asyncio
import strawberry

@strawberry.type
class Subscription:
    @strawberry.subscription
    async def count(self, target: int = 5) -> int:
        for i in range(target):
            yield i
            await asyncio.sleep(0.5)

schema = strawberry.Schema(query=Query, subscription=Subscription)
```

Requieren ASGI con WebSockets (Uvicorn lo soporta) y cliente que hable el protocolo de subscriptions.

---

## 17. N+1 y rendimiento

Problema clásico: un resolver `posts` por cada `user` dispara muchas queries a BD.

Mitigaciones:

- DataLoaders (batching/caching por request).
- Joins / queries agregadas cuando el patrón es predecible.
- Paginar listas (`limit`/`offset` o cursores).

Ejemplo de paginación simple:

```python
@strawberry.field
def users(self, limit: int = 20, offset: int = 0) -> list[User]:
    items = list(USERS.values())[offset : offset + limit]
    return [User(**u) for u in items]
```

---

## 18. Naming y schema SDL

- En Python: `snake_case` (`create_user`, `display_name`).
- En GraphQL: suele verse `camelCase` (`createUser`, `displayName`).

Puedes inspeccionar el schema generado:

```python
print(schema.as_str())
```

O usar la introspección del playground.

---

## 19. REST vs GraphQL (para el PAP)

| REST | GraphQL (Strawberry) |
|------|----------------------|
| Muchas rutas | Un endpoint `/graphql` |
| El servidor decide la forma del JSON | El cliente elige campos |
| Over/under-fetching común | Fetch preciso |
| Versionar rutas (`/v1/...`) | Evoluciona el schema con cuidado |
| Ideal para recursos CRUD simples | Ideal cuando el cliente necesita formas flexibles de datos |

Para un agente de IA (Agents SDK), GraphQL es conveniente: la tool puede enviar una `query` string arbitraria en lugar de muchas tools REST distintas.

---

## 20. Checklist de una API Strawberry

1. Modelar tipos con `@strawberry.type`.
2. Definir lecturas en `Query`.
3. Definir escrituras en `Mutation` (si aplica).
4. Usar `@strawberry.input` para payloads limpios.
5. Crear `schema = strawberry.Schema(...)`.
6. Montar `GraphQLRouter` en FastAPI bajo `/graphql`.
7. Inyectar auth/DB con `context_getter`.
8. Probar en el IDE y con `curl`/cliente HTTP.
9. En producción: desactivar IDE (`graphql_ide=None`), validar inputs, controlar errores.

---

## 21. Referencias

- Schema basics: https://strawberry.rocks/docs/general/schema-basics
- FastAPI integration: https://strawberry.rocks/docs/integrations/fastapi
- Types: https://strawberry.rocks/docs/types/schema
- Mutations: https://strawberry.rocks/docs/general/mutations
