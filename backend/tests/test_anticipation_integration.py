import asyncio
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from glass.api.app import create_app
from glass.auth import AuthUser, current_user
from glass.cache import cache_clear, cache_get_entity, slugify
from glass.db import acquire
from glass.events.bus import bus
from glass.workers.arq_settings import (
    claim_detect_job,
    entity_research_job,
    research_and_verify_job,
    trajectory_job,
)
from glass.workers.claim_detect import DetectedClaim
from glass.workers.entity_extract import ExtractedEntity
from glass.workers.research import SearchResult
from glass.workers.trajectory import PredictedCandidate
from glass.workers.verify import VerificationResult


@pytest.fixture(autouse=True)
async def _clean():
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


class _FakeArqPool:
    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, name: str, *args) -> None:
        self.enqueued.append((name, args))


async def _first_pending_entity(session_id: UUID) -> str:
    """Helper — read the most recent pending entity row for the session and
    return its UUID as a string."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM entities WHERE session_id = $1 AND research_state = 'pending' "
            "ORDER BY created_at LIMIT 1",
            session_id,
        )
        assert row is not None
    return str(row["id"])


@pytest.mark.asyncio
async def test_end_to_end_anticipation_flow(
    fake_user_app, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pool = _FakeArqPool()

    # --- Stubs for everything external ---
    async def fake_extract(docket: str) -> list[ExtractedEntity]:
        return [ExtractedEntity(name="Cerebras Systems", kind="company", salience=9)]

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://bloomberg.com/cerebras",
                title="Cerebras raises $1.1B Series F",
                publisher="bloomberg.com",
                published_at=None,
                excerpt="Cerebras closed a $1.1B round in Sept 2024",
            )
        ]

    async def fake_detect(window_text: str) -> list[DetectedClaim]:
        return [
            DetectedClaim(
                text="Cerebras raised $1.2 billion",
                claim_type="numeric",
                speaker="Speaker 0",
                approx_end_ms=5000,
            )
        ]

    async def fake_verify(claim_text: str, sources) -> VerificationResult:
        return VerificationResult(
            state="partial",
            verdict="Close — actually $1.1B.",
            correction="$1.1B (Sept 2024)",
            confidence=92,
        )

    async def fake_predict(window_text: str) -> list[PredictedCandidate]:
        # Trajectory predicts the SAME entity already in the table
        return [PredictedCandidate(name="Cerebras Systems", kind="company", likelihood=9)]

    async def fake_get_pool():
        return fake_pool

    monkeypatch.setattr("glass.api.setup.extract_entities_from_docket", fake_extract)
    monkeypatch.setattr("glass.api.setup._get_pool", fake_get_pool)
    monkeypatch.setattr("glass.workers.background_research.search_for_claim", fake_search)
    monkeypatch.setattr("glass.workers.arq_settings.detect_claims_in_window", fake_detect)
    monkeypatch.setattr("glass.workers.arq_settings.search_for_claim", fake_search)
    monkeypatch.setattr("glass.workers.arq_settings.verify_claim", fake_verify)
    monkeypatch.setattr("glass.workers.arq_settings.predict_trajectory", fake_predict)

    # --- 1. Create session ---
    async with AsyncClient(
        transport=ASGITransport(app=fake_user_app), base_url="http://test"
    ) as client:
        cr = await client.post("/api/sessions", json={"name": "TWiST E2289"})
        sid = UUID(cr.json()["id"])

        # --- 2. Submit setup with docket ---
        await client.post(
            f"/api/sessions/{sid}/setup",
            json={
                "docket": "TWiST E2289: Cerebras IPO, talking with Jason.",
                "anticipation_c": False,
            },
        )

    # --- 3. Setup should have enqueued one entity_research_job ---
    assert len(fake_pool.enqueued) == 1
    assert fake_pool.enqueued[0][0] == "entity_research_job"
    fake_pool.enqueued.clear()

    # Run the entity research inline
    entity_id = await _first_pending_entity(sid)
    await entity_research_job({"redis": fake_pool}, str(sid), entity_id)

    # Cache should be populated
    cached = await cache_get_entity(slugify("Cerebras Systems"))
    assert cached is not None
    assert cached["name"] == "Cerebras Systems"

    # --- 4. Mark session live + insert a transcript line ---
    async with acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET state = 'live', started_at = now() WHERE id = $1",
            sid,
        )
        await conn.execute(
            """
            INSERT INTO transcript_lines (session_id, text, start_ms, end_ms, is_final)
            VALUES ($1, $2, 0, 5000, TRUE)
            """,
            sid,
            "Cerebras raised one point two billion dollars last September.",
        )

    # --- 5. Trajectory predicts Cerebras — should NOT enqueue duplicate ---
    await trajectory_job({"redis": fake_pool}, str(sid), 5000)
    assert fake_pool.enqueued == []

    # --- 6. claim_detect_job runs — claim NOT in cache yet, enqueues research ---
    await claim_detect_job({"redis": fake_pool}, str(sid), 5000)
    job_names = [j[0] for j in fake_pool.enqueued]
    assert "research_and_verify_job" in job_names

    rv_args = next(
        j[1] for j in fake_pool.enqueued if j[0] == "research_and_verify_job"
    )
    fake_pool.enqueued.clear()

    # Subscribe before triggering research_and_verify so we catch the publish
    received: list[dict] = []

    async def collect() -> None:
        async for ev in bus.subscribe(str(sid)):
            received.append(ev)
            if any(e["kind"] == "card" and not e.get("cache_hit") for e in received):
                break

    ct = asyncio.create_task(collect())
    await asyncio.sleep(0.1)
    await research_and_verify_job({"redis": fake_pool}, *rv_args)
    await asyncio.wait_for(ct, timeout=3.0)

    # --- 7. Same claim in a DIFFERENT session should be cache-hit ---
    received.clear()

    async with acquire() as conn:
        uid = await conn.fetchval(
            "SELECT user_id FROM sessions WHERE id = $1", sid
        )
        sid2 = await conn.fetchval(
            "INSERT INTO sessions (user_id, name, state) "
            "VALUES ($1, 'next show', 'live') RETURNING id",
            uid,
        )
        await conn.execute(
            """
            INSERT INTO transcript_lines (session_id, text, start_ms, end_ms, is_final)
            VALUES ($1, $2, 0, 5000, TRUE)
            """,
            sid2,
            "Cerebras raised one point two billion dollars last September.",
        )

    async def collect2() -> None:
        async for ev in bus.subscribe(str(sid2)):
            received.append(ev)
            if any(e["kind"] == "card" and e.get("cache_hit") is True for e in received):
                break

    ct2 = asyncio.create_task(collect2())
    await asyncio.sleep(0.1)
    await claim_detect_job({"redis": fake_pool}, str(sid2), 5000)
    await asyncio.wait_for(ct2, timeout=3.0)

    cache_hit_cards = [
        e for e in received if e["kind"] == "card" and e.get("cache_hit") is True
    ]
    assert len(cache_hit_cards) == 1
    assert cache_hit_cards[0]["state"] == "partial"
    # And no new research_and_verify was enqueued for the second session
    assert all(j[0] != "research_and_verify_job" for j in fake_pool.enqueued)
