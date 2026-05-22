"""Tests for manual_verify_job — 3 branches."""

from datetime import date
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from glass.db import acquire
from glass.models import hash_claim_text
from glass.workers.research import SearchResult
from glass.workers.verify import VerificationResult


@pytest.fixture(autouse=True)
async def _truncate_after():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE claim_sources, claims, transcript_lines, session_speakers, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


async def _seed_session() -> str:
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


def _mk_source(rank: int = 1) -> SearchResult:
    return SearchResult(
        url=f"https://example.com/{rank}",
        title="t",
        publisher="reuters",
        published_at=date(2024, 9, 25),
        excerpt="raised $1.1B",
    )


def _mk_verdict(state: str = "verified", confidence: int = 92) -> VerificationResult:
    return VerificationResult(
        state=state,
        verdict="Confirmed.",
        correction=None,
        confidence=confidence,
    )


@pytest.mark.asyncio
async def test_query_branch_inserts_manual_pinned_critical_card():
    """Free-text query → Sonnet extracts proposition → research+verify → insert."""
    from glass.workers.manual_verify import ExtractedProposition, manual_verify_job

    sid = await _seed_session()

    with (
        patch(
            "glass.workers.manual_verify.sonnet_extract_proposition",
            new=AsyncMock(
                return_value=ExtractedProposition(
                    proposition="Cerebras raised $1.1B in Series F",
                    entity="Cerebras",
                    time_anchor="2024",
                )
            ),
        ),
        patch(
            "glass.workers.manual_verify.search_for_claim",
            new=AsyncMock(return_value=[_mk_source(1)]),
        ),
        patch(
            "glass.workers.manual_verify.verify_claim",
            new=AsyncMock(return_value=_mk_verdict("verified", 92)),
        ),
    ):
        await manual_verify_job(
            ctx={},
            session_id=sid,
            request={"query": "did Cerebras really raise 1.1 billion?"},
        )

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM claims WHERE session_id = $1", sid
        )
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "manual"
    assert row["pinned"] is True
    assert row["zone"] == "critical"
    assert row["query_echo"] == "did Cerebras really raise 1.1 billion?"
    assert row["state"] == "verified"
    assert row["claim_text"] == "Cerebras raised $1.1B in Series F"


@pytest.mark.asyncio
async def test_verify_last_branch_creates_new_manual_card_for_existing_claim():
    """verify_last loads the most-recent claim and re-verifies as a new manual card."""
    from glass.workers.manual_verify import manual_verify_job

    sid = await _seed_session()
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO claims (session_id, claim_text, claim_hash, claim_type, state)
            VALUES ($1, 'X raised $1B', $2, 'numeric', 'verified')
            """,
            sid,
            hash_claim_text("X raised $1B"),
        )

    # Sleep tiny bit so the new manual claim has a distinct ON CONFLICT path:
    # the existing claim has the same hash, so ON CONFLICT will UPDATE it to
    # manual rather than insert a second row. That's the spec'd behavior —
    # the host's manual verify mutates the existing claim into a manual card.

    with (
        patch(
            "glass.workers.manual_verify.search_for_claim",
            new=AsyncMock(return_value=[_mk_source(1)]),
        ),
        patch(
            "glass.workers.manual_verify.verify_claim",
            new=AsyncMock(
                return_value=VerificationResult(
                    state="disputed",
                    verdict="actually X raised $0.5B",
                    correction="X raised $0.5B",
                    confidence=85,
                )
            ),
        ),
    ):
        await manual_verify_job(
            ctx={},
            session_id=sid,
            request={"action": "verify_last"},
        )

    async with acquire() as conn:
        rows = await conn.fetch("SELECT * FROM claims WHERE session_id = $1", sid)
    assert len(rows) == 1  # ON CONFLICT updated the existing row
    row = rows[0]
    assert row["source"] == "manual"
    assert row["pinned"] is True
    assert row["zone"] == "critical"
    assert row["state"] == "disputed"


@pytest.mark.asyncio
async def test_verify_last_branch_no_op_when_no_recent_claim():
    """verify_last is a no-op when the session has no claims."""
    from glass.workers.manual_verify import manual_verify_job

    sid = await _seed_session()

    with (
        patch("glass.workers.manual_verify.search_for_claim", new=AsyncMock()),
        patch("glass.workers.manual_verify.verify_claim", new=AsyncMock()),
    ):
        await manual_verify_job(
            ctx={}, session_id=sid, request={"action": "verify_last"}
        )

    async with acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM claims WHERE session_id = $1", sid
        )
    assert count == 0


@pytest.mark.asyncio
async def test_rescan_30s_branch_detects_claims_in_recent_transcript():
    """rescan_30s pulls last 30s of transcript, detects claims, verifies each."""
    from glass.workers.claim_detect import DetectedClaim
    from glass.workers.manual_verify import manual_verify_job

    sid = await _seed_session()
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO transcript_lines (session_id, text, start_ms, end_ms, is_final)
            VALUES ($1, 'And Cerebras raised one point two billion', 0, 3000, TRUE)
            """,
            sid,
        )

    with (
        patch(
            "glass.workers.claim_detect.detect_claims_in_window",
            new=AsyncMock(
                return_value=[
                    DetectedClaim(
                        text="Cerebras raised $1.2B",
                        claim_type="numeric",
                        speaker="Speaker 0",
                        approx_end_ms=3000,
                    )
                ]
            ),
        ),
        patch(
            "glass.workers.manual_verify.search_for_claim",
            new=AsyncMock(return_value=[_mk_source(1)]),
        ),
        patch(
            "glass.workers.manual_verify.verify_claim",
            new=AsyncMock(return_value=_mk_verdict("verified", 88)),
        ),
    ):
        await manual_verify_job(
            ctx={}, session_id=sid, request={"action": "rescan_30s"}
        )

    async with acquire() as conn:
        rows = await conn.fetch("SELECT * FROM claims WHERE session_id = $1", sid)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "manual"
    assert row["pinned"] is True
    assert row["claim_text"] == "Cerebras raised $1.2B"


@pytest.mark.asyncio
async def test_unknown_request_is_logged_and_no_op():
    from glass.workers.manual_verify import manual_verify_job

    sid = await _seed_session()
    await manual_verify_job(ctx={}, session_id=sid, request={"action": "foo"})

    async with acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM claims WHERE session_id = $1", sid
        )
    assert count == 0
