"""Redis client for session storage, PKCE codes, and caching."""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _pool


async def close_redis():
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None


# ── PKCE store ───────────────────────────────────────────────────


async def store_pkce(state: str, verifier: str, ttl: int = 600):
    r = await get_redis()
    await r.set(f"pkce:{state}", verifier, ex=ttl)


async def pop_pkce(state: str) -> str | None:
    r = await get_redis()
    key = f"pkce:{state}"
    val = await r.get(key)
    if val:
        await r.delete(key)
    return val


# ── Session store (JWT refresh tracking) ─────────────────────────


async def store_session(user_id: str, data: dict, ttl: int = 86400 * 7):
    r = await get_redis()
    await r.set(f"session:{user_id}", json.dumps(data), ex=ttl)


async def get_session(user_id: str) -> dict | None:
    r = await get_redis()
    val = await r.get(f"session:{user_id}")
    return json.loads(val) if val else None


async def delete_session(user_id: str):
    r = await get_redis()
    await r.delete(f"session:{user_id}")


# ── Generic cache ────────────────────────────────────────────────


async def cache_set(key: str, value: Any, ttl: int = 300):
    r = await get_redis()
    await r.set(f"cache:{key}", json.dumps(value), ex=ttl)


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    val = await r.get(f"cache:{key}")
    return json.loads(val) if val else None
