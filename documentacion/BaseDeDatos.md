# Base de datos del PAP

Postgres 15 en Docker, con una **version reducida del esquema real** de la empresa y datos
**100% inventados**. Sustituye a `api/db.json`.

La idea: que las queries que escriban aqui sean casi identicas a las que correrian contra
produccion. Por eso los nombres de tabla y de columna son los reales; lo unico que se recorto es
la cantidad (7 tablas en vez de 151, 24 columnas en `crm_clients` en vez de 64).

---

## 1. Levantarla

```bash
docker compose up -d --wait
```

La primera vez tarda un poco: crea el volumen, aplica el esquema y siembra los datos solos.

El `--wait` no es un adorno: mientras siembra, Postgres levanta un servidor temporal interno, asi
que el puerto responde **antes** de que `papdb` exista. Si se conectan sin esperar, se van a topar
con `FATAL: database "papdb" does not exist`. Con `--wait`, docker espera al healthcheck de verdad.

Para comprobar que quedo bien:

```bash
docker exec -it pap-postgres psql -U pap -d papdb -c "SELECT * FROM pap_resumen();"
```

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

Otros comandos:

```bash
docker compose down        # apagar, conservando datos
docker compose down -v     # borrar TODO; el siguiente `up` vuelve a sembrar
docker exec -it pap-postgres psql -U pap -d papdb   # abrir una consola SQL
```

### Conexion

```
postgresql://pap:pap@localhost:5433/papdb
```

| | |
|---|---|
| Host | `localhost` |
| Puerto | **5433** (no 5432) |
| Base | `papdb` |
| Usuario / contrasena | `pap` / `pap` |

> **Por que 5433:** el puerto 5432 de esta maquina lo ocupa el Postgres de trabajo de la empresa.
> Esta base usa otro puerto, otro contenedor (`pap-postgres`) y otro volumen
> (`pap-postgres-data`), asi que no hay forma de que se toquen.

Desde Python:

```python
import psycopg  # pip install "psycopg[binary]"

with psycopg.connect("postgresql://pap:pap@localhost:5433/papdb") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM whatsapp_message")
        print(cur.fetchone()[0])
```

---

## 2. Dos convenciones que hay que saber antes de escribir una query

### 2.1 `uid`, `cat`, `uat`

No es la nomenclatura habitual. En este esquema:

| Columna | Significa |
|---|---|
| `uid` | La llave primaria (uuid). **No** se llama `id` |
| `cat` | *created at* — cuando se creo la fila |
| `uat` | *updated at* |

**No existe `created_at`, ni `sent_at`, ni `timestamp`.** La fecha de un mensaje es `cat`.
Todos los timestamps son `timestamptz` (con zona horaria), igual que en produccion.

### 2.2 `clients` NO es la tabla de los que escriben

Esta es la trampa mas facil de este esquema, y es peligrosa porque **no da error**: devuelve
numeros equivocados en silencio.

| Tabla | Quien es |
|---|---|
| `clients` | Los **asesores** de la inmobiliaria. Usuarios de la plataforma, los que contestan |
| `crm_clients` | Los **contactos / leads**: la gente que escribe por WhatsApp |

`whatsapp_conversation.client_id` apunta a **`crm_clients.uid`**, no a `clients.uid`.
Cuando la pregunta es "cuantos usuarios escribieron", el usuario es un `crm_clients`.

---

## 3. Como se conectan las tablas

```
real_state_agencies          la agencia (tenant). Tiene timezone
        │ agency_id
        ▼
whatsapp_connection          "MI NUMERO" de WhatsApp Business (phone_e164)
        │ connection_id
        ▼
whatsapp_conversation ───client_id──►  crm_clients      el contacto que escribe
        │                              UNIQUE(connection_id, client_id)
        │ conversation_id
        ▼
whatsapp_message             direction, content (jsonb), cat
```

Puntos a notar:

- Un contacto tiene **una conversacion por numero**. La agencia 1 tiene dos numeros, asi que
  un mismo contacto puede aparecer en dos conversaciones distintas.
- El texto del mensaje **no esta en una columna de texto**: vive dentro de `content`, que es
  `jsonb`. Se lee con `content->>'body'`.
- `direction` es `'inbound'` (lo escribio el contacto) u `'outbound'` (lo escribio el asesor).

### Valores validos

Estas columnas son `varchar` **sin CHECK**, igual que en produccion: alla se validan solo desde
el codigo de la aplicacion. Se replico tal cual para que el comportamiento coincida.

| Columna | Valores |
|---|---|
| `whatsapp_message.direction` | `inbound`, `outbound` |
| `whatsapp_message.message_type` | `text`, `image`, `audio`, `document`, `video`, `location`, `template` |
| `whatsapp_message.m_status` | `pending`, `sent`, `delivered`, `read`, `failed` |

Los enums de verdad (estos si los valida Postgres) son `crm_client_status_v1`,
`crm_client_types_v1`, `preferred_contact_methods_v1` y `lost_reasons_v1`.

---

## 4. Queries de ejemplo

De menor a mayor dificultad. Conviene correrlas y entenderlas antes de conectar el agente.

### 4.1 La pregunta del enunciado

> *"¿Cuantos usuarios le escribieron a mi numero la semana pasada?"*

```sql
SELECT count(DISTINCT wc.client_id) AS usuarios
FROM whatsapp_message wm
JOIN whatsapp_conversation wc ON wc.uid = wm.conversation_id
JOIN whatsapp_connection wcx  ON wcx.uid = wc.connection_id
WHERE wcx.phone_e164 = '+523300000001'
  AND wm.direction = 'inbound'
  AND wm.cat >= now() - interval '7 days';
```

Tres decisiones que hay que justificar:

1. `DISTINCT wc.client_id` — la pregunta dice *usuarios*, no *mensajes*. Sin el `DISTINCT`
   cuentan mensajes y el numero sale inflado.
2. `direction = 'inbound'` — *escribieron ellos*. Sin este filtro se cuentan tambien las
   respuestas de los asesores.
3. `phone_e164` — *mi* numero. Hay tres numeros en la base; sin este filtro se mezclan.

### 4.2 Los tres numeros, lado a lado

```sql
SELECT wcx.name, wcx.phone_e164,
       count(DISTINCT wc.client_id) FILTER (WHERE wm.direction = 'inbound') AS usuarios,
       count(*) FILTER (WHERE wm.direction = 'inbound') AS mensajes_entrantes
FROM whatsapp_connection wcx
LEFT JOIN whatsapp_conversation wc ON wc.connection_id = wcx.uid
LEFT JOIN whatsapp_message wm
       ON wm.conversation_id = wc.uid AND wm.cat >= now() - interval '7 days'
GROUP BY wcx.name, wcx.phone_e164
ORDER BY usuarios DESC;
```

### 4.3 Mensajes por dia

```sql
SELECT date_trunc('day', cat)::date AS dia,
       count(*) FILTER (WHERE direction = 'inbound')  AS entrantes,
       count(*) FILTER (WHERE direction = 'outbound') AS salientes
FROM whatsapp_message
WHERE cat >= now() - interval '14 days'
GROUP BY 1 ORDER BY 1;
```

### 4.4 Contactos nuevos por semana

```sql
SELECT date_trunc('week', cat)::date AS semana, count(*) AS nuevos
FROM crm_clients
GROUP BY 1 ORDER BY 1 DESC LIMIT 8;
```

### 4.5 Quien escribio mas

```sql
SELECT c.first_name || ' ' || c.first_last_name AS contacto,
       c.primary_phone, c.client_status,
       count(*) AS mensajes_enviados
FROM whatsapp_message wm
JOIN whatsapp_conversation wc ON wc.uid = wm.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id
WHERE wm.direction = 'inbound'
GROUP BY 1, 2, 3
ORDER BY mensajes_enviados DESC
LIMIT 10;
```

### 4.6 Conversaciones sin responder

El ultimo mensaje lo escribio el contacto y nadie contesto. `DISTINCT ON` es especifico de
Postgres y resuelve "la fila mas reciente por grupo" sin subqueries.

```sql
SELECT c.first_name || ' ' || c.first_last_name AS contacto,
       ultimo.cat AS ultimo_mensaje,
       age(now(), ultimo.cat) AS lleva_esperando,
       ultimo.content->>'body' AS texto
FROM (
    SELECT DISTINCT ON (conversation_id) conversation_id, cat, direction, content
    FROM whatsapp_message
    ORDER BY conversation_id, cat DESC
) AS ultimo
JOIN whatsapp_conversation wc ON wc.uid = ultimo.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id
WHERE ultimo.direction = 'inbound'
ORDER BY ultimo.cat DESC;
```

### 4.7 Buscar dentro del texto del mensaje

```sql
SELECT c.first_name, wm.cat, wm.content->>'body' AS texto
FROM whatsapp_message wm
JOIN whatsapp_conversation wc ON wc.uid = wm.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id
WHERE wm.content->>'body' ILIKE '%infonavit%'
ORDER BY wm.cat DESC;
```

### 4.8 "La semana pasada" bien hecho: con zona horaria

Las dos agencias estan en husos distintos (`America/Mexico_City` y `America/Tijuana`). Un corte
en UTC parte el dia en el lugar equivocado. Lo correcto es cortar en la hora **local de la
agencia**, que por eso se guarda en `real_state_agencies.timezone`:

```sql
SELECT a.name, a.timezone,
       count(DISTINCT wc.client_id) AS usuarios
FROM whatsapp_message wm
JOIN whatsapp_conversation wc ON wc.uid = wm.conversation_id
JOIN real_state_agencies a    ON a.uid = wc.agency_id
WHERE wm.direction = 'inbound'
  AND (wm.cat AT TIME ZONE a.timezone)
      >= date_trunc('day', (now() AT TIME ZONE a.timezone)) - interval '7 days'
GROUP BY a.name, a.timezone;
```

Comparen el resultado con el de 4.1: la diferencia es justo el efecto del huso horario.

### 4.9 Resumenes de IA ya calculados

`whatsapp_conversation_episode` guarda resumenes generados por un modelo. Para un agente suele
ser mejor leer esto que 40 mensajes sueltos:

```sql
SELECT c.first_name, e.window_from::date, e.window_to::date,
       e.summary, e.key_topics, e.model
FROM whatsapp_conversation_episode e
JOIN whatsapp_conversation wc ON wc.uid = e.conversation_id
JOIN crm_clients c ON c.uid = wc.client_id
ORDER BY e.window_to DESC;
```

### 4.10 Mirar como Postgres ejecuta la query

```sql
EXPLAIN ANALYZE
SELECT count(*) FROM whatsapp_message WHERE cat >= now() - interval '7 days';
```

Da un **Seq Scan**: no hay indice suelto sobre `cat`. Los indices son
`(conversation_id, cat)` y `(connection_id, cat)`, asi que sirven cuando la query acota primero
por conversacion o por conexion — como hace 4.1. En produccion pasa exactamente lo mismo, con
millones de filas. Vale la pena comparar el `EXPLAIN` de esta query con el de 4.1.

---

## 5. Si "la semana pasada" deja de traer datos

Los datos se sembraron relativos al momento en que se creo el volumen. Si la base lleva semanas
levantada, la ventana de 7 dias se queda atras y sale vacia. Para re-anclar todo a hoy sin
reconstruir:

```sql
SELECT pap_refresh_timestamps();
```

Recorre todos los timestamps hacia adelante conservando las distancias entre eventos, asi que
las queries vuelven a dar resultados equivalentes. La alternativa es
`docker compose down -v && docker compose up -d`.

---

## 6. Que se recorto del esquema real (y por que)

| | Produccion | Aqui |
|---|---|---|
| Tablas | 151 | 7 |
| Tipos enum | 53 | 4 |
| Columnas en `crm_clients` | 64 | 24 |
| Extensiones | 7 (incluida PostGIS) | 1 (`uuid-ossp`) |

Que se quito y la razon:

- **Las columnas de domicilio** de `crm_clients` (calle, colonia, CP, estado) y el enum
  `mexican_states` con sus 32 valores: no aportan nada a analitica de WhatsApp.
- **Datos fiscales y de identidad** (CURP, RFC, clave de elector, ingresos): son datos
  personales sensibles y no hacen falta para el ejercicio.
- **`whatsapp_connection.access_token_encrypted`**: es un secreto real. No tiene por que
  existir en una base de practica.
- **PostGIS**: ninguna de estas siete tablas usa geometrias, asi que la imagen `alpine` basta
  (mucho mas ligera, y nativa en Apple Silicon).

Lo que **no** se cambio, a proposito: nombres de tabla y columna, tipos, la convencion
`uid`/`cat`/`uat`, los valores exactos de los enums, las llaves foraneas, y los indices
relevantes. Tambien se conservo la *ausencia* de CHECKs en `direction` y `m_status`, para que la
base se comporte como la de verdad.

### Sobre los datos

Todos inventados, generados por aritmetica determinista (sin `random()`): la base es identica
para todos, asi que dos personas pueden comparar el resultado de una query y debe coincidir al
digito. **Ni una fila viene de produccion ni de dev** — los datos reales de clientes no salen de
ahi, y esa regla no se negocia.

---

## 7. Siguiente paso

Esta base solo reemplaza a `db.json`. Falta lo suyo: que `api/managers/*.py` dejen de leer el
JSON y consulten Postgres, y que los tipos de `api/schema/*` reflejen estas tablas. El flujo
(`Cliente → /chat → agente → call_graphql → resolvers`) descrito en `Flujo.md` no cambia; lo
unico que cambia es de donde salen los datos.

Dos cosas que van a encontrarse en el camino:

- **N+1**: si cada resolver abre su propia consulta, una query de GraphQL que pida 50 contactos
  con sus mensajes lanza 51 consultas. `GraphQL.md` ya habla de DataLoaders.
- **Conexiones**: abrir una conexion nueva por resolver es caro. Conviene un pool
  (`psycopg_pool`) creado una sola vez al arrancar el servidor.
