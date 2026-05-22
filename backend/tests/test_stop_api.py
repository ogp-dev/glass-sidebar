import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from glass.api.app import create_app
from glass.auth import AuthUser, current_user
from glass.db import acquire


@pytest.fixture(autouse=True)
async def _truncate_after():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE claim_sources, claims, transcript_lines, session_speakers, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def fake_user_app():
    app = create_app()
    fake = AuthUser(clerk_user_id="user_test", email="t@example.com")
    app.dependency_overrides[current_user] = lambda: fake
    return app


@pytest.mark.asyncio
async def test_stop_publishes_shutdown_and_marks_session_ended(fake_user_app):
    from glass.events.bus import bus

    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        r = await client.post("/api/sessions", json={"name": "test"})
        sid = UUID(r.json()["id"])

        received: list[dict] = []
        got = asyncio.Event()

        async def consume():
            async for msg in bus.subscribe_control(str(sid)):
                received.append(msg)
                got.set()
                return

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.1)  # let subscription register

        res = await client.post(f"/api/sessions/{sid}/stop")
        assert res.status_code == 200
        body = res.json()
        assert body["state"] == "ended"
        assert body["ended_at"] is not None

        await asyncio.wait_for(got.wait(), timeout=2.0)
        if not consumer.done():
            consumer.cancel()
            with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
                await consumer

        assert received == [{"type": "shutdown"}]

        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state, ended_at FROM sessions WHERE id = $1", sid
            )
        assert row["state"] == "ended"
        assert row["ended_at"] is not None


@pytest.mark.asyncio
async def test_stop_returns_404_for_unknown_session(fake_user_app):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        bogus = uuid4()
        res = await client.post(f"/api/sessions/{bogus}/stop")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_stop_is_idempotent_preserves_first_ended_at(fake_user_app):
    """Calling /stop twice should keep the original ended_at."""
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        r = await client.post("/api/sessions", json={"name": "test"})
        sid = r.json()["id"]

        r1 = await client.post(f"/api/sessions/{sid}/stop")
        ended_at_1 = r1.json()["ended_at"]
        assert ended_at_1 is not None

        await asyncio.sleep(0.05)

        r2 = await client.post(f"/api/sessions/{sid}/stop")
        ended_at_2 = r2.json()["ended_at"]
        assert ended_at_2 == ended_at_1  # COALESCE preserves first value
