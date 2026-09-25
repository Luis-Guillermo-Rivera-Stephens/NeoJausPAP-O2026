from typing import Optional

from api.managers._sql import clamp_limit, fetch_all, fetch_one, like_pattern


def list_crm_clients(
    agency_id: Optional[str] = None,
    limit: int = 10,
    q: Optional[str] = None,
    client_status: Optional[str] = None,
) -> list[dict]:
    safe_limit = clamp_limit(limit)
    sql = "SELECT * FROM crm_clients WHERE is_deleted = false"
    params: list[object] = []
    if agency_id is not None:
        sql += " AND agency_id = %s"
        params.append(agency_id)
    if client_status:
        sql += " AND client_status::text = %s"
        params.append(client_status)
    pattern = like_pattern(q)
    if pattern:
        sql += """
            AND (
                first_name ILIKE %s
                OR coalesce(first_last_name, '') ILIKE %s
                OR coalesce(preferred_name, '') ILIKE %s
                OR coalesce(primary_phone, '') ILIKE %s
                OR coalesce(primary_email, '') ILIKE %s
                OR coalesce(wa_profile_name, '') ILIKE %s
                OR client_status::text ILIKE %s
            )
        """
        params.extend([pattern] * 7)
    params.append(safe_limit)
    return fetch_all(sql + " ORDER BY cat DESC LIMIT %s", tuple(params))


def get_crm_client(uid: str) -> Optional[dict]:
    return fetch_one(
        "SELECT * FROM crm_clients WHERE uid = %s AND is_deleted = false",
        (uid,),
    )
