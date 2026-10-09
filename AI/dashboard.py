"""Valida una query de conteo, la ejecuta y pinta el Markdown. El modelo no ve la serie."""

from __future__ import annotations

import math
import re
from contextvars import ContextVar

from graphql import GraphQLError, parse, validate
from graphql.language.ast import FieldNode, OperationDefinitionNode

from api.schema.schema import schema

CHAT_ID: ContextVar[str | None] = ContextVar("dashboard_chat_id", default=None)

ALLOWED = {"count", "kpis", "countBy", "countOverTime", "countCompare"}
KIND_FIELDS = {
    "kpi": {"kpis", "count"},
    "categorias": {"countBy"},
    "tendencia": {"countOverTime"},
    "comparativa": {"countCompare"},
}
KINDS = set(KIND_FIELDS) | {"reporte"}
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SKIP = {"key", "n", "inbound", "outbound", "usuarios"}
_KPI = (
    ("agencies", "Agencias activas"),
    ("advisors", "Asesores"),
    ("clients", "Contactos"),
    ("lost", "Perdidos"),
    ("connections", "Números activos"),
    ("conversations", "Conversaciones"),
    ("openWindows", "Ventanas abiertas (hoy)"),
    ("unanswered", "Sin responder (hoy)"),
    ("messages", "Mensajes"),
    ("inbound", "Entrantes"),
    ("outbound", "Salientes"),
    ("conMensaje", "Contactos con mensaje"),
    ("usuarios", "Contactos que escribieron"),
)


def _operation(document):
    ops = [node for node in document.definitions if isinstance(node, OperationDefinitionNode)]
    if len(ops) != 1:
        raise ValueError("una sola operación")
    return ops[0]


def _roots(operation) -> list[tuple[str, str]]:
    """(respuesta en data, nombre del campo)."""
    found = []
    for sel in operation.selection_set.selections:
        if not isinstance(sel, FieldNode):
            raise ValueError("solo campos, sin fragmentos")
        name = sel.name.value
        alias = sel.alias.value if sel.alias else name
        found.append((alias, name))
    if not found:
        raise ValueError("la query no pide campos")
    return found


def _all_fields(node) -> list[str]:
    names = []
    if isinstance(node, FieldNode):
        names.append(node.name.value)
    selection = getattr(node, "selection_set", None)
    if selection:
        for child in selection.selections:
            names.extend(_all_fields(child))
    return names


def normalize(query: str) -> str:
    """Acepta el campo suelto: countOverTime(...) { key n }."""
    text = query.strip()
    if text.startswith(("query", "mutation", "{")):
        return text
    return "query { " + text + " }"


def check(query: str, kind: str) -> str | None:
    """None si la query sirve para ese kind. Si no, el texto del error."""
    if kind not in KINDS:
        return f"kind no válido: {kind}"
    try:
        document = parse(normalize(query))
        operation = _operation(document)
        roots = _roots(operation)
    except (GraphQLError, ValueError) as error:
        return str(error)
    leaves = _SKIP | {key for key, _ in _KPI}
    invalid = [name for name in _all_fields(operation) if name not in ALLOWED and name not in leaves]
    if invalid:
        return f"campo no permitido: {invalid[0]}"
    errors = validate(schema._schema, document)
    if errors:
        return errors[0].message
    names = {name for _, name in roots}
    if kind == "reporte":
        if len(roots) < 2:
            return "reporte pide al menos dos conteos hermanos"
        return None
    allowed = KIND_FIELDS[kind]
    if not names <= allowed:
        return f"{kind} solo acepta {', '.join(sorted(allowed))}"
    return None


def _key(row: dict) -> str:
    return str(row.get("key") or "sin_valor")


def _label(key: str) -> str:
    match = _DATE.match(str(key))
    if not match:
        return str(key)
    return f"{match.group(3)}-{match.group(2)}"


def _bar(n: int, top: int) -> str:
    blocks = 0 if top <= 0 or n <= 0 else round(n / top * 16)
    if n > 0 and blocks == 0:
        blocks = 1
    blocks = min(16, blocks)
    return "█" * blocks + " " * (16 - blocks)


def _percents(values: list[int]) -> list[float]:
    total = sum(values)
    if total <= 0:
        return [0.0 for _ in values]
    rounded = [round(n / total * 100, 1) for n in values]
    if rounded:
        rounded[-1] = round(rounded[-1] + (100.0 - sum(rounded)), 1)
    return rounded


def _top(rows: list[dict]) -> list[dict]:
    if len(rows) <= 8:
        return rows
    head = rows[:8]
    rest = sum(row.get("n") or 0 for row in rows[8:])
    return head + [{"key": "otros", "n": rest}]


def _corte(query: str) -> str:
    found = re.findall(r'(since|until)\s*:\s*"([^"]+)"', query)
    if not found:
        return "Todo el histórico"
    return ", ".join(f"{name} {value[:10]}" for name, value in found)


def _header(title: str, corte: str) -> list[str]:
    return [f"# {title}", "", f"_{corte} · GraphQL_", ""]


def _lectura_num(rows: list[dict], dated: bool) -> str:
    if not rows:
        return "Sin datos para ese corte."
    top = max(rows, key=lambda row: row.get("n") or 0)
    low = min(rows, key=lambda row: row.get("n") or 0)
    label = _label if dated else str
    return (
        f"Pico {label(_key(top))} = {top.get('n') or 0}. "
        f"Mínimo {label(_key(low))} = {low.get('n') or 0}. "
        f"Total {sum(row.get('n') or 0 for row in rows)}."
    )


def _kpis(data: dict) -> list[str]:
    lines = ["## Indicadores", "", "| Indicador | Valor |", "| --- | ---: |"]
    shown = [(label, data[key]) for key, label in _KPI if data.get(key) is not None]
    if not shown:
        return ["Sin datos para ese corte."]
    lines += [f"| {label} | {value} |" for label, value in shown]
    lines += ["", "## Lectura", f"- {shown[0][0]} {shown[0][1]}."]
    return lines


def _count(value: int) -> list[str]:
    return [
        "## Indicadores",
        "",
        "| Indicador | Valor |",
        "| --- | ---: |",
        f"| Total | {value} |",
        "",
        "## Lectura",
        f"- Total {value}.",
    ]


def _bars(heading: str, rows: list[dict], dated: bool, chart: bool) -> list[str]:
    if not dated:
        rows = _top(rows)
    if not rows or sum(row.get("n") or 0 for row in rows) == 0:
        return [f"## {heading}", "", "Sin datos para ese corte."]
    show = _label if dated else str
    top = max(row.get("n") or 0 for row in rows)
    pcts = _percents([row.get("n") or 0 for row in rows])
    col = "Periodo" if dated else "Categoría"
    lines = [f"## {heading}", "", f"| {col} | n | % | |", "| --- | ---: | ---: | --- |"]
    for row, pct in zip(rows, pcts):
        n = row.get("n") or 0
        lines.append(f"| {show(_key(row))} | {n} | {pct:.1f} | {_bar(n, top)} |")
    if chart and dated:
        labels = ", ".join(f'"{show(_key(row))}"' for row in rows)
        bars = ", ".join(str(row.get("n") or 0) for row in rows)
        lines += [
            "",
            "```mermaid",
            "xychart-beta",
            f'    title "{heading}"',
            f"    x-axis [{labels}]",
            f'    y-axis "n" 0 --> {math.ceil(top)}',
            f"    bar [{bars}]",
            "```",
        ]
    lines += ["", "## Lectura", f"- {_lectura_num(rows, dated)}"]
    return lines


def _compare(heading: str, rows: list[dict]) -> list[str]:
    if not rows or sum(row.get("n", 0) for row in rows) == 0:
        return [f"## {heading}", "", "Sin datos para ese corte."]
    if len(rows) == 1 and rows[0].get("key") == "total":
        row = rows[0]
        lines = [
            f"## {heading}",
            "",
            "| Indicador | Valor |",
            "| --- | ---: |",
            f"| Entrantes | {row['inbound']} |",
            f"| Salientes | {row['outbound']} |",
            f"| Total | {row['n']} |",
            f"| Usuarios | {row['usuarios']} |",
        ]
    else:
        top = max(max(row["inbound"], row["outbound"]) for row in rows)
        lines = [
            f"## {heading}",
            "",
            "| | Entrantes | | Salientes | | Total | Usuarios |",
            "| --- | ---: | --- | ---: | --- | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                f"| {_label(_key(row))} | {row['inbound']} | {_bar(row['inbound'], top)} | "
                f"{row['outbound']} | {_bar(row['outbound'], top)} | {row['n']} | {row['usuarios']} |"
            )
    inbound = sum(row["inbound"] for row in rows)
    outbound = sum(row["outbound"] for row in rows)
    lines += ["", "## Lectura", f"- Entrantes {inbound}, salientes {outbound}."]
    return lines


def _nested(bucket: dict) -> list[str]:
    lines = [f"### {_key(bucket)} ({bucket.get('n') or 0})", ""]
    for key, value in bucket.items():
        if key in _SKIP or value is None:
            continue
        if isinstance(value, int):
            lines.append(f"- {key}: {value}")
        elif isinstance(value, dict):
            lines += _kpis(value)
        elif isinstance(value, list):
            if value and "inbound" in value[0]:
                lines += _compare(key, value)
            else:
                dated = bool(value) and bool(_DATE.match(str(value[0].get("key", ""))))
                lines += _bars(key, value, dated, chart=False)
    return lines


def _block(alias: str, name: str, value, nested_charts: bool) -> list[str]:
    heading = alias if alias != name else {
        "count": "Total",
        "kpis": "Indicadores",
        "countBy": "Categorías",
        "countOverTime": "Serie",
        "countCompare": "Comparativa",
    }[name]
    if name == "kpis":
        return _kpis(value)
    if name == "count":
        return _count(value)
    if not isinstance(value, list):
        return [f"## {heading}", "", "Sin datos para ese corte."]
    if name == "countCompare":
        lines = _compare(heading, value)
    else:
        lines = _bars(heading, value, name == "countOverTime", chart=nested_charts)
    if name == "countBy":
        for bucket in value:
            if any(key not in _SKIP for key in bucket):
                lines += ["", *_nested(bucket)]
    return lines


_SLOT = re.compile(r"\{\{dashboard(?::(\d+))?\}\}")


def splice(text: str, parts: list[str]) -> str:
    """Cambia {{dashboard:N}} por el Markdown N. Sin marcas, el texto va antes y los bloques después."""
    if not parts:
        return text
    def _one(match: re.Match) -> str:
        raw = match.group(1)
        index = int(raw) - 1 if raw else 0
        if 0 <= index < len(parts):
            return "\n\n" + parts[index].strip() + "\n"
        return match.group(0)
    if _SLOT.search(text or ""):
        return _SLOT.sub(_one, text)
    body = "\n\n".join(part.strip() for part in parts)
    if (text or "").strip():
        return text.strip() + "\n\n" + body
    return body + "\n"


def digest(markdown: str) -> str:
    """La lectura, sin las tablas. Eso es lo único que vuelve al modelo."""
    lines = [line[2:].strip() for line in markdown.splitlines() if line.startswith("- ")]
    return " ".join(lines)


def render_result(kind: str, title: str, query: str, data: dict) -> str:
    document = parse(query)
    roots = _roots(_operation(document))
    lines = _header(title, _corte(query))
    for alias, name in roots:
        lines += _block(alias, name, data.get(alias), nested_charts=(kind != "reporte" and len(roots) == 1))
        lines.append("")
    return "\n".join(lines).strip() + "\n"
