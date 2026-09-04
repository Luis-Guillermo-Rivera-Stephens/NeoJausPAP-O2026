import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db.json"


def load_db() -> dict:
    with open(DB_PATH, encoding="utf-8") as file:
        return json.load(file)
