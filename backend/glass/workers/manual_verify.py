"""Manual fact-verify worker (Ask Glass).

The host triggers this from the dashboard top bar (Cmd+K). Three branches:

- `{"query": "..."}` — Sonnet extracts proposition from free text, then research+verify
- `{"action": "verify_last"}` — re-verifies the most recent claim, bypassing cache
- `{"action": "rescan_30s"}` — re-detects claims in the last 30s of transcript at
  a lower confidence threshold, then verifies each

All branches produce cards with `source='manual'`, `pinned=True`, `zone='critical'`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import structlog

from glass.config import settings
from glass.db import acquire
from glass.events.bus import bus
from glass.models import CardSource, CardZone, ClaimType, hash_claim_text
from glass.workers.research import search_for_claim
from glass.workers.verify import verify_claim

log = structlog.get_logger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_EXTRACT_PROMPT = (_PROMPT_DIR / "manual_extract.txt").read_text()

# Sonnet for higher-stakes extraction; auto-detect uses Haiku.
_EXTRACT_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class ExtractedProposition:
    proposition: str
    entity: str | None
    time_anchor: str | None


async def sonnet_extract_proposition(query: str) -> ExtractedProposition:
    """Use Sonnet to pull a verifiable proposition from a free-text host question."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=_EXTRACT_MODEL,
        max_tokens=300,
        system=_EXTRACT_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    # Strip ```json fences if present
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back: treat the whole query as the proposition
        log.warning("manual_verify.extract_parse_failed", text=text[:200])
        return ExtractedProposition(proposition=query.strip(), entity=None, time_anchor=None)
    return ExtractedProposition(
        proposition=str(data.get("proposition") or query.strip()),
        entity=data.get("entity"),
        time_anchor=data.get("time_anchor"),
    )


async def manual_verify_job(
    ctx: dict[str, Any], session_id: str, request: dict[str, Any]
) -> None:
    """Three branches: free-text query / verify_last / rescan_30s.

    All produce card(s) with source='manual', pinned=True, zone='critical'.
    """
    if "query" in request:
        await _run_query_branch(session_id, request["query"])
    elif request.get("action") == "verify_last":
        await _run_verify_last_branch(session_id)
    elif request.get("action") == "rescan_30s":
        await _run_rescan_branch(session_id)
    else:
        log.warning("manual_verify.unknown_request", request=request)


async def _run_query_branch(session_id: str, query: str) -> None:
    extracted = await sonnet_extract_proposition(query)
    sources = await search_for_claim(extracted.proposition)
    verdict = await verify_claim(extracted.proposition, sources)
    await _insert_manual_card(
        session_id=session_id,
        claim_text=extracted.proposition,
        verdict=verdict,
        sources=sources,
        query_echo=query,
    )


async def _run_verify_last_branch(session_id: str) -> None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT claim_text FROM claims WHERE session_id = $1 "
            "ORDER BY detected_at DESC LIMIT 1",
            session_id,
        )
    if row is None:
        log.info("manual_verify.no_recent_claim", session_id=session_id)
        return
    claim_text = row["claim_text"]
    sources = await search_for_claim(claim_text)
    # Force recompute — caller explicitly wants a fresh check (no cache)
    verdict = await verify_claim(claim_text, sources)
    await _insert_manual_card(
        session_id=session_id,
        claim_text=claim_text,
        verdict=verdict,
        sources=sources,
        query_echo=None,
    )


async def _run_rescan_branch(session_id: str) -> None:
    """Pull last 30s of transcript, detect claims at lower threshold, verify each."""
    from glass.workers.claim_detect import detect_claims_in_window

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT text, end_ms FROM transcript_lines
            WHERE session_id = $1 AND is_final = TRUE
              AND created_at > now() - interval '30 seconds'
            ORDER BY start_ms
            """,
            session_id,
        )
    if not rows:
        log.info("manual_verify.no_recent_transcript", session_id=session_id)
        return
    window_text = "\n".join(f"[Speaker ? @ {r['end_ms']}] {r['text']}" for r in rows)
    claims = await detect_claims_in_window(window_text)
    for c in claims:
        sources = await search_for_claim(c.text)
        verdict = await verify_claim(c.text, sources)
        await _insert_manual_card(
            session_id=session_id,
            claim_text=c.text,
            verdict=verdict,
            sources=sources,
            query_echo=None,
        )


def _clean(s: str | None) -> str | None:
    """Strip NUL bytes — Postgres TEXT columns reject 0x00; Exa excerpts
    occasionally include them from PDF-like sources."""
    if s is None:
        return None
    return s.replace("\x00", "")


async def _insert_manual_card(
    *,
    session_id: str,
    claim_text: str,
    verdict: Any,  # VerificationResult from glass.workers.verify
    sources: list[Any],  # list[SearchResult] from glass.workers.research
    query_echo: str | None,
) -> None:
    claim_hash = hash_claim_text(claim_text)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO claims (
                session_id, claim_text, claim_hash, claim_type, state,
                verdict_text, correction_text, confidence,
                verified_at, pinned, source, zone, query_echo
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, now(), TRUE, $9, $10, $11
            )
            ON CONFLICT (session_id, claim_hash) DO UPDATE
              SET state = EXCLUDED.state,
                  verdict_text = EXCLUDED.verdict_text,
                  correction_text = EXCLUDED.correction_text,
                  confidence = EXCLUDED.confidence,
                  pinned = TRUE,
                  source = EXCLUDED.source,
                  zone = EXCLUDED.zone,
                  query_echo = EXCLUDED.query_echo,
                  verified_at = now()
            RETURNING id
            """,
            session_id,
            claim_text,
            claim_hash,
            ClaimType.EVENT.value,  # manual queries don't have an inherent type
            verdict.state,
            _clean(verdict.verdict),
            _clean(verdict.correction),
            verdict.confidence,
            CardSource.MANUAL.value,
            CardZone.CRITICAL.value,
            query_echo,
        )
        claim_id = row["id"]
        for rank, s in enumerate(sources, start=1):
            await conn.execute(
                """
                INSERT INTO claim_sources (claim_id, url, title, publisher, published_at, excerpt, rank)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                claim_id,
                _clean(s.url),
                _clean(s.title),
                _clean(s.publisher),
                s.published_at,
                _clean(s.excerpt),
                rank,
            )

    sources_payload = [
        {
            "url": s.url,
            "title": s.title,
            "publisher": s.publisher,
            "published_at": s.published_at.isoformat() if s.published_at else None,
            "rank": i,
        }
        for i, s in enumerate(sources, start=1)
    ]

    await bus.publish(
        session_id,
        {
            "kind": "card",
            "id": str(claim_id),
            "claim_text": claim_text,
            "claim_type": ClaimType.EVENT.value,
            "state": verdict.state,
            "verdict": verdict.verdict,
            "correction": verdict.correction,
            "confidence": verdict.confidence,
            "sources": sources_payload,
            "pinned": True,
            "source": CardSource.MANUAL.value,
            "zone": CardZone.CRITICAL.value,
            "query_echo": query_echo,
            "speaker": None,
        },
    )
