import json
import re
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from glass.cache import cache_set_entity
from glass.db import acquire
from glass.workers.research import search_for_claim

log = structlog.get_logger(__name__)

# Entity background cache TTL: 1 hour matches the typical podcast session length
# and is the spec's stated value for entity / claim cache freshness.
_CACHE_TTL_SEC = 3600

# Heads-up cards with a notability at or above this are suppressed — a primer
# on a household name (NVIDIA, Jensen Huang) is noise, not signal.
_NOTABILITY_SUPPRESS_AT = 8

_NOTABILITY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "notability.txt"
_NOTABILITY_SYSTEM_PROMPT = _NOTABILITY_PROMPT_PATH.read_text()
_NOTABILITY_MODEL = "claude-haiku-4-5-20251001"
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_client: AsyncAnthropic | None = None


def _client_or_init() -> AsyncAnthropic:
    global _client
    if _client is None:
        from glass.config import settings

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def assess_notability(name: str, kind: str) -> int:
    """Rate how widely recognized an entity is, 1-10 (10 = household name).

    Gates heads-up cards: a primer on a famous entity is noise. Fails open —
    any error returns 1, so a failure never silently hides a heads-up card.
    """
    try:
        client = _client_or_init()
        msg = await client.messages.create(
            model=_NOTABILITY_MODEL,
            max_tokens=256,
            system=[
                {
                    "type": "text",
                    "text": _NOTABILITY_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": f"Entity: {name}\nKind: {kind}"}],
        )
        text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
        data = json.loads(_MD_FENCE.sub("", text).strip())
        return max(1, min(10, int(data["notability"])))
    except Exception as exc:  # noqa: BLE001 — fail open, never block a card
        log.warning("notability.assess_failed", entity=name, error=str(exc))
        return 1


def _summarize_for_heads_up(background: dict) -> str:
    """A glanceable single-line summary for a heads-up card. v1 uses the
    top source's title + publisher; iterate when we have real shows to
    test against."""
    sources = background.get("sources") or []
    if not sources:
        return ""
    top = sources[0]
    title = top.get("title") or ""
    publisher = top.get("publisher") or ""
    if title and publisher:
        return f"{title} ({publisher})"
    return title or publisher


async def research_entity(session_id: str, entity_id: str) -> None:
    """Research a single entity. Writes Postgres + Redis.

    On success: research_state -> 'done', cache populated.
    On no sources: research_state -> 'failed', cache untouched.
    On missing entity row: log + return (idempotent on stale enqueue).
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT slug, name, kind FROM entities WHERE id = $1 AND session_id = $2",
            entity_id,
            session_id,
        )
    if row is None:
        log.info("background_research.entity_gone", entity_id=entity_id)
        return

    slug = row["slug"]
    name = row["name"]
    kind = row["kind"]

    sources = await search_for_claim(name)

    if not sources:
        async with acquire() as conn:
            await conn.execute(
                "UPDATE entities SET research_state = 'failed' WHERE id = $1",
                entity_id,
            )
        return

    background = {
        "name": name,
        "kind": kind,
        "sources": [
            {
                "url": s.url,
                "title": s.title,
                "publisher": s.publisher,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "excerpt": s.excerpt,
            }
            for s in sources
        ],
    }

    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE entities
            SET background = $1::jsonb,
                research_state = 'done',
                researched_at = now()
            WHERE id = $2
            """,
            json.dumps(background),
            entity_id,
        )

    await cache_set_entity(slug, background, ttl_sec=_CACHE_TTL_SEC)

    # If the session is already live, surface a heads-up card now. Pre-show
    # research (state 'draft'/'ready') just warms the cache — those entities
    # are surfaced by emit_docket_heads_ups() when the session goes live.
    async with acquire() as conn:
        state = await conn.fetchval(
            "SELECT state FROM sessions WHERE id = $1", session_id
        )
    if state == "live":
        await _publish_heads_up(session_id, entity_id, name, kind, background)


async def _publish_heads_up(
    session_id: str, entity_id: str, name: str, kind: str, background: dict
) -> None:
    """Publish a heads-up card for one researched entity — unless a claim has
    already referenced it, or it is well-known enough that a primer is noise
    (notability gate). Shared by live entity research and the docket sweep."""
    # Avoid a duplicate heads-up: skip if a claim already referenced this
    # entity (by name match — coarse but adequate for v1).
    async with acquire() as conn:
        already_referenced = await conn.fetchval(
            "SELECT 1 FROM claims WHERE session_id = $1 AND claim_text ILIKE $2 LIMIT 1",
            session_id,
            f"%{name}%",
        )
    if already_referenced:
        return

    # A heads-up card is a primer on an entity. For a household name (NVIDIA,
    # Jensen Huang) that primer is noise — suppress it so heads-ups only
    # surface for entities the host genuinely may not know.
    notability = await assess_notability(name, kind)
    if notability >= _NOTABILITY_SUPPRESS_AT:
        log.info(
            "background_research.heads_up_suppressed",
            entity=name,
            notability=notability,
        )
        return

    from glass.events.bus import bus

    await bus.publish(
        session_id,
        {
            "kind": "card",
            "id": f"heads_up:{entity_id}",
            "claim_text": name,
            "claim_type": "heads_up",
            "state": "heads_up",
            "verdict": _summarize_for_heads_up(background),
            "correction": None,
            "confidence": None,
            "sources": background["sources"],
            "pinned": False,
            "source": "auto",
            "zone": "calm",
            "query_echo": None,
            "speaker": None,
            "entity_id": entity_id,
            "entity_kind": kind,
        },
    )
    log.info(
        "background_research.heads_up_emitted", entity=name, notability=notability
    )


async def emit_docket_heads_ups(session_id: str) -> None:
    """Surface heads-up cards for entities whose research finished before the
    session went live — the docket prep. Pre-show research only warmed the
    cache; this runs on the draft->live transition so the host opens the
    dashboard to the prepared context. Each entity still passes the
    notability gate, so household names stay filtered out."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, kind, background
            FROM entities
            WHERE session_id = $1
              AND research_state = 'done'
              AND background IS NOT NULL
            """,
            session_id,
        )
    for row in rows:
        background = row["background"]
        if isinstance(background, str):
            background = json.loads(background)
        await _publish_heads_up(
            session_id, str(row["id"]), row["name"], row["kind"], background
        )
