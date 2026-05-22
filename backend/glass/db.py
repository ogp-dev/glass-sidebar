import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> asyncpg.Pool:
    """Return the process-wide asyncpg pool, creating it lazily on first call.

    Settings is imported lazily so pytest monkeypatching of DATABASE_URL takes
    effect before the singleton is instantiated. Do not move this import to
    module top — that breaks the test suite.
    """
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:  # double-check after acquiring lock
            from glass.config import settings

            _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
