import pytest

from glass.db import acquire, close_pool


@pytest.mark.asyncio
async def test_can_acquire_and_query() -> None:
    async with acquire() as conn:
        val = await conn.fetchval("SELECT 1")
        assert val == 1
    await close_pool()


@pytest.mark.asyncio
async def test_tables_exist() -> None:
    async with acquire() as conn:
        names = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        table_names = {row["tablename"] for row in names}
        assert "sessions" in table_names
        assert "transcript_lines" in table_names
        assert "claims" in table_names
        assert "claim_sources" in table_names
    await close_pool()
