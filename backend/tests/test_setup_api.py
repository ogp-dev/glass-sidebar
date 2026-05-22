from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from glass.api.app import create_app
from glass.auth import AuthUser, current_user
from glass.cache import cache_clear
from glass.db import acquire
from glass.workers.entity_extract import ExtractedEntity


@pytest.fixture(autouse=True)
async def _truncate_and_clear():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE entities, claim_sources, claims, transcript_lines, "
            "session_speakers, sessions, users RESTART IDENTITY CASCADE"
        )
    await cache_clear()


@pytest.fixture
def fake_user_app():
    app = create_app()
    fake = AuthUser(clerk_user_id="user_test", email="t@example.com")
    app.dependency_overrides[current_user] = lambda: fake
    return app


class _FakeArqRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, name: str, *args) -> None:
        self.enqueued.append((name, args))


@pytest.fixture
def stub_anticipation(monkeypatch: pytest.MonkeyPatch):
    """Stub LLM + Arq pool for setup tests."""
    fake_pool = _FakeArqRedis()

    async def fake_extract(docket: str) -> list[ExtractedEntity]:
        return [
            ExtractedEntity(name="Cerebras Systems", kind="company", salience=9),
            ExtractedEntity(name="Jason Calacanis", kind="person", salience=8),
        ]

    async def fake_get_pool():
        return fake_pool

    monkeypatch.setattr("glass.api.setup.extract_entities_from_docket", fake_extract)
    monkeypatch.setattr("glass.api.setup._get_pool", fake_get_pool)
    return fake_pool


@pytest.mark.asyncio
async def test_setup_persists_docket_and_creates_entities(
    fake_user_app, stub_anticipation: _FakeArqRedis
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        sr = await client.post("/api/sessions", json={"name": "TWiST E2289"})
        sid = UUID(sr.json()["id"])

        body = {
            "docket": "TWiST E2289: Cerebras IPO, Jason talking with David Sacks.",
            "anticipation_c": False,
        }
        r = await client.post(f"/api/sessions/{sid}/setup", json=body)
        assert r.status_code == 200
        out = r.json()
        assert out["state"] == "ready"
        assert out["entities_count"] == 2

        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT setup_doc, state FROM sessions WHERE id = $1", sid
            )
            assert row["setup_doc"] == body["docket"]
            assert row["state"] == "ready"

        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT slug, name, kind, research_state FROM entities "
                "WHERE session_id = $1 ORDER BY name",
                sid,
            )
            assert len(rows) == 2
            assert {r["slug"] for r in rows} == {"cerebras-systems", "jason-calacanis"}
            for r in rows:
                assert r["research_state"] == "pending"

        assert len(stub_anticipation.enqueued) == 2
        names = [job[0] for job in stub_anticipation.enqueued]
        assert names == ["entity_research_job", "entity_research_job"]


@pytest.mark.asyncio
async def test_setup_empty_docket_still_ready(
    fake_user_app, stub_anticipation: _FakeArqRedis
) -> None:
    """Empty docket -> ready with 0 entities, no LLM call."""
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        sr = await client.post("/api/sessions", json={"name": "x"})
        sid = UUID(sr.json()["id"])

        r = await client.post(
            f"/api/sessions/{sid}/setup", json={"docket": "", "anticipation_c": False}
        )
        assert r.status_code == 200
        assert r.json()["state"] == "ready"
        assert r.json()["entities_count"] == 0

        async with acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM entities WHERE session_id = $1", sid
            )
            assert count == 0


@pytest.mark.asyncio
async def test_setup_session_not_found(
    fake_user_app, stub_anticipation: _FakeArqRedis
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/sessions/00000000-0000-0000-0000-000000000000/setup",
            json={"docket": "x", "anticipation_c": False},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_setup_dedupes_entities_by_slug(
    fake_user_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If extractor returns two entities that slugify to the same key,
    only the higher-salience one survives."""
    fake_pool = _FakeArqRedis()

    async def fake_extract(docket: str) -> list[ExtractedEntity]:
        return [
            ExtractedEntity(name="Cerebras Systems", kind="company", salience=9),
            ExtractedEntity(name="cerebras  systems", kind="company", salience=3),
        ]

    async def fake_get_pool():
        return fake_pool

    monkeypatch.setattr("glass.api.setup.extract_entities_from_docket", fake_extract)
    monkeypatch.setattr("glass.api.setup._get_pool", fake_get_pool)

    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        sr = await client.post("/api/sessions", json={"name": "x"})
        sid = UUID(sr.json()["id"])
        r = await client.post(
            f"/api/sessions/{sid}/setup",
            json={"docket": "any", "anticipation_c": False},
        )
        assert r.status_code == 200
        assert r.json()["entities_count"] == 1
        async with acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM entities WHERE session_id = $1", sid
            )
            assert count == 1
