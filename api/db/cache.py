"""Par de ventanas del chat en Redis. Caduca a la medianoche de America/Mexico_City."""

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import redis

LOCAL = ZoneInfo("America/Mexico_City")

_client: redis.Redis | None = None


def end_of_day(now: datetime) -> datetime:
    local = now.astimezone(LOCAL)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return midnight.astimezone(timezone.utc)


def ttl_seconds(now: datetime) -> int:
    return max(1, int((end_of_day(now) - now).total_seconds()))


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "pap") or None,
            decode_responses=True,
        )
    return _client


def _key(chat_id: str, kind: str) -> str:
    return f"mem:{chat_id}:{kind}"


def _dump(summary: str, window_to: datetime) -> str:
    return json.dumps(
        {"summary": summary, "window_to": window_to.astimezone(timezone.utc).isoformat()}
    )


def get_pair(chat_id: str) -> tuple[str, str] | None:
    now = datetime.now(timezone.utc)
    raw_current, raw_closed = client().mget(_key(chat_id, "current"), _key(chat_id, "closed"))
    if not raw_current:
        return None
    current = json.loads(raw_current)
    window_to = datetime.fromisoformat(current["window_to"])
    if window_to.tzinfo is None:
        window_to = window_to.replace(tzinfo=timezone.utc)
    if window_to <= now:
        return None
    closed = json.loads(raw_closed)["summary"] if raw_closed else ""
    return closed, current["summary"]


def put(chat_id: str, kind: str, summary: str, window_to: datetime, now: datetime) -> None:
    client().set(_key(chat_id, kind), _dump(summary, window_to), ex=ttl_seconds(now))


DASH_TTL = 600


def append_dashboard(chat_id: str, markdown: str) -> int:
    """Agrega un dashboard y devuelve su número (1, 2, …)."""
    key = f"dash:{chat_id}"
    index = int(client().rpush(key, markdown))
    client().expire(key, DASH_TTL)
    return index


def read_dashboard(chat_id: str, index: int) -> str | None:
    """index es 1, 2, … No borra la lista."""
    if index < 1:
        return None
    return client().lindex(f"dash:{chat_id}", index - 1)


def take_dashboards(chat_id: str) -> list[str]:
    key = f"dash:{chat_id}"
    rows = client().lrange(key, 0, -1)
    client().delete(key)
    return list(rows or [])


def put_current(chat_id: str, summary: str, window_to: datetime, now: datetime) -> None:
    try:
        put(chat_id, "current", summary, window_to, now)
    except redis.RedisError:
        try:
            client().delete(_key(chat_id, "current"))
        except redis.RedisError:
            pass
        raise
