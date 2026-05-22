import json
import re
from typing import Any

import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None
_KEY_PREFIX = "glass:"
_ENTITY_PREFIX = f"{_KEY_PREFIX}entity:"
_CLAIM_PREFIX = f"{_KEY_PREFIX}claim:"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase + collapse non-alphanumerics to single dashes, strip ends.

    Used for canonical entity keys in the cache. Determinism matters: the
    same input must always produce the same slug across processes.
    """
    return _NON_ALNUM.sub("-", text.lower()).strip("-")


async def _client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        from glass.config import settings

        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def _close() -> None:
    """Test helper. Closes the global client and resets it so the next call
    creates a fresh one."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get_entity(slug: str) -> dict[str, Any] | None:
    c = await _client()
    raw = await c.get(f"{_ENTITY_PREFIX}{slug}")
    return json.loads(raw) if raw else None


async def cache_set_entity(slug: str, payload: dict[str, Any], *, ttl_sec: int) -> None:
    c = await _client()
    await c.set(f"{_ENTITY_PREFIX}{slug}", json.dumps(payload), ex=ttl_sec)


async def cache_get_claim(claim_hash: str) -> dict[str, Any] | None:
    c = await _client()
    raw = await c.get(f"{_CLAIM_PREFIX}{claim_hash}")
    return json.loads(raw) if raw else None


async def cache_set_claim(
    claim_hash: str, payload: dict[str, Any], *, ttl_sec: int
) -> None:
    c = await _client()
    await c.set(f"{_CLAIM_PREFIX}{claim_hash}", json.dumps(payload), ex=ttl_sec)


async def cache_clear() -> None:
    """Wipe all glass:* keys. Test-only helper.

    Note: scan + delete pattern is used to avoid KEYS *, which would
    block Redis on a large dataset. For v1 size this is fine."""
    c = await _client()
    cursor = 0
    while True:
        cursor, keys = await c.scan(cursor=cursor, match=f"{_KEY_PREFIX}*", count=500)
        if keys:
            await c.delete(*keys)
        if cursor == 0:
            break
