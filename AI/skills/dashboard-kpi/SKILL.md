---
name: dashboard-kpi
description: Tabla de indicadores (KPIs) en Markdown con cifras de la API GraphQL. Usar cuando pidan KPIs, totales, "cuántos", un resumen en números o la tabla de indicadores de un reporte. Sin gráfica.
---

# Dashboard de indicadores

Una sola query con `call_graphql`. Postgres cuenta todas las filas del filtro; tú no bajas listas ni sumas a mano.

## Datos

Tabla completa: `kpis`. Una sola cifra: `count`.

```graphql
query {
  kpis(since: "2026-09-01T00:00:00-06:00") {
    agencies advisors clients lost connections
    conversations openWindows unanswered
    messages inbound outbound conMensaje usuarios
  }
}
```

```graphql
query { count(entity: MESSAGES, direction: "inbound", since: "2026-09-01T00:00:00-06:00") }
```

- Filtros: `since`, `until` (sobre `cat`, `until` exclusivo), `agencyId`, `connectionId`, `clientId`, `clientStatus`. `count` también acepta `direction` y `metric: COUNT_DISTINCT_CLIENTS`.
- `count(entity:)` es obligatorio en la raíz: `CRM_CLIENTS`, `MESSAGES`, `CONVERSATIONS`, `CONNECTIONS`.
- Sin fecha el corte es todo el histórico: dilo en el título.
- `openWindows` y `unanswered` son estado de ahora, ignoran el rango. Rotúlalos "(hoy)".
- `lost` usa `lostAt` si hay fechas; sin fechas, todos los perdidos.
- `null` = no aplica a ese corte. Omite esa fila.
- Nombres de asesores o números: `advisors { nickname }`, `connections { name }`. Listas cortas; solo si los vas a nombrar. `agencies { uid isActive }` no trae nombre.

## Formato

```markdown
# {título}

_{corte} · GraphQL_

## Indicadores
| Indicador | Valor |
| --- | ---: |
| Contactos | {clients} |
| Perdidos | {lost} |
| Conversaciones | {conversations} |
| Ventanas abiertas (hoy) | {openWindows} |
| Sin responder (hoy) | {unanswered} |
| Mensajes | {messages} |
| Entrantes / salientes | {inbound} / {outbound} |
| Contactos que escribieron | {usuarios} |

## Lectura
- {1–2 frases. Solo números que ya aparecen arriba.}
```

Sin Mermaid. Si GraphQL devuelve `errors`, corrige y reintenta. No inventes ceros. No listes teléfonos, correos ni textos de mensajes. Español, corto.
