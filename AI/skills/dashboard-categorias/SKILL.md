---
name: dashboard-categorias
description: Desglose por categoría en Markdown (tabla con barras + pastel Mermaid) con cifras de la API GraphQL. Usar cuando pidan distribución, "por estatus", "por asesor", "por tipo", "por fuente", "por número", pastel, barras o ranking de categorías.
---

# Dashboard de categorías

Una sola query con `call_graphql`: `countBy`. Devuelve todas las cubetas de la dimensión, de mayor a menor. Pide el desglose completo: no filtres un estatus si no lo pidieron.

## Datos

```graphql
query {
  countBy(entity: CRM_CLIENTS, by: CLIENT_STATUS, since: "2026-09-01T00:00:00-06:00") { key n }
}
```

| entity | by |
|---|---|
| `CRM_CLIENTS` | `CLIENT_STATUS` `CLIENT_TYPE` `LEAD_SOURCE` `LOST_REASON` `IS_LOST` `PREFERRED_CONTACT` `ADVISOR` |
| `MESSAGES` | `DIRECTION` `MESSAGE_TYPE` `M_STATUS` `ERROR_CODE` `SENT_BY` `CONNECTION` `CLIENT_STATUS` |
| `CONVERSATIONS` | `CONVERSATION_CATEGORY` `CONNECTION` `CLIENT_STATUS` |
| `CONNECTIONS` | `STATUS` `IS_ACTIVE` |

- `metric`: `COUNT` (default) o `COUNT_DISTINCT_CLIENTS`. Filtros: `since`, `until`, `agencyId`, `clientStatus`, `direction` (solo mensajes), `connectionId`, `clientId`.
- `DAY`/`WEEK` no van aquí: eso es `countOverTime` (skill dashboard-tendencia).
- Segundo corte dentro de cada categoría: anida. La cubeta padre ya acota al hijo; no repitas `entity` si es la misma.

```graphql
query {
  countBy(entity: CRM_CLIENTS, by: ADVISOR) {
    key n
    countBy(by: CLIENT_STATUS) { key n }
    mensajes: count(entity: MESSAGES)
  }
}
```

- Tasa (entrega, lectura, pérdida): divide cubetas de la misma serie. `read / total`.
- Embudo: ordena `CLIENT_STATUS` new → contacted → active → closed.

## Formato

```markdown
# {título}

_{corte} · GraphQL_

## {nombre de la serie}

| Categoría | n | % | |
| --- | ---: | ---: | --- |
| {key} | {n} | {0.0} | {barra} |

```mermaid
pie showData
    title {título corto}
    "{key}" : {n}
```

## Lectura
- {1–3 frases. Solo números que ya aparecen arriba.}
```

- Una fila por cubeta que devolvió la API, ni una más. Solo si llegan más de 8, las que sobran a partir de la novena se suman en `otros`. Orden de mayor a menor.
- Barra: 16 celdas. `bloques = round(n / max * 16)`; si `n > 0` y da 0, usa 1. Carácter `█`, el resto espacios (ningún otro carácter). `max` es el mayor de la columna.
- Porcentaje = `n / suma de los n de la tabla * 100`, un decimal; la columna suma 100. Total 0: sin gráfica, escribe `Sin datos para ese corte.`
- En el pie van los mismos enteros que en la tabla. Etiquetas cortas, sin saltos de línea.
- Anidado: una tabla por categoría padre, con subtítulo `### {key padre} ({n})`. Pie solo del nivel raíz.

Si GraphQL devuelve `errors`, corrige y reintenta. No inventes ceros para claves que no vinieron. No listes teléfonos, correos ni textos. Español, corto.
