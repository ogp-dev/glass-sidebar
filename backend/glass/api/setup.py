from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from glass.auth import AuthUser, current_user
from glass.cache import slugify
from glass.db import acquire
from glass.workers.entity_extract import extract_entities_from_docket

router = APIRouter(tags=["setup"])


class SetupBody(BaseModel):
    docket: str = ""
    anticipation_c: bool = False


class SetupResult(BaseModel):
    state: str
    entities_count: int


async def _get_pool():
    """Thin wrapper so tests can stub Arq enqueue without touching real Redis."""
    from glass.workers.arq_settings import _get_pool as _real_get_pool

    return await _real_get_pool()


@router.post("/sessions/{session_id}/setup", response_model=SetupResult)
async def setup_session(
    session_id: UUID,
    body: SetupBody,
    user: AuthUser = Depends(current_user),
) -> SetupResult:
    async with acquire() as conn:
        owned = await conn.fetchval(
            """
            SELECT s.id FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = $1 AND u.clerk_user_id = $2
            """,
            session_id,
            user.clerk_user_id,
        )
        if owned is None:
            raise HTTPException(status_code=404, detail="session not found")

        await conn.execute(
            """
            UPDATE sessions
            SET setup_doc = $1, anticipation_c = $2
            WHERE id = $3
            """,
            body.docket,
            body.anticipation_c,
            session_id,
        )

    entities: list = []
    if body.docket.strip():
        entities = await extract_entities_from_docket(body.docket)

    by_slug: dict[str, tuple[str, str, int]] = {}
    for e in entities:
        s = slugify(e.name)
        if not s:
            continue
        existing = by_slug.get(s)
        if existing is None or e.salience > existing[2]:
            by_slug[s] = (e.name, e.kind, e.salience)

    inserted_ids: list[str] = []
    if by_slug:
        async with acquire() as conn:
            for slug, (name, kind, _salience) in by_slug.items():
                eid = await conn.fetchval(
                    """
                    INSERT INTO entities (session_id, slug, name, kind)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (session_id, slug) DO NOTHING
                    RETURNING id
                    """,
                    session_id,
                    slug,
                    name,
                    kind,
                )
                if eid is not None:
                    inserted_ids.append(str(eid))

    async with acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET state = 'ready' WHERE id = $1", session_id
        )

    if inserted_ids:
        pool = await _get_pool()
        for eid in inserted_ids:
            await pool.enqueue_job("entity_research_job", str(session_id), eid)

    return SetupResult(state="ready", entities_count=len(by_slug))
