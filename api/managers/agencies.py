from typing import Optional

from api.managers._sql import fetch_all, fetch_one


def list_agencies(active_only: bool = True) -> list[dict]:
    sql = "SELECT uid, is_active FROM real_state_agencies"
    if active_only:
        sql += " WHERE is_active = true"
    return fetch_all(sql + " ORDER BY uid")


def get_agency(uid: str) -> Optional[dict]:
    return fetch_one(
        "SELECT uid, is_active FROM real_state_agencies WHERE uid = %s",
        (uid,),
    )
