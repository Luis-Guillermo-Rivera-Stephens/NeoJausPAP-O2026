"""python AI/test_dashboard.py — render y validación, sin modelo."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from dotenv import load_dotenv

load_dotenv(root / ".env")

from AI.dashboard import check, render_result, splice


def _rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        if not line.startswith("| ") or line.startswith("| ---") or line.startswith("| Categoría") or line.startswith("| Periodo") or line.startswith("| Indicador") or line.startswith("| |"):
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def _pct_sum(markdown: str) -> float:
    return round(sum(float(row[2]) for row in _rows(markdown) if len(row) > 2 and row[2].replace(".", "", 1).isdigit()), 1)


def test_render_category():
    data = {"countBy": [
        {"key": "active", "n": 14},
        {"key": "new", "n": 7},
    ]}
    markdown = render_result("categorias", "Estatus", "query { countBy { key n } }", data)
    keys = {row[0] for row in _rows(markdown)}
    assert keys == {"active", "new"}
    assert "otros" not in markdown
    assert _pct_sum(markdown) == 100.0
    assert "14" in markdown and "7" in markdown
    assert "pie" not in markdown


def test_render_otros():
    rows = [{"key": f"c{i}", "n": 10 - i} for i in range(9)]
    markdown = render_result("categorias", "Muchos", "query { countBy { key n } }", {"countBy": rows})
    assert "otros" in markdown
    shown = {row[0] for row in _rows(markdown)}
    assert "c8" not in shown
    assert shown <= {row["key"] for row in rows} | {"otros"}
    assert _pct_sum(markdown) == 100.0


def test_render_time():
    data = {"countOverTime": [
        {"key": "2026-06-15", "n": 56},
        {"key": "2026-09-07", "n": 457},
    ]}
    markdown = render_result("tendencia", "Semanas", "query { countOverTime { key n } }", data)
    assert "15-06" in markdown and "07-09" in markdown
    assert "xychart-beta" in markdown
    assert "457" in markdown
    assert _pct_sum(markdown) == 100.0


def test_render_compare_and_kpis():
    compare = render_result("comparativa", "Dirección", "query { countCompare { key inbound outbound n usuarios } }", {"countCompare": [
        {"key": "total", "inbound": 951, "outbound": 709, "n": 1660, "usuarios": 50},
    ]})
    assert "951" in compare and "709" in compare and "1660" in compare
    kpis = render_result("kpi", "Base", "query { kpis { clients messages openWindows agencies } }", {"kpis": {
        "clients": 50, "messages": 1660, "openWindows": 0, "agencies": None,
    }})
    assert "50" in kpis and "1660" in kpis
    assert "Agencias" not in kpis


def test_check_queries():
    ok = 'query { countOverTime(entity: MESSAGES, by: WEEK) { key n } }'
    assert check(ok, "tendencia") is None
    bare = 'countOverTime(by: DAY, entity: MESSAGES, since: "2026-09-01T00:00:00Z", until: "2026-10-01T00:00:00Z") { key n }'
    assert check(bare, "tendencia") is None
    denied = "query { crmClients(limit: 1) { uid } }"
    assert "no permitido" in check(denied, "reporte")
    wrong = 'query { countBy(entity: CRM_CLIENTS, by: CLIENT_STATUS) { key n } }'
    assert check(wrong, "tendencia") is not None


def test_splice_order():
    text = "Intro\n{{dashboard:2}}\nMedio\n{{dashboard:1}}\nCierre"
    out = splice(text, ["GRAFICA-A", "GRAFICA-B"])
    assert out.index("GRAFICA-B") < out.index("Medio") < out.index("GRAFICA-A") < out.index("Cierre")
    assert "Intro" in out


if __name__ == "__main__":
    test_render_category()
    test_render_otros()
    test_render_time()
    test_render_compare_and_kpis()
    test_check_queries()
    test_splice_order()
    print("ok")
