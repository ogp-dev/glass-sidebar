import json
from datetime import date
from typing import Any

import structlog
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from glass.cache import cache_get_claim, cache_set_claim, slugify
from glass.db import acquire
from glass.events.bus import bus
from glass.models import hash_claim_text
from glass.stt.transcript_store import recent_lines
from glass.workers.background_research import emit_docket_heads_ups, research_entity
from glass.workers.claim_detect import detect_claims_in_window
from glass.workers.research import search_for_claim
from glass.workers.trajectory import predict_trajectory
from glass.workers.verify import verify_claim

log = structlog.get_logger(__name__)


def _redis_settings() -> RedisSettings:
    from glass.config import settings

    return RedisSettings.from_dsn(settings.redis_url)


_pool: ArqRedis | None = None


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
    return _pool


async def enqueue_claim_detect(session_id: str, window_end_ms: int) -> None:
    pool = await _get_pool()
    await pool.enqueue_job("claim_detect_job", session_id, window_end_ms)


def _coerce_published_at(value: object) -> date | None:
    """Cached source payloads serialize ``published_at`` as an ISO string (see
    cache_set_claim). The claim_sources.published_at column is a DATE, and
    asyncpg needs a real ``date`` object — passing the str raises DataError.
    Convert it back; tolerate None and already-typed values."""
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


async def _apply_cached_verdict(
    session_id: str, claim_id: str, cached: dict, speaker: str | None = None
) -> None:
    """Persist a cached verdict to the claim row + publish the card event
    immediately, bypassing the verify pipeline.

    cached payload shape mirrors what research_and_verify_job writes via
    cache_set_claim — see that function for the contract.
    """
    from glass.models import ClaimState, zone_for_state

    cached_state = cached.get("state", "unverified")
    cached_zone = zone_for_state(ClaimState(cached_state)).value

    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE claims
            SET state = $1, zone = $2, verdict_text = $3, correction_text = $4,
                confidence = $5, verified_at = now()
            WHERE id = $6
            """,
            cached_state,
            cached_zone,
            cached.get("verdict"),
            cached.get("correction"),
            cached.get("confidence"),
            claim_id,
        )
        for rank, s in enumerate(cached.get("sources") or [], start=1):
            await conn.execute(
                """
                INSERT INTO claim_sources
                    (claim_id, url, title, publisher, published_at, excerpt, rank)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                claim_id,
                s["url"],
                s.get("title"),
                s.get("publisher"),
                _coerce_published_at(s.get("published_at")),
                s.get("excerpt"),
                rank,
            )

    await bus.publish(
        session_id,
        {
            "kind": "card",
            "id": claim_id,
            "claim_text": cached.get("claim_text", ""),
            "claim_type": cached.get("claim_type", "numeric"),
            "state": cached_state,
            "verdict": cached.get("verdict"),
            "correction": cached.get("correction"),
            "confidence": cached.get("confidence"),
            "sources": cached.get("sources") or [],
            "pinned": False,
            "source": "auto",
            "zone": cached_zone,
            "query_echo": None,
            "speaker": speaker,
            "cache_hit": True,
        },
    )


async def claim_detect_job(ctx: dict[str, Any], session_id: str, window_end_ms: int) -> None:
    """Pull last ~60s of transcript, detect claims, enqueue research jobs.

    Skips claims already seen in this session (uses the
    uq_claims_session_claim_hash unique constraint as the source of truth).
    """
    lines = await recent_lines(session_id, window_ms=60_000, now_ms=window_end_ms)
    if not lines:
        return

    window_text = "\n".join(
        f"[{ln.speaker or 'You'} @ {ln.end_ms}] {ln.text}" for ln in lines
    )
    detected = await detect_claims_in_window(window_text)

    for d in detected:
        chash = hash_claim_text(d.text)
        # The detector copies the line's "You"/"Guest" tag; anything else is
        # garbage — store NULL rather than a bogus speaker.
        speaker = d.speaker if d.speaker in ("You", "Guest") else None
        async with acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM claims WHERE session_id = $1 AND claim_hash = $2",
                session_id,
                chash,
            )
            if existing:
                continue
            cid = await conn.fetchval(
                """
                INSERT INTO claims
                    (session_id, claim_text, claim_hash, claim_type, state,
                     speaker)
                VALUES ($1, $2, $3, $4, 'pending', $5)
                RETURNING id
                """,
                session_id,
                d.text,
                chash,
                d.claim_type,
                speaker,
            )
        # Anticipation cache check — if we've already verified this exact claim
        # in the last hour (any session), use the cached verdict and skip the
        # full verify pipeline. cache_hit=True lets the frontend show a tiny
        # "instant" indicator if it wants.
        cached = await cache_get_claim(chash)
        if cached is not None:
            await _apply_cached_verdict(session_id, str(cid), cached, speaker)
            continue

        await ctx["redis"].enqueue_job(
            "research_and_verify_job", session_id, str(cid)
        )


async def research_and_verify_job(ctx: dict[str, Any], session_id: str, claim_id: str) -> None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT claim_text FROM claims WHERE id = $1", claim_id
        )
        if row is None:
            return
        claim_text = row["claim_text"]

    sources = await search_for_claim(claim_text)
    verification = await verify_claim(claim_text, sources)

    # Postgres rejects NUL bytes (0x00) in TEXT columns. Exa occasionally
    # returns excerpts with embedded NULs from PDF-like sources. Strip
    # defensively on everything that flows into TEXT columns.
    def _clean(s: str | None) -> str | None:
        if s is None:
            return None
        return s.replace("\x00", "")

    from glass.models import ClaimState, zone_for_state
    verified_zone = zone_for_state(ClaimState(verification.state)).value

    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE claims
            SET state = $1, zone = $2, verdict_text = $3, correction_text = $4,
                confidence = $5, verified_at = now()
            WHERE id = $6
            """,
            verification.state,
            verified_zone,
            _clean(verification.verdict),
            _clean(verification.correction),
            verification.confidence,
            claim_id,
        )
        for rank, s in enumerate(sources, start=1):
            await conn.execute(
                """
                INSERT INTO claim_sources
                    (claim_id, url, title, publisher, published_at, excerpt, rank)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                claim_id,
                _clean(s.url),
                _clean(s.title),
                _clean(s.publisher),
                s.published_at,
                _clean(s.excerpt),
                rank,
            )
        full = await conn.fetchrow(
            """
            SELECT c.*,
                   (SELECT jsonb_agg(
                       jsonb_build_object(
                           'url', cs.url,
                           'title', cs.title,
                           'publisher', cs.publisher,
                           'published_at', cs.published_at,
                           'rank', cs.rank
                       ) ORDER BY cs.rank
                   ) FROM claim_sources cs WHERE cs.claim_id = c.id) AS sources
            FROM claims c WHERE c.id = $1
            """,
            claim_id,
        )

    raw_sources = full["sources"]
    if isinstance(raw_sources, str):
        parsed_sources = json.loads(raw_sources)
    elif raw_sources is None:
        parsed_sources = []
    else:
        parsed_sources = raw_sources

    await bus.publish(
        session_id,
        {
            "kind": "card",
            "id": str(full["id"]),
            "claim_text": full["claim_text"],
            "claim_type": full["claim_type"],
            "state": full["state"],
            "verdict": full["verdict_text"],
            "correction": full["correction_text"],
            "confidence": full["confidence"],
            "sources": parsed_sources,
            "pinned": full.get("pinned", False),
            "source": full.get("source", "auto"),
            "zone": full.get("zone", "calm"),
            "query_echo": full.get("query_echo"),
            "speaker": full.get("speaker"),
        },
    )

    # Populate the claim cache so the same claim in any future session can
    # short-circuit the verify pipeline.
    await cache_set_claim(
        hash_claim_text(full["claim_text"]),
        {
            "claim_text": full["claim_text"],
            "claim_type": full["claim_type"],
            "state": full["state"],
            "verdict": full["verdict_text"],
            "correction": full["correction_text"],
            "confidence": full["confidence"],
            "sources": parsed_sources,
        },
        ttl_sec=3600,
    )


async def trajectory_job(ctx: dict, session_id: str, window_end_ms: int) -> None:
    """Predict the next 30-90s of topics/entities and enqueue research jobs.

    Runs every ~20s during a live session (throttled by the audio WS handler
    in Plan B Task 8). Upserts each candidate as an entity row in
    state='pending' and enqueues entity_research_job per row, skipping
    anything already in the entities table for this session.
    """
    lines = await recent_lines(session_id, window_ms=120_000, now_ms=window_end_ms)
    if not lines:
        return
    window_text = "\n".join(
        f"[Speaker ? @ {ln.end_ms}] {ln.text}" for ln in lines
    )
    candidates = await predict_trajectory(window_text)

    for c in candidates:
        # Post-filter: drop low-confidence + single-word topics. The prompt
        # already discourages this, but Sonnet still emits some — belt and
        # suspenders.
        if c.likelihood < 7:
            continue
        if c.kind == "topic" and len(c.name.split()) < 2:
            continue

        slug = slugify(c.name)
        if not slug:
            continue
        async with acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM entities WHERE session_id = $1 AND slug = $2",
                session_id,
                slug,
            )
            if existing is not None:
                continue
            eid = await conn.fetchval(
                """
                INSERT INTO entities (session_id, slug, name, kind)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (session_id, slug) DO NOTHING
                RETURNING id
                """,
                session_id,
                slug,
                c.name,
                c.kind,
            )
            if eid is None:
                continue
        await ctx["redis"].enqueue_job("entity_research_job", session_id, str(eid))


async def entity_research_job(ctx: dict, session_id: str, entity_id: str) -> None:
    """Thin wrapper so the Arq function table has a stable name."""
    await research_entity(session_id, entity_id)


async def docket_heads_ups_job(ctx: dict, session_id: str) -> None:
    """On a session going live, surface heads-up cards for docket entities
    researched pre-show (they had only warmed the cache until now)."""
    await emit_docket_heads_ups(session_id)


class WorkerSettings:
    # redis_settings=None → arq falls back to RedisSettings() (localhost:6379).
    # Production workers export REDIS_URL before starting; _redis_settings() is used
    # by enqueue_claim_detect() and _get_pool() at runtime, not at import time.
    redis_settings = None
    functions = [
        claim_detect_job,
        research_and_verify_job,
        trajectory_job,
        entity_research_job,
        docket_heads_ups_job,
        # Lazy import — manual_verify imports from research/verify, so we keep
        # the symbol introduction local to WorkerSettings to avoid coupling
        # module import order during pytest collection.
    ]
    # Append manual_verify_job here so import side-effects stay isolated:
    from glass.workers.manual_verify import manual_verify_job as _manual_verify_job
    functions.append(_manual_verify_job)
    keep_result_forever = False
    max_jobs = 20
