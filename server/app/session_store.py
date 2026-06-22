"""Redis 세션 CRUD.

키: session:{session_id}
값: JSON — SessionData 스키마
TTL: settings.SESSION_TTL_SEC (기본 1시간)
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

_KEY_PREFIX = "session"


def _key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_session() -> dict[str, Any]:
    return {
        "history": [],
        "requestion_count": 0,
        "locked": False,
        "created_at": _now_iso(),
    }


async def create_session(redis: aioredis.Redis) -> str:
    session_id = str(uuid.uuid4())
    data = _empty_session()
    await redis.set(_key(session_id), json.dumps(data), ex=settings.SESSION_TTL_SEC)
    return session_id


async def get_session(redis: aioredis.Redis, session_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def _save(redis: aioredis.Redis, session_id: str, data: dict[str, Any]) -> None:
    """TTL을 유지하면서 세션 저장."""
    ttl = await redis.ttl(_key(session_id))
    ex = ttl if ttl > 0 else settings.SESSION_TTL_SEC
    await redis.set(_key(session_id), json.dumps(data), ex=ex)


async def increment_requestion(redis: aioredis.Redis, session_id: str) -> int:
    """requestion_count를 1 증가시키고 새 값 반환."""
    data = await get_session(redis, session_id)
    if data is None:
        raise KeyError(session_id)
    data["requestion_count"] += 1
    await _save(redis, session_id, data)
    return data["requestion_count"]


async def lock_session(redis: aioredis.Redis, session_id: str) -> None:
    data = await get_session(redis, session_id)
    if data is None:
        raise KeyError(session_id)
    data["locked"] = True
    await _save(redis, session_id, data)


async def reset_session(redis: aioredis.Redis, session_id: str) -> None:
    """카운터·lock 초기화. 히스토리는 유지."""
    data = await get_session(redis, session_id)
    if data is None:
        raise KeyError(session_id)
    data["requestion_count"] = 0
    data["locked"] = False
    await _save(redis, session_id, data)


async def append_history(
    redis: aioredis.Redis,
    session_id: str,
    role: str,
    content: str,
    persona_name: str | None = None,
) -> None:
    data = await get_session(redis, session_id)
    if data is None:
        raise KeyError(session_id)
    entry: dict[str, Any] = {"role": role, "content": content, "ts": _now_iso()}
    if persona_name is not None:
        entry["persona_name"] = persona_name
    data["history"].append(entry)
    await _save(redis, session_id, data)
