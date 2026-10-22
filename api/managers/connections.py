from typing import Optional

from api.managers._sql import fetch_all, fetch_one


def list_connections(agency_id: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM whatsapp_connection"
    params: tuple[object, ...] = ()
    if agency_id is not None:
        sql += " WHERE agency_id = %s"
        params = (agency_id,)
    return fetch_all(sql + " ORDER BY name", params)


def get_connection(uid: str) -> Optional[dict]:
    return fetch_one("SELECT * FROM whatsapp_connection WHERE uid = %s", (uid,))
