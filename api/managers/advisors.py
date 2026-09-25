from typing import Optional

from api.managers._sql import fetch_all, fetch_one


def list_advisors() -> list[dict]:
    return fetch_all("SELECT * FROM clients ORDER BY nickname")


def get_advisor(uid: str) -> Optional[dict]:
    return fetch_one("SELECT * FROM clients WHERE uid = %s", (uid,))
