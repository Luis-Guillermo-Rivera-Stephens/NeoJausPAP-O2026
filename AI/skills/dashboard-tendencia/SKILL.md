---
name: dashboard-tendencia
description: Serie de tiempo en Markdown (tabla cronológica + xychart Mermaid) con cifras de la API GraphQL. Usar cuando pidan tendencia, evolución, "por día", "por semana", histórico, crecimiento o cómo cambió algo en el tiempo.
---

# Dashboard de tendencia

Una sola query con `call_graphql`: `countOverTime`. Devuelve la serie completa del rango en orden cronológico. Solo aparecen los días o semanas con filas.

## Datos

```graphql
query {
  countOverTime(entity: MESSAGES, by: WEEK, since: "2026-08-01T00:00:00-06:00") { key n }
}
```

- `by`: `DAY` o `WEEK` (semana que inicia en lunes). Fechas en `America/Mexico_City`.
- `entity`: `CRM_CLIENTS` (altas), `MESSAGES`, `CONVERSATIONS`, `CONNECTIONS`. Obligatorio en la raíz.
- `metric`: `COUNT` (default) o `COUNT_DISTINCT_CLIENTS` (contactos distintos por periodo).
- Filtros: `since`, `until` (exclusivo), `agencyId`, `clientStatus`, `direction` (solo mensajes), `connectionId`, `clientId`. Sin fecha es todo el histórico: dilo en el título.
- Más de 30 puntos: usa `WEEK` o acota `since`.
- Entrantes contra salientes por periodo: usa `countCompare(by: DAY)` (skill dashboard-comparativa), no dos `countOverTime`.
- Serie dentro de cada categoría: anida.

```graphql
query {
  countBy(entity: CRM_CLIENTS, by: ADVISOR) {
    key n
    countOverTime(by: WEEK) { key n }
  }
}
```

## Formato

```markdown
# {título}

_{corte} · GraphQL_

## {nombre de la serie}

| {Día|Semana} | n | % | |
| --- | ---: | ---: | --- |
| {DD-MM} | {n} | {0.0} | {barra} |

```mermaid
xychart-beta
    title "{título corto}"
    x-axis ["{DD-MM}", "{DD-MM}", ...una etiqueta por fila de la tabla]
    y-axis "{unidad}" 0 --> {max}
    bar [{n}, {n}, ...un entero por fila, en el mismo orden]
```

## Lectura
- {1–3 frases. Solo números que ya aparecen arriba. Señala el pico y el mínimo.}
```

- La clave llega `YYYY-MM-DD`; la etiqueta es `DD-MM`. Orden cronológico, sin reordenar por tamaño.
- Una fila por periodo que devolvió la API. Barra: 16 celdas. `bloques = round(n / max * 16)`; si `n > 0` y da 0, usa 1. Carácter `█`, el resto espacios (ningún otro carácter).
- Porcentaje = `n / suma de todos los n * 100`, un decimal; la columna suma 100. Total 0: sin gráfica, escribe `Sin datos para ese corte.`
- En `bar []` van los mismos enteros que en la tabla. El eje Y llega al máximo de la serie, redondeado hacia arriba.
- Anidado: una tabla por categoría padre con subtítulo `### {key padre} ({n})`. Un xychart solo si hay una serie; con varias, solo tablas.

Si GraphQL devuelve `errors`, corrige y reintenta. No rellenes periodos ausentes con ceros inventados. No listes teléfonos, correos ni textos. Español, corto.
