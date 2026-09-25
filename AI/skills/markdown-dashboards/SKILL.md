---
name: markdown-dashboards
description: Genera dashboards y gráficas en Markdown (KPIs, barras Unicode y Mermaid) solo con cifras de la API GraphQL real de WhatsApp/CRM. Usar cuando pidan dashboard, gráfica, gráfico, reporte visual, KPIs, barras, pastel, tendencia, comparativa o un resumen con números del negocio.
---

# Dashboards en Markdown

Responde con un dashboard en Markdown. Cada cifra sale de `call_graphql` (POST `http://localhost:8000/graphql`). Si la consulta falla o no hay filas, no hay gráfica.

## Datos

Usa solo `agregado`. Postgres cuenta todas las filas que cumplan el filtro; la respuesta son cubetas (`key`, `n`), no listas de contactos ni mensajes. No pidas `crmClients`, `conversations` ni `messages` para un dashboard.

Filtros opcionales: `since`, `until` (sobre `cat`, `until` exclusivo), `agencyId`, `clientId`, `connectionId`, `clientStatus`, `direction`. Sin filtro de fecha el corte es todo el histórico: dilo en el título.

| entity | groupBy válido |
|---|---|
| `CRM_CLIENTS` | `NONE` `CLIENT_STATUS` `DAY` `WEEK` `ADVISOR` |
| `MESSAGES` | `NONE` `DIRECTION` `MESSAGE_TYPE` `M_STATUS` `DAY` `WEEK` `CONNECTION` `CLIENT_STATUS` |
| `CONVERSATIONS` | `NONE` `CONVERSATION_CATEGORY` `DAY` `WEEK` `CONNECTION` `CLIENT_STATUS` |

`metric`: `COUNT` (default) o `COUNT_DISTINCT_CLIENTS`. `direction` solo con `MESSAGES`. `connectionId` no aplica a `CRM_CLIENTS`.

```graphql
query {
  agregado(entity: CRM_CLIENTS, groupBy: CLIENT_STATUS, since: "2026-09-01T00:00:00-06:00") {
    key
    n
  }
}
```

```graphql
query {
  agregado(entity: MESSAGES, groupBy: DIRECTION, metric: COUNT) { key n }
}
```

`clientStatus`: new, contacted, active, closed, lost, inactive, archived. `direction`: inbound, outbound. Las fechas de `DAY`/`WEEK` van en `America/Mexico_City`. Si GraphQL devuelve `errors`, corrige y reintenta. No inventes ceros para claves que no vinieron.

## Formato de respuesta

Una sola respuesta, en este orden. Español, corto.

```markdown
# {título}

_{corte} · GraphQL_

## Indicadores
| Indicador | Valor |
| --- | ---: |
| {nombre} | {n} |

## {nombre de la serie}

| Categoría | n | % | |
| --- | ---: | ---: | --- |
| {cat} | {n} | {0.0} | {barra} |

```mermaid
{pie o xychart-beta}
```

## Lectura
- {1–3 frases. Solo números que ya aparecen arriba.}
```

Reglas de la gráfica:

- Un solo número: solo la tabla de indicadores. Sin Mermaid.
- Categorías (máx. 8; el resto se suma en `otros`), ordenadas de mayor a menor: tabla con barra + `pie`.
- Serie de tiempo, orden cronológico: tabla con barra + `xychart-beta`.
- Dos series (p. ej. inbound/outbound): una tabla con dos columnas de barras. Sin pie.

Barra: 16 celdas. `bloques = round(n / max * 16)`. Si `n > 0` y el redondeo da 0, usa 1. Carácter `█`, resto espacios. `max` es el mayor de esa columna. Porcentaje con un decimal; si el total es 0, omite la gráfica y escribe `Sin datos para ese corte.`

```mermaid
pie showData
    title Leads por estatus
    "active" : 12
    "new" : 4
```

```mermaid
xychart-beta
    title "Mensajes por día"
    x-axis ["01-09", "02-09", "03-09"]
    y-axis "mensajes" 0 --> 20
    bar [4, 9, 12]
```

En el pie y en el `bar []` van los mismos enteros que en la tabla. El eje Y llega al máximo de la serie, redondeado hacia arriba. Etiquetas cortas, sin saltos de línea.
