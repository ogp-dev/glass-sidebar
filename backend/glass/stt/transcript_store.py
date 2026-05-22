from uuid import UUID

from glass.db import acquire
from glass.models import TranscriptLine


async def insert_line(
    session_id: str | UUID,
    *,
    text: str,
    start_ms: int,
    end_ms: int,
    is_final: bool,
    speaker: str | None = None,
    speaker_id: UUID | None = None,
) -> TranscriptLine:
    """Append a transcript line. Returns the inserted row.

    `speaker` is the plain "You" / "Guest" label (migration 0004) — that is
    what claim attribution and the dashboard use.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO transcript_lines
                (session_id, speaker_id, speaker, text, start_ms, end_ms,
                 is_final)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            UUID(str(session_id)),
            speaker_id,
            speaker,
            text,
            start_ms,
            end_ms,
            is_final,
        )
    return TranscriptLine.model_validate(dict(row))


async def recent_lines(
    session_id: str | UUID,
    *,
    window_ms: int = 60_000,
    now_ms: int | None = None,
) -> list[TranscriptLine]:
    """Return finalized lines from the last `window_ms` ms.

    Window is anchored at `now_ms` if given, otherwise at the most recent
    end_ms in the session.
    """
    async with acquire() as conn:
        if now_ms is None:
            now_ms = (
                await conn.fetchval(
                    "SELECT COALESCE(MAX(end_ms), 0) FROM transcript_lines "
                    "WHERE session_id = $1",
                    UUID(str(session_id)),
                )
                or 0
            )
        cutoff = max(0, now_ms - window_ms)
        rows = await conn.fetch(
            """
            SELECT * FROM transcript_lines
            WHERE session_id = $1 AND is_final = TRUE AND end_ms > $2
            ORDER BY start_ms
            """,
            UUID(str(session_id)),
            cutoff,
        )
    return [TranscriptLine.model_validate(dict(r)) for r in rows]
