from pathlib import Path

from agents import function_tool
import requests

from AI.dashboard import CHAT_ID, check, digest, graphic_problem, normalize, render_result
from AI.jev import rewrite_advisor_ids
from api.db.cache import append_dashboard, read_dashboard
from api.schema.schema import schema

SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def _skill_dirs() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip("\"'")
    return meta


@function_tool
def call_graphql(query: str) -> str:
    query = rewrite_advisor_ids(query)
    print(f"[TOOL] call_graphql query={query}")
    try:
        url = "http://localhost:8000/graphql"
        response = requests.post(url, json={"query": query})
        body = response.json()
        errors = body.get("errors") if isinstance(body, dict) else None
        if errors:
            return "error: " + "; ".join(item.get("message", "") for item in errors)
        return body
    except Exception as e:
        print(f"[TOOL] call_graphql error={e}")
        return str(e)


@function_tool
def render_dashboard(kind: str, query: str, title: str, graphic: str = "bar") -> str:
    """Guarda un dashboard a partir de una query de conteo. kind es el campo: kpi si la query es count o kpis; categorias si es countBy; tendencia si es countOverTime; comparativa si es countCompare; reporte si hay dos o más campos hermanos. graphic es el dibujo: bar (default); pie solo categorias; line o area en tendencia, o en reporte si todos los hermanos son countOverTime (una serie por alias, una sola gráfica); stacked o scatter solo comparativa. Si comparas dos asesores día a día, un solo render_dashboard kind=reporte graphic=line. Devuelve ok N y un resumen, o error."""
    print(f"[TOOL] render_dashboard kind={kind} graphic={graphic}")
    chat_id = CHAT_ID.get()
    if not chat_id:
        return "error: sin chat"
    graphic = (graphic or "bar").strip().lower()
    query = normalize(query)
    mismatch = graphic_problem(kind, graphic, query)
    if mismatch:
        print(f"[TOOL] render_dashboard reject={mismatch}")
        return f"error: {mismatch}"
    problem = check(query, kind)
    if problem:
        print(f"[TOOL] render_dashboard reject={problem}")
        return f"error: {problem}"
    try:
        result = schema.execute_sync(query)
    except Exception as error:
        print(f"[TOOL] render_dashboard error={error}")
        return f"error: {error}"
    if result.errors:
        return "error: " + "; ".join(error.message for error in result.errors)
    if not result.data:
        return "error: sin datos"
    try:
        markdown = render_result(kind, title, query, result.data, graphic)
        index = append_dashboard(chat_id, markdown)
    except Exception as error:
        print(f"[TOOL] render_dashboard error={error}")
        return f"error: {error}"
    return f"ok {index}\n" + digest(markdown)


def _sin_grafica(markdown: str) -> str:
    lines = []
    skip = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            skip = not skip
            continue
        if not skip:
            lines.append(line)
    return "\n".join(lines)


@function_tool
def ver_dashboard(n: int) -> str:
    """Lee el dashboard N ya guardado (tablas, sin la gráfica). Úsalo solo si el resumen no alcanza para un insight concreto."""
    print(f"[TOOL] ver_dashboard n={n}")
    chat_id = CHAT_ID.get()
    if not chat_id:
        return "error: sin chat"
    try:
        markdown = read_dashboard(chat_id, n)
    except Exception as error:
        print(f"[TOOL] ver_dashboard error={error}")
        return f"error: {error}"
    if not markdown:
        return f"error: no hay dashboard {n}"
    return _sin_grafica(markdown)


@function_tool
def read_skill(name: str = "") -> str:
    """Lista skills en AI/skills o lee el SKILL.md de una por nombre."""
    print(f"[TOOL] read_skill name={name!r}")
    return load_skill(name)


def load_skill(name: str = "") -> str:
    try:
        dirs = _skill_dirs()
        if not name.strip():
            if not dirs:
                return "No hay skills en AI/skills."
            lines = []
            for d in dirs:
                meta = _frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
                desc = meta.get("description") or "(sin description)"
                lines.append(f"- {meta.get('name') or d.name}: {desc}")
            return "\n".join(lines)

        key = name.strip().lower().replace("_", "-")
        for d in dirs:
            meta = _frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
            if d.name.lower() == key or (meta.get("name") or "").lower() == key:
                return (d / "SKILL.md").read_text(encoding="utf-8")
        available = ", ".join(d.name for d in dirs) or "(ninguna)"
        return f"Skill '{name}' no encontrada. Disponibles: {available}"
    except Exception as e:
        print(f"[TOOL] read_skill error={e}")
        return str(e)

