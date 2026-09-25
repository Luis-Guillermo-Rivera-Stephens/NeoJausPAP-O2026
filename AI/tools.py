from pathlib import Path

from agents import function_tool
import requests

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
    print(f"[TOOL] call_graphql query={query}")
    try:
        url = "http://localhost:8000/graphql"
        response = requests.post(url, json={"query": query})
        print(f"[TOOL] call_graphql response={response.json()}")
        return response.json()
    except Exception as e:
        print(f"[TOOL] call_graphql error={e}")
        return str(e)


@function_tool
def read_skill(name: str = "") -> str:
    """Lista skills en AI/skills o lee el SKILL.md de una por nombre."""
    print(f"[TOOL] read_skill name={name!r}")
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

