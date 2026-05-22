import asyncio
from uuid import uuid4

import pytest

from glass.db import acquire
from glass.events.bus import bus
from glass.workers.arq_settings import claim_detect_job, research_and_verify_job
from glass.workers.research import SearchResult
from glass.workers.verify import VerificationResult


@pytest.fixture(autouse=True)
async def _truncate_after():
    from glass.cache import cache_clear
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE entities, claim_sources, claims, transcript_lines, "
            "session_speakers, sessions, users RESTART IDENTITY CASCADE"
        )
    await cache_clear()


@pytest.fixture
async def session_with_line():
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
        await conn.execute(
            """
            INSERT INTO transcript_lines (session_id, text, start_ms, end_ms, is_final)
            VALUES ($1, $2, 0, 5000, TRUE)
            """,
            sid,
            "Cerebras raised one point two billion dollars last September.",
        )
    return str(sid)


class _FakeArqRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple] = []

    async def enqueue_job(self, name: str, *args) -> None:
        self.enqueued.append((name, args))


@pytest.mark.asyncio
async def test_full_pipeline(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glass.workers.claim_detect import DetectedClaim

    async def fake_detect(window_text: str) -> list[DetectedClaim]:
        return [
            DetectedClaim(
                text="Cerebras raised $1.2 billion",
                claim_type="numeric",
                speaker="Speaker 0",
                approx_end_ms=5000,
            )
        ]

    async def fake_search(claim_text: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://bloomberg.com/x",
                title="Cerebras raised $1.1B Series F",
                publisher="bloomberg.com",
                published_at=None,
                excerpt="Cerebras closed a $1.1B round",
            )
        ]

    async def fake_verify(claim_text: str, sources) -> VerificationResult:
        return VerificationResult(
            state="partial",
            verdict="Close — wrong amount.",
            correction="Actually $1.1B",
            confidence=92,
        )

    monkeypatch.setattr("glass.workers.arq_settings.detect_claims_in_window", fake_detect)
    monkeypatch.setattr("glass.workers.arq_settings.search_for_claim", fake_search)
    monkeypatch.setattr("glass.workers.arq_settings.verify_claim", fake_verify)

    received: list[dict] = []

    async def collect() -> None:
        async for ev in bus.subscribe(session_with_line):
            received.append(ev)
            if any(e["kind"] == "card" for e in received):
                break

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await claim_detect_job(fake_ctx, session_with_line, 5000)
    for job_name, args in fake_ctx["redis"].enqueued:
        if job_name == "research_and_verify_job":
            await research_and_verify_job(fake_ctx, *args)

    await asyncio.wait_for(collect_task, timeout=3.0)

    cards = [e for e in received if e["kind"] == "card"]
    assert len(cards) == 1
    assert cards[0]["state"] == "partial"
    assert "1.1B" in cards[0]["correction"]
    assert len(cards[0]["sources"]) == 1
    assert cards[0]["sources"][0]["url"] == "https://bloomberg.com/x"


@pytest.mark.asyncio
async def test_dedup_skips_already_seen_claim(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the claim already exists in the session, claim_detect_job skips it."""
    from glass.workers.claim_detect import DetectedClaim

    async def fake_detect(window_text: str) -> list[DetectedClaim]:
        return [
            DetectedClaim(
                text="Cerebras raised $1.2 billion",
                claim_type="numeric",
                speaker="Speaker 0",
                approx_end_ms=5000,
            )
        ]

    monkeypatch.setattr("glass.workers.arq_settings.detect_claims_in_window", fake_detect)

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await claim_detect_job(fake_ctx, session_with_line, 5000)
    first_enqueue_count = len(fake_ctx["redis"].enqueued)
    assert first_enqueue_count == 1

    # Run again — should NOT enqueue a second job
    await claim_detect_job(fake_ctx, session_with_line, 5000)
    assert len(fake_ctx["redis"].enqueued) == first_enqueue_count


@pytest.mark.asyncio
async def test_claim_detect_no_lines_is_no_op() -> None:
    """If there are no transcript lines in the session, do nothing."""
    sid = uuid4()
    async with acquire() as conn:
        uid = await conn.fetchval(
            "INSERT INTO users (clerk_user_id, email) VALUES ($1, $2) RETURNING id",
            f"user_{sid}",
            "nolines@example.com",
        )
        await conn.execute(
            "INSERT INTO sessions (id, user_id, name) VALUES ($1, $2, 'empty')",
            sid,
            uid,
        )
    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await claim_detect_job(fake_ctx, str(sid), 5000)
    assert fake_ctx["redis"].enqueued == []


@pytest.mark.asyncio
async def test_trajectory_job_inserts_entity_and_enqueues_research(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glass.workers.arq_settings import trajectory_job
    from glass.workers.trajectory import PredictedCandidate

    async def fake_predict(window_text: str) -> list[PredictedCandidate]:
        return [
            PredictedCandidate(name="Cerebras Systems", kind="company", likelihood=9),
            PredictedCandidate(name="Cerebras Systems", kind="company", likelihood=8),  # dup
        ]

    monkeypatch.setattr(
        "glass.workers.arq_settings.predict_trajectory", fake_predict
    )

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await trajectory_job(fake_ctx, session_with_line, 5000)

    # Only one entity inserted (dup skipped by slug)
    async with acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM entities WHERE session_id = $1", session_with_line
        )
        assert count == 1

    # One research job enqueued
    assert len(fake_ctx["redis"].enqueued) == 1
    assert fake_ctx["redis"].enqueued[0][0] == "entity_research_job"


@pytest.mark.asyncio
async def test_trajectory_job_skips_existing_entity(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the entity is already known (e.g. inserted by setup), trajectory
    must not double-insert or double-enqueue."""
    from glass.workers.arq_settings import trajectory_job
    from glass.workers.trajectory import PredictedCandidate

    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO entities (session_id, slug, name, kind)
            VALUES ($1, 'cerebras-systems', 'Cerebras Systems', 'company')
            """,
            session_with_line,
        )

    async def fake_predict(window_text: str) -> list[PredictedCandidate]:
        return [PredictedCandidate(name="Cerebras Systems", kind="company", likelihood=9)]

    monkeypatch.setattr(
        "glass.workers.arq_settings.predict_trajectory", fake_predict
    )

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await trajectory_job(fake_ctx, session_with_line, 5000)

    assert fake_ctx["redis"].enqueued == []


@pytest.mark.asyncio
async def test_claim_detect_uses_claim_cache(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the claim cache has a verdict for the same hash, claim_detect_job
    must NOT enqueue research_and_verify and MUST publish the cached card
    immediately with cache_hit=True."""
    from glass.cache import cache_clear, cache_set_claim
    from glass.models import hash_claim_text
    from glass.workers.arq_settings import claim_detect_job
    from glass.workers.claim_detect import DetectedClaim

    await cache_clear()

    async def fake_detect(window_text: str) -> list[DetectedClaim]:
        return [
            DetectedClaim(
                text="Cerebras raised $1.2 billion",
                claim_type="numeric",
                speaker="Speaker 0",
                approx_end_ms=5000,
            )
        ]

    monkeypatch.setattr(
        "glass.workers.arq_settings.detect_claims_in_window", fake_detect
    )

    chash = hash_claim_text("Cerebras raised $1.2 billion")
    await cache_set_claim(
        chash,
        {
            "claim_text": "Cerebras raised $1.2 billion",
            "claim_type": "numeric",
            "state": "partial",
            "verdict": "Close — actually $1.1B.",
            "correction": "$1.1B (Sept 2024)",
            "confidence": 88,
            "sources": [
                {
                    "url": "https://bloomberg.com/x",
                    "title": "Cerebras",
                    "publisher": "bloomberg.com",
                    "published_at": None,
                    "excerpt": "...",
                }
            ],
        },
        ttl_sec=60,
    )

    received: list = []

    async def collect() -> None:
        async for ev in bus.subscribe(session_with_line):
            received.append(ev)
            if any(e["kind"] == "card" for e in received):
                break

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0.1)  # let subscription register on Redis

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await claim_detect_job(fake_ctx, session_with_line, 5000)

    await asyncio.wait_for(collect_task, timeout=3.0)

    cards = [e for e in received if e["kind"] == "card"]
    assert len(cards) == 1
    assert cards[0]["cache_hit"] is True
    assert cards[0]["state"] == "partial"

    # No research_and_verify_job enqueued
    assert all(j[0] != "research_and_verify_job" for j in fake_ctx["redis"].enqueued)

    await cache_clear()


@pytest.mark.asyncio
async def test_trajectory_job_drops_low_likelihood(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Candidates with likelihood < 7 must not be enqueued."""
    from glass.workers.arq_settings import trajectory_job
    from glass.workers.trajectory import PredictedCandidate

    async def fake_predict(window_text: str) -> list[PredictedCandidate]:
        return [
            PredictedCandidate(name="Real Topic Worth Caring", kind="company", likelihood=8),
            PredictedCandidate(name="Maybe Maybe", kind="company", likelihood=5),  # filtered
            PredictedCandidate(name="No Way", kind="topic", likelihood=2),  # filtered
        ]

    monkeypatch.setattr(
        "glass.workers.arq_settings.predict_trajectory", fake_predict
    )

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await trajectory_job(fake_ctx, session_with_line, 5000)

    # Only the likelihood=8 candidate survived
    async with acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM entities WHERE session_id = $1", session_with_line
        )
        assert count == 1
    assert len(fake_ctx["redis"].enqueued) == 1


@pytest.mark.asyncio
async def test_trajectory_job_drops_single_word_topics(
    session_with_line: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """kind=topic with only one word in name must be dropped."""
    from glass.workers.arq_settings import trajectory_job
    from glass.workers.trajectory import PredictedCandidate

    async def fake_predict(window_text: str) -> list[PredictedCandidate]:
        return [
            PredictedCandidate(name="IPO", kind="topic", likelihood=9),  # filtered (1 word)
            PredictedCandidate(name="AI chip wars", kind="topic", likelihood=9),  # OK (3 words)
        ]

    monkeypatch.setattr(
        "glass.workers.arq_settings.predict_trajectory", fake_predict
    )

    fake_ctx: dict = {"redis": _FakeArqRedis()}
    await trajectory_job(fake_ctx, session_with_line, 5000)

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT name FROM entities WHERE session_id = $1 ORDER BY name", session_with_line
        )
        names = {row["name"] for row in rows}
    assert "AI chip wars" in names
    assert "IPO" not in names
    assert len(names) == 1
