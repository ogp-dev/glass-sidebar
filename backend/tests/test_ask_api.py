"""Tests for POST /api/sessions/:id/ask."""

from uuid import UUID

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


class _FakePool:
    """In-memory arq pool stub — captures enqueue_job calls."""

    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, name: str, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))

        class _Job:
            job_id = "job-" + str(len(self.enqueued))

        return _Job()


@pytest.fixture
def fake_pool(monkeypatch: pytest.MonkeyPatch):
    pool = _FakePool()

    async def _get_pool_stub():
        return pool

    monkeypatch.setattr("glass.workers.arq_settings._get_pool", _get_pool_stub)
    return pool


@pytest.fixture
def fake_user_app(fake_pool):
    app = create_app()
    fake = AuthUser(clerk_user_id="user_test", email="t@example.com")
    app.dependency_overrides[current_user] = lambda: fake
    return app


async def _seed_session(client: AsyncClient) -> str:
    r = await client.post("/api/sessions", json={"name": "test"})
    return r.json()["id"]


@pytest.mark.asyncio
async def test_ask_with_query_enqueues_job(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)

        r = await client.post(
            f"/api/sessions/{sid}/ask",
            json={"query": "did Cerebras raise 1.1B?"},
        )
        assert r.status_code == 202
        body = r.json()
        assert "job_id" in body
        assert "accepted_at" in body

        assert len(fake_pool.enqueued) == 1
        name, args, _ = fake_pool.enqueued[0]
        assert name == "manual_verify_job"
        assert args[0] == sid
        assert args[1] == {"query": "did Cerebras raise 1.1B?"}


@pytest.mark.asyncio
async def test_ask_with_verify_last_action_enqueues_job(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(
            f"/api/sessions/{sid}/ask",
            json={"action": "verify_last"},
        )
        assert r.status_code == 202
        assert fake_pool.enqueued[0][1][1] == {"action": "verify_last"}


@pytest.mark.asyncio
async def test_ask_with_rescan_30s_action_enqueues_job(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(
            f"/api/sessions/{sid}/ask",
            json={"action": "rescan_30s"},
        )
        assert r.status_code == 202
        assert fake_pool.enqueued[0][1][1] == {"action": "rescan_30s"}


@pytest.mark.asyncio
async def test_ask_rejects_both_query_and_action(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(
            f"/api/sessions/{sid}/ask",
            json={"query": "x", "action": "verify_last"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_ask_rejects_neither_query_nor_action(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(f"/api/sessions/{sid}/ask", json={})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_ask_rejects_empty_query(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(f"/api/sessions/{sid}/ask", json={"query": "   "})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_ask_rejects_unknown_action(fake_user_app, fake_pool):
    async with AsyncClient(transport=ASGITransport(app=fake_user_app), base_url="http://test") as client:
        sid = await _seed_session(client)
        r = await client.post(
            f"/api/sessions/{sid}/ask",
            json={"action": "do_something_evil"},
        )
        assert r.status_code == 422
