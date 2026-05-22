import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from glass.auth import AuthUser, current_user
from glass.db import acquire
from glass.events.bus import bus
from glass.models import HostAction

router = APIRouter(tags=["cards"])


class CardActionBody(BaseModel):
    action: HostAction


class PinBody(BaseModel):
    pinned: bool


@router.post("/sessions/{session_id}/cards/{card_id}/pin")
async def pin_card(
    session_id: UUID,
    card_id: UUID,
    body: PinBody,
    user: AuthUser = Depends(current_user),
) -> dict[str, Any]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE claims c
            SET pinned = $1
            FROM sessions s, users u
            WHERE c.id = $2
              AND c.session_id = $3
              AND c.session_id = s.id
              AND s.user_id = u.id
              AND u.clerk_user_id = $4
            RETURNING c.id
            """,
            body.pinned,
            card_id,
            session_id,
            user.clerk_user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="card not found")
    await bus.publish(
        str(session_id),
        {"kind": "card_updated", "id": str(card_id), "pinned": body.pinned},
    )
    return {"status": "ok", "pinned": body.pinned}


@router.post("/sessions/{session_id}/cards/{card_id}/action")
async def card_action(
    session_id: UUID,
    card_id: UUID,
    body: CardActionBody,
    user: AuthUser = Depends(current_user),
) -> dict[str, str]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE claims c
            SET host_action = $1, host_action_at = now()
            FROM sessions s, users u
            WHERE c.id = $2
              AND c.session_id = $3
              AND c.session_id = s.id
              AND s.user_id = u.id
              AND u.clerk_user_id = $4
            RETURNING c.id
            """,
            body.action.value,
            card_id,
            session_id,
            user.clerk_user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="card not found")
    return {"status": "ok", "action": body.action.value}


@router.get("/sessions/{session_id}/cards")
async def list_cards(
    session_id: UUID,
    user: AuthUser = Depends(current_user),
) -> list[dict[str, Any]]:
    """Return all fact cards for this session, oldest-first.

    Used by the frontend Live route to hydrate history on mount before
    it subscribes to the Redis pub/sub channel for new events. Without
    this, cards that were published before the subscription opened are
    lost.

    Returns the same payload shape that the WS publishes for ``kind=card``
    events so the frontend can use a single rendering path.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
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
            FROM claims c
            JOIN sessions s ON c.session_id = s.id
            JOIN users u ON s.user_id = u.id
            WHERE c.session_id = $1
              AND u.clerk_user_id = $2
            ORDER BY c.detected_at
            """,
            session_id,
            user.clerk_user_id,
        )

    cards: list[dict[str, Any]] = []
    for row in rows:
        raw_sources = row["sources"]
        if isinstance(raw_sources, str):
            parsed_sources = json.loads(raw_sources)
        elif raw_sources is None:
            parsed_sources = []
        else:
            parsed_sources = raw_sources

        cards.append(
            {
                "id": str(row["id"]),
                "claim_text": row["claim_text"],
                "claim_type": row["claim_type"],
                "state": row["state"],
                "verdict": row["verdict_text"],
                "correction": row["correction_text"],
                "confidence": row["confidence"],
                "sources": parsed_sources,
                "pinned": row["pinned"],
                "source": row["source"],
                "zone": row["zone"],
                "query_echo": row["query_echo"],
                "speaker": row["speaker"],
                "detected_at": row["detected_at"].isoformat()
                if row["detected_at"] is not None
                else None,
            }
        )
    return cards
