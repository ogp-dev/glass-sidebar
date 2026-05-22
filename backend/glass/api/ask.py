"""POST /api/sessions/:id/ask — Ask Glass manual verification endpoint."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from glass.auth import AuthUser, current_user

router = APIRouter(tags=["ask"])


class AskBody(BaseModel):
    """Exactly one of `query` or `action` must be provided."""

    query: str | None = None
    action: Literal["verify_last", "rescan_30s"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "AskBody":
        if (self.query is None) == (self.action is None):
            raise ValueError("provide exactly one of: query, action")
        if self.query is not None and not self.query.strip():
            raise ValueError("query must not be empty")
        return self


@router.post("/sessions/{session_id}/ask", status_code=202)
async def ask_glass(
    session_id: UUID,
    body: AskBody,
    user: AuthUser = Depends(current_user),
) -> dict[str, str]:
    """Enqueue a manual_verify_job. Returns the job_id for client tracking.

    The job runs asynchronously on the Arq worker and publishes a `card` event
    on the dashboard channel when it completes.
    """
    from glass.workers.arq_settings import _get_pool

    if body.query is not None:
        payload: dict = {"query": body.query.strip()}
    else:
        assert body.action is not None  # validated above
        payload = {"action": body.action}

    try:
        pool = await _get_pool()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"queue unavailable: {exc}")

    job = await pool.enqueue_job("manual_verify_job", str(session_id), payload)
    return {
        "job_id": job.job_id if job is not None else "unknown",
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }
