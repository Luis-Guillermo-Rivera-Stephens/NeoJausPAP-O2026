# PAP — Agente de IA sobre GraphQL

Un agente de IA que responde preguntas en lenguaje natural consultando una base de datos.
El cliente pregunta *"¿cuántos usuarios me escribieron la semana pasada?"*, el agente traduce eso
a una query GraphQL, la ejecuta y responde en español.

```
Cliente  →  POST /chat  →  Agente (gpt-4o-mini)  →  GraphQL  →  Postgres
```

La base de datos es una **versión reducida del esquema real de la empresa**, con datos
**100% inventados**. Los nombres de tabla y columna son los de producción: lo que aprendan aquí
sirve tal cual allá.

---

## 1. Arranque

Necesitan **Docker** y **Python 3.10+**.

```bash
# 1. Dependencias de Python
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configuración
cp .env.example .env              # y pongan su OPENAI_API_KEY dentro

# 3. Base de datos (se crea y se siembra sola la primera vez)
docker compose up -d --wait

# 4. Comprobar que quedó bien
docker exec -it pap-postgres psql -U pap -d papdb -c "SELECT * FROM pap_resumen();"
```

Debe salir esto:

```
             tabla             | filas
-------------------------------+-------
 real_state_agencies           |     2
 clients (asesores)            |     4
 crm_clients                   |    50
 whatsapp_connection           |     3
 whatsapp_conversation         |    66
 whatsapp_message              |  1660
 whatsapp_conversation_episode |     9
```

Levantar el servidor y hablarle al agente:

```bash
uvicorn server:app --reload       # API en http://localhost:8000
python test.py                    # chat por terminal, en otra pestaña
```

### Conexión a la base

```
postgresql://pap:pap@localhost:5433/papdb
```

| Host | Puerto | Base | Usuario | Contraseña |
|---|---|---|---|---|
| `localhost` | **5433** | `papdb` | `pap` | `pap` |

> El puerto es **5433**, no el 5432 de siempre. El 5432 suele estar ocupado por otro Postgres.

Abrir una consola SQL: `docker exec -it pap-postgres psql -U pap -d papdb`

---

## 2. El esquema

El dominio es una **inmobiliaria que atiende clientes por WhatsApp**. Hay agencias, cada agencia
tiene números de WhatsApp Business, la gente les escribe, y esos contactos viven en un CRM.

```mermaid
erDiagram
    real_state_agencies ||--o{ whatsapp_connection : "tiene números"
    real_state_agencies ||--o{ crm_clients : "tiene contactos"
    whatsapp_connection ||--o{ whatsapp_conversation : "recibe en"
    crm_clients ||--o{ whatsapp_conversation : "participa en"
    whatsapp_conversation ||--o{ whatsapp_message : "contiene"
    whatsapp_conversation ||--o{ whatsapp_conversation_episode : "resumida en"
    clients ||--o{ crm_clients : "atiende"

    real_state_agencies {
        uuid uid PK
        varchar name
        varchar timezone
    }
    clients {
        uuid uid PK
        varchar nickname
        varchar first_name
    }
    crm_clients {
        uuid uid PK
        uuid agency_id FK
        uuid assigned_to FK
        varchar first_name
        varchar primary_phone
        varchar wa_id
        enum client_status
        timestamptz cat
    }
    whatsapp_connection {
        uuid uid PK
        uuid agency_id FK
        varchar phone_e164
        varchar name
    }
    whatsapp_conversation {
        uuid uid PK
        uuid connection_id FK
        uuid client_id FK
        timestamptz cat
    }
    whatsapp_message {
        uuid uid PK
        uuid conversation_id FK
        varchar direction
        jsonb content
        timestamptz cat
    }
    whatsapp_conversation_episode {
        uuid uid PK
        uuid conversation_id FK
        text summary
        jsonb key_topics
    }
```

El camino que van a recorrer casi siempre:

```
whatsapp_connection   ← "mi número"
        ↓ connection_id
whatsapp_conversation ──client_id──►  crm_clients   ← "el usuario que escribe"
        ↓ conversation_id
whatsapp_message      ← direction, content, cat
```

### ⚠️ Dos trampas que hay que leer antes de escribir una query

**1. Las columnas no se llaman como esperan.**

| Columna | Qué es |
|---|---|
| `uid` | La llave primaria (uuid). **No** se llama `id` |
| `cat` | *created at* — cuándo se creó la fila |
| `uat` | *updated at* |

**No existe `created_at`, ni `sent_at`, ni `timestamp`.** La fecha de un mensaje es `cat`.

**2. `clients` no es la gente que escribe.**

| Tabla | Quién es |
|---|---|
| `clients` | Los **asesores** de la inmobiliaria — los que contestan |
| `crm_clients` | Los **contactos** — la gente que escribe por WhatsApp |

`whatsapp_conversation.client_id` apunta a **`crm_clients.uid`**, no a `clients.uid`.
Confundirlas **no da error**: devuelve números equivocados en silencio. Cuando la pregunta es
"cuántos usuarios escribieron", el usuario es un `crm_clients`.

### Referencia de columnas

<details>
<summary><b>real_state_agencies</b> — la agencia (2 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `cat` / `uat` | timestamptz | creación / actualización |
| `name` | varchar(128) | |
| `timezone` | varchar(64) | `America/Mexico_City`, `America/Tijuana` |
| `is_active` | boolean | |
</details>

<details>
<summary><b>clients</b> — los asesores (4 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `cat` / `uat` | timestamptz | |
| `nickname` | varchar(128) | NOT NULL |
| `first_name`, `first_last_name` | varchar | |
| `email`, `phone_number` | varchar | |
</details>

<details>
<summary><b>crm_clients</b> — los contactos que escriben (50 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `cat` / `uat` | timestamptz | `cat` = cuándo entró el lead |
| `agency_id` | uuid | FK → `real_state_agencies` |
| `created_by`, `assigned_to` | uuid | FK → `clients` (el asesor) |
| `first_name`, `first_last_name`, `preferred_name` | varchar | |
| `primary_email`, `primary_phone` | varchar | |
| `phone_country_code` | varchar(4) | default `52` |
| `preferred_contact_method` | enum | `email`, `phone`, `whatsapp` |
| `client_status` | enum | `new`, `contacted`, `active`, `closed`, `lost`, `inactive`, `archived` |
| `client_type` | enum | `buyer`, `seller`, `renter`, `landlord`, `investor`, `developer`, `other`, `agent` |
| `lead_source` | varchar | `facebook_ads`, `portal_inmuebles24`, `referido`… |
| `tags` | text[] | arreglo de Postgres |
| `comments` | varchar(2048) | |
| `is_deleted` | boolean | borrado lógico: casi siempre hay que filtrar `= false` |
| `wa_id` | varchar(32) | su número en WhatsApp |
| `wa_profile_name` | varchar(128) | el nombre que trae su perfil |
| `is_lost`, `lost_reason`, `lost_at` | | por qué se perdió el lead |
</details>

<details>
<summary><b>whatsapp_connection</b> — "mi número" (3 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `agency_id` | uuid | FK → `real_state_agencies` |
| `phone_e164` | varchar(20) | **el número: `+523300000001`** |
| `display_phone` | varchar(20) | el mismo, formateado |
| `name` | varchar(60) | `Ventas Guadalajara`, `Soporte Guadalajara`, `Ventas Tijuana` |
| `waba_id`, `phone_number_id` | varchar | ids de la API de Meta |
| `is_active`, `status` | | `connected`, `paused`, `disconnected`… |

La agencia 1 tiene **dos** números. Por eso un mismo contacto puede tener dos conversaciones.
</details>

<details>
<summary><b>whatsapp_conversation</b> — une número ↔ contacto (66 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `connection_id` | uuid | FK → `whatsapp_connection` |
| `client_id` | uuid | FK → **`crm_clients`** ⚠️ |
| `agency_id` | uuid | FK → `real_state_agencies` |
| `cat` | timestamptz | |
| `conversation_category` | varchar(16) | `marketing`, `service`, `utility`, `referral` |
| `window_expires_at` | timestamptz | la ventana de 24 h de WhatsApp |
| `last_read_at` | timestamptz | |

`UNIQUE (connection_id, client_id)`: un contacto tiene **una** conversación por número.
</details>

<details>
<summary><b>whatsapp_message</b> — los mensajes (1,660 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `cat` | timestamptz | **la fecha del mensaje** |
| `conversation_id` | uuid | FK → `whatsapp_conversation` |
| `connection_id` | uuid | FK → `whatsapp_connection` |
| `direction` | varchar(8) | `inbound` (escribió el contacto) / `outbound` (respondió el asesor) |
| `content` | jsonb | **el texto va aquí**: `content->>'body'` |
| `message_type` | varchar(16) | `text`, `image`, `audio`, `document`, `video`, `location`, `template` |
| `m_status` | varchar(16) | `pending`, `sent`, `delivered`, `read`, `failed` |
| `wamid` | varchar(128) | id del mensaje en Meta (único) |
| `sent_by` | uuid | FK → `clients`; `NULL` en los entrantes |

`direction`, `message_type` y `m_status` son `varchar` **sin CHECK** — igual que en producción,
donde se validan sólo desde el código. Postgres aquí no los va a corregir.
</details>

<details>
<summary><b>whatsapp_conversation_episode</b> — resúmenes de IA (9 filas)</summary>

| Columna | Tipo | |
|---|---|---|
| `uid` | uuid | PK |
| `conversation_id` | uuid | FK → `whatsapp_conversation` |
| `window_from`, `window_to` | timestamptz | periodo que resume |
| `summary` | text | el resumen |
| `key_topics` | jsonb | `["precio", "disponibilidad"]` |
| `model`, `cost_usd_micros` | | qué modelo lo generó y cuánto costó |

Para un agente suele ser más barato leer esto que 40 mensajes sueltos.
</details>

---

## 3. La query que hay que saber hacer

> *"¿Cuántos usuarios le escribieron a mi número la semana pasada?"*

```sql
SELECT count(DISTINCT wc.client_id) AS usuarios
FROM whatsapp_message wm
JOIN whatsapp_conversation wc ON wc.uid = wm.conversation_id
JOIN whatsapp_connection wcx  ON wcx.uid = wc.connection_id
WHERE wcx.phone_e164 = '+523300000001'
  AND wm.direction = 'inbound'
  AND wm.cat >= now() - interval '7 days';
```

Da **10**. Las tres decisiones que importan:

1. `DISTINCT wc.client_id` — la pregunta dice *usuarios*, no *mensajes*. Sin esto cuentan mensajes.
2. `direction = 'inbound'` — *escribieron ellos*. Sin esto cuentan también las respuestas.
3. `phone_e164` — *mi* número. Hay tres en la base; sin esto se mezclan.

Hay **9 queries más** (mensajes por día, conversaciones sin responder, búsqueda de texto dentro
del jsonb, cortes por zona horaria, `EXPLAIN`) en **[`documentacion/BaseDeDatos.md`](documentacion/BaseDeDatos.md)**.

---

## 4. Qué hay que construir

Hoy la API lee de un archivo plano, `api/db.json`, con datos de un salón de belleza. **Ese es el
trabajo: que deje de leer el JSON y lea Postgres**, y que los tipos de GraphQL reflejen las tablas
de arriba.

0. **Instalen el driver**: `requirements.txt` todavía no trae con qué hablarle a Postgres.

   ```bash
   pip install "psycopg[binary]" psycopg_pool
   ```

   Cuando lo tengan funcionando, agréguenlo a `requirements.txt`.

1. `api/managers/*.py` — hoy hacen `load_db()` sobre el JSON. Deben consultar Postgres.
2. `api/schema/*.py` — los tipos (`Client`, `Service`, `Appointment`) son del dominio viejo.
   Hay que modelar `CrmClient`, `Conversation`, `Message`.
3. `AI/agent.py` — las `instructions` describen el esquema viejo. Hay que decirle al agente qué
   puede consultar ahora.

El flujo **no cambia**: el cliente sólo habla con `/chat`, y sólo el agente toca GraphQL
(ver [`documentacion/Flujo.md`](documentacion/Flujo.md)).

Dos cosas con las que se van a topar:

- **N+1** — si cada resolver abre su propia consulta, pedir 50 contactos con sus mensajes lanza
  51 queries. `GraphQL.md` habla de DataLoaders.
- **Conexiones** — abrir una conexión por resolver es caro. Conviene un pool (`psycopg_pool`)
  creado una sola vez al arrancar.

---

## 5. Mapa del repo

```
server.py                  FastAPI: POST /chat y /graphql
test.py                    cliente de terminal para hablarle al agente
AI/
  agent.py                 definición del agente y sus instructions
  tools.py                 call_graphql: la única herramienta del agente
api/
  db.json                  la "base" vieja  →  hay que reemplazarla
  managers/                leen db.json     →  deben leer Postgres
  schema/                  tipos y resolvers de Strawberry
db/
  init/01_schema.sql       tablas, enums, índices  (se aplica solo)
  init/02_seed.sql         los datos dummy         (se aplica solo)
  init/03_helpers.sql      pap_resumen(), pap_refresh_timestamps()
docker-compose.yml         el Postgres
documentacion/
  BaseDeDatos.md           ← la base a fondo, con 10 queries de ejemplo
  Flujo.md                 ← cómo viaja una petición por el sistema
  GraphQL.md               ← manual de Strawberry
  AgentsSDK.md             ← manual de openai-agents
```

---

## 6. Problemas comunes

**`FATAL: database "papdb" does not exist`**
Se conectaron mientras aún sembraba. Mientras lo hace, Postgres levanta un servidor temporal que
ya responde en el puerto. Usen `docker compose up -d --wait`, que espera al healthcheck de verdad.

**"La semana pasada" no devuelve nada**
Los datos se sembraron relativos al día en que crearon el volumen y ya envejecieron. Re-anclen todo
a hoy sin perder nada:

```sql
SELECT pap_refresh_timestamps();
```

**Quiero empezar de cero**

```bash
docker compose down -v && docker compose up -d --wait
```

Borra el volumen y vuelve a sembrar. Los datos son deterministas: sale **exactamente** la misma
base, siempre, en todas las máquinas. Si dos personas corren la misma query, el resultado debe
coincidir al dígito.

**El puerto 5433 ya está ocupado**
Cambien el mapeo en `docker-compose.yml` (`"5434:5432"`) y el `DATABASE_URL` del `.env`.

---

## 7. Sobre los datos

Todo inventado. Nombres, teléfonos, mensajes: generados por aritmética determinista. **Ninguna
fila viene de la base real de la empresa** — los datos de clientes reales no salen de ahí.
