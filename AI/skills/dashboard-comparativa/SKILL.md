---
name: dashboard-comparativa
description: Comparativa entrantes contra salientes en Markdown (tabla con dos columnas de barras) con cifras de la API GraphQL. Usar cuando pidan inbound vs outbound, "quién escribe más", mensajes recibidos y enviados, actividad por número de WhatsApp o cuántos usuarios escribieron.
---

# Dashboard comparativo

Una sola query con `call_graphql`: `countCompare`. Solo mensajes. Cada fila trae `inbound`, `outbound`, `n` (total) y `usuarios` (contactos distintos que escribieron).

## Datos

```graphql
query {
  countCompare(by: CONNECTION, since: "2026-09-01T00:00:00-06:00") { key inbound outbound n usuarios }
}
```

- `by`: `NONE` (una fila, `key: "total"`), `DAY`, `WEEK` (serie) o `CONNECTION` (un renglón por número de WhatsApp).
- Filtros: `since`, `until` (exclusivo), `agencyId`, `clientStatus`, `connectionId`, `clientId`. Sin fecha es todo el histórico: dilo en el título.
- "¿Cuántos usuarios le escribieron a mi número la semana pasada?" = `countCompare(by: CONNECTION, since, until)` y lees `usuarios`.
- Comparativa dentro de otra categoría: anida `countCompare` en un `countBy`.

```graphql
query {
  countBy(entity: CRM_CLIENTS, by: ADVISOR) {
    key n
    countCompare { key inbound outbound usuarios }
  }
}
```

## Formato

```markdown
# {título}

_{corte} · GraphQL_

## {nombre de la serie}

| {Número|Día|Semana} | Entrantes | | Salientes | | Total | Usuarios |
| --- | ---: | --- | ---: | --- | ---: | ---: |
| {key} | {inbound} | {barra} | {outbound} | {barra} | {n} | {usuarios} |

## Lectura
- {1–3 frases. Solo números que ya aparecen arriba. Di la proporción entrantes/salientes.}
```

- `by: NONE`: tabla de indicadores con cuatro filas (Entrantes, Salientes, Total, Usuarios) en vez de la tabla ancha.
- `DAY`/`WEEK`: orden cronológico, etiqueta `DD-MM`. `CONNECTION`: de mayor a menor por total.
- Una fila por cubeta que devolvió la API. Barra: 16 celdas. `bloques = round(n / max * 16)`; si `n > 0` y da 0, usa 1. Carácter `█`, el resto espacios (ningún otro carácter). `max` es el mayor entre las dos columnas, para que sean comparables.
- Sin pie. Total 0: sin gráfica, escribe `Sin datos para ese corte.`

Si GraphQL devuelve `errors`, corrige y reintenta. No inventes ceros. No listes teléfonos, correos ni textos. Español, corto.
