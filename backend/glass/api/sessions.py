from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from glass.auth import AuthUser, current_user
from glass.db import acquire
from glass.models import Session

router = APIRouter(tags=["sessions"])


class CreateSessionBody(BaseModel):
    name: str


async def _ensure_user(user: AuthUser) -> UUID:
    """Upsert the Clerk user into our users table; return its uuid."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (clerk_user_id, email)
            VALUES ($1, $2)
            ON CONFLICT (clerk_user_id) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
            """,
            user.clerk_user_id,
            user.email,
        )
        return row["id"]  # type: ignore[no-any-return]


@router.post(
    "/sessions", status_code=status.HTTP_201_CREATED, response_model=Session
)
async def create_session(
    body: CreateSessionBody, user: AuthUser = Depends(current_user)
) -> Session:
    user_id = await _ensure_user(user)
    async with acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO sessions (user_id, name) VALUES ($1, $2) RETURNING *",
            user_id,
            body.name,
        )
    return Session.model_validate(dict(row))


@router.get("/sessions")
async def list_sessions(
    user: AuthUser = Depends(current_user),
) -> list[dict[str, Any]]:
    """The current user's sessions, newest first, for the Recent-sessions list
    on the start page. Includes per-session fact-card counts."""
    user_id = await _ensure_user(user)
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.name, s.state, s.created_at, s.ended_at,
                   count(c.id) AS card_count,
                   count(c.id) FILTER (WHERE c.state = 'disputed')
                       AS disputed_count
            FROM sessions s
            LEFT JOIN claims c ON c.session_id = s.id
            WHERE s.user_id = $1
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """,
            user_id,
        )
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "state": row["state"],
            "created_at": row["created_at"].isoformat(),
            "ended_at": row["ended_at"].isoformat()
            if row["ended_at"] is not None
            else None,
            "card_count": row["card_count"],
            "disputed_count": row["disputed_count"],
        }
        for row in rows
    ]


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(
    session_id: UUID, user: AuthUser = Depends(current_user)
) -> Session:
    user_id = await _ensure_user(user)
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM sessions WHERE id = $1 AND user_id = $2",
            session_id,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return Session.model_validate(dict(row))


@router.post("/sessions/{session_id}/end", response_model=Session)
async def end_session(
    session_id: UUID, user: AuthUser = Depends(current_user)
) -> Session:
    user_id = await _ensure_user(user)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET state = 'ended', ended_at = now()
            WHERE id = $1 AND user_id = $2
            RETURNING *
            """,
            session_id,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return Session.model_validate(dict(row))


@router.get("/sessions/{session_id}/transcript")
async def list_transcript(
    session_id: UUID, user: AuthUser = Depends(current_user)
) -> list[dict[str, Any]]:
    """The session's transcript lines, ordered by start time — used by the
    read-only review screen. 404 if the session is not the caller's."""
    user_id = await _ensure_user(user)
    async with acquire() as conn:
        owns = await conn.fetchval(
            "SELECT 1 FROM sessions WHERE id = $1 AND user_id = $2",
            session_id,
            user_id,
        )
        if owns is None:
            raise HTTPException(status_code=404, detail="session not found")
        rows = await conn.fetch(
            """
            SELECT id, text, start_ms, end_ms, speaker
            FROM transcript_lines
            WHERE session_id = $1
            ORDER BY start_ms
            """,
            session_id,
        )
    return [
        {
            "id": str(row["id"]),
            "text": row["text"],
            "start_ms": row["start_ms"],
            "end_ms": row["end_ms"],
            "speaker": row["speaker"],
        }
        for row in rows
    ]


@router.post("/sessions/{session_id}/stop", response_model=Session)
async def stop_session(
    session_id: UUID, user: AuthUser = Depends(current_user)
) -> Session:
    """Stop a live session: push shutdown to the helper via control channel +
    mark the row ended. The helper's audio WS subscribes to the control
    channel (see glass/api/ws_audio.py) and tears down its audio engine on
    receipt of ``{"type": "shutdown"}``.
    """
    from glass.events.bus import bus

    user_id = await _ensure_user(user)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE sessions
            SET state = 'ended', ended_at = COALESCE(ended_at, now())
            WHERE id = $1 AND user_id = $2
            RETURNING *
            """,
            session_id,
            user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    await bus.publish_control(str(session_id), {"type": "shutdown"})
    return Session.model_validate(dict(row))
