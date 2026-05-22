from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from glass.api.app import create_app
from glass.auth import AuthUser, current_user
from glass.db import acquire, close_pool
from glass.models import hash_claim_text


@pytest.fixture(autouse=True)
async def _truncate_after():
    """Clean tables after each API test so they don't leak state."""
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE claim_sources, claims, transcript_lines, session_speakers, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def fake_user_app():
    fake_user = AuthUser(clerk_user_id="user_test", email="t@example.com")
    app = create_app()
    # Use FastAPI dependency_overrides so the override takes effect at request
    # dispatch time, not at router-build time (monkeypatching the module attr
    # doesn't work because Depends() captures the callable reference).
    app.dependency_overrides[current_user] = lambda: fake_user
    return app


@pytest.mark.asyncio
async def test_create_session(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r = await client.post("/api/sessions", json={"name": "TWiST E2288"})
        assert r.status_code == 201
        body = r.json()
        assert UUID(body["id"])
        assert body["name"] == "TWiST E2288"
        assert body["state"] == "draft"


@pytest.mark.asyncio
async def test_get_session(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r1 = await client.post("/api/sessions", json={"name": "TWiST E2289"})
        sid = r1.json()["id"]
        r2 = await client.get(f"/api/sessions/{sid}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "TWiST E2289"


@pytest.mark.asyncio
async def test_get_session_not_found(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_end_session(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r1 = await client.post("/api/sessions", json={"name": "x"})
        sid = r1.json()["id"]
        r2 = await client.post(f"/api/sessions/{sid}/end")
        assert r2.status_code == 200
        assert r2.json()["state"] == "ended"
        assert r2.json()["ended_at"] is not None


@pytest.mark.asyncio
async def test_health_endpoint(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


@pytest.fixture(scope="session", autouse=True)
async def _cleanup_pool_at_end():
    yield
    await close_pool()


@pytest.mark.asyncio
async def test_list_sessions_newest_first(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        await client.post("/api/sessions", json={"name": "older"})
        await client.post("/api/sessions", json={"name": "newer"})
        r = await client.get("/api/sessions")
        assert r.status_code == 200
        assert [s["name"] for s in r.json()] == ["newer", "older"]


@pytest.mark.asyncio
async def test_list_sessions_scoped_with_counts(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r1 = await client.post("/api/sessions", json={"name": "mine"})
        sid = UUID(r1.json()["id"])
        async with acquire() as conn:
            for text, state in [("claim one", "verified"), ("claim two", "disputed")]:
                await conn.execute(
                    """
                    INSERT INTO claims
                        (id, session_id, claim_text, claim_hash, claim_type, state)
                    VALUES ($1, $2, $3, $4, 'numeric', $5)
                    """,
                    uuid4(),
                    sid,
                    text,
                    hash_claim_text(text),
                    state,
                )
            # a session owned by a different user — must not appear
            await conn.execute(
                "INSERT INTO users (clerk_user_id, email) VALUES ('other', 'o@x.com')"
            )
            await conn.execute(
                """
                INSERT INTO sessions (user_id, name)
                SELECT id, 'theirs' FROM users WHERE clerk_user_id = 'other'
                """
            )
        r = await client.get("/api/sessions")
        body = r.json()
        assert [s["name"] for s in body] == ["mine"]
        assert body[0]["card_count"] == 2
        assert body[0]["disputed_count"] == 1


@pytest.mark.asyncio
async def test_get_transcript_ordered(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        r1 = await client.post("/api/sessions", json={"name": "s"})
        sid = UUID(r1.json()["id"])
        async with acquire() as conn:
            for text, start in [("second", 2000), ("first", 1000)]:
                await conn.execute(
                    """
                    INSERT INTO transcript_lines
                        (id, session_id, speaker, text, start_ms, end_ms, is_final)
                    VALUES ($1, $2, 'You', $3, $4, $5, true)
                    """,
                    uuid4(),
                    sid,
                    text,
                    start,
                    start + 500,
                )
        r = await client.get(f"/api/sessions/{sid}/transcript")
        assert r.status_code == 200
        assert [line["text"] for line in r.json()] == ["first", "second"]


@pytest.mark.asyncio
async def test_get_transcript_foreign_session_404(fake_user_app):
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        async with acquire() as conn:
            await conn.execute(
                "INSERT INTO users (clerk_user_id, email) VALUES ('other', 'o@x.com')"
            )
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (user_id, name)
                SELECT id, 'theirs' FROM users WHERE clerk_user_id = 'other'
                RETURNING id
                """
            )
        r = await client.get(f"/api/sessions/{row['id']}/transcript")
        assert r.status_code == 404
