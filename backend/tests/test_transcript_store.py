from uuid import uuid4

import pytest

from glass.db import acquire
from glass.stt.transcript_store import insert_line, recent_lines


@pytest.fixture(autouse=True)
async def _truncate_after():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE claim_sources, claims, transcript_lines, session_speakers, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


@pytest.fixture
async def session_id() -> str:
    sid = uuid4()
    async with acquire() as conn:
        uid = await conn.fetchval(
            "INSERT INTO users (clerk_user_id, email) VALUES ($1, $2) RETURNING id",
            f"user_{sid}",
            "t@example.com",
        )
        await conn.execute(
            "INSERT INTO sessions (id, user_id, name) VALUES ($1, $2, 'test')",
            sid,
            uid,
        )
    return str(sid)


@pytest.mark.asyncio
async def test_insert_and_recent(session_id: str) -> None:
    line1 = await insert_line(
        session_id, text="hello world", start_ms=0, end_ms=1500, is_final=True
    )
    line2 = await insert_line(
        session_id, text="second line", start_ms=1600, end_ms=3000, is_final=True
    )
    assert line1.text == "hello world"
    assert line2.text == "second line"

    lines = await recent_lines(session_id, window_ms=60_000)
    assert [ln.text for ln in lines] == ["hello world", "second line"]


@pytest.mark.asyncio
async def test_recent_lines_respects_window(session_id: str) -> None:
    await insert_line(session_id, text="old", start_ms=0, end_ms=1000, is_final=True)
    await insert_line(
        session_id, text="new", start_ms=120_000, end_ms=121_000, is_final=True
    )
    lines = await recent_lines(session_id, window_ms=60_000, now_ms=125_000)
    assert [ln.text for ln in lines] == ["new"]


@pytest.mark.asyncio
async def test_recent_lines_excludes_partial(session_id: str) -> None:
    await insert_line(session_id, text="partial", start_ms=0, end_ms=500, is_final=False)
    await insert_line(session_id, text="final", start_ms=600, end_ms=1500, is_final=True)
    lines = await recent_lines(session_id, window_ms=60_000)
    assert [ln.text for ln in lines] == ["final"]


@pytest.mark.asyncio
async def test_recent_lines_empty_session_returns_empty(session_id: str) -> None:
    lines = await recent_lines(session_id, window_ms=60_000)
    assert lines == []
