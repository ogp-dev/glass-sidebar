import asyncio
import contextlib
import json
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from glass.db import acquire
from glass.events.bus import bus
from glass.stt.deepgram_client import DeepgramStream
from glass.stt.transcript_store import insert_line

log = structlog.get_logger(__name__)

router = APIRouter()


async def _maybe_enqueue_trajectory(session_id: str, window_end_ms: int) -> bool:
    """Enqueue a trajectory job if 20s have passed since the last one.

    Uses Redis SET NX EX as a distributed lock with TTL — only one process
    can claim the slot at a time, and the lock auto-expires after 20s so the
    next tick can fire. Returns True if a job was enqueued.
    """
    from glass.cache import _client

    redis = await _client()
    key = f"glass:throttle:trajectory:{session_id}"
    acquired = await redis.set(key, "1", ex=20, nx=True)
    if not acquired:
        return False

    from glass.workers.arq_settings import _get_pool

    pool = await _get_pool()
    await pool.enqueue_job("trajectory_job", session_id, window_end_ms)
    return True


async def _drain_audio_only(websocket: WebSocket, sid: str) -> None:
    """Dev fallback when Deepgram is unavailable. Just consume frames so the
    WS handshake completes; log a heartbeat every 100 frames."""
    frames = 0
    try:
        while True:
            await websocket.receive_bytes()
            frames += 1
            if frames % 100 == 0:
                log.info("audio_ws.drain_heartbeat", session_id=sid, frames=frames)
    except WebSocketDisconnect:
        log.info(
            "audio_ws.drain_disconnect", session_id=sid, frames_drained=frames
        )


# Sentinel value pushed into audio_q / text_q when the demux loop sees the
# client disconnect. Consumers treat this as EOF and exit their own loops.
_EOF_BYTES = b""
_EOF_TEXT = ""


@router.websocket("/ws/audio/{session_id}")
async def audio_ws(websocket: WebSocket, session_id: UUID) -> None:
    # TODO(security): in production, validate ?token= against the host's session.
    # v1 trusts the session_id issued by /api/sessions; we skip strict check.
    await websocket.accept()
    sid = str(session_id)

    # The browser mic and the Mac helper BOTH connect to this endpoint. Only
    # the helper sends guest system-audio (channel 0x02) frames — so
    # helper_status is keyed on the first 0x02 frame (see forward_audio),
    # never on the bare connection. Emitting it on accept made the browser
    # mic's own connection look like "the helper", which the dashboard's
    # auto-connect chased into a reconnect loop.
    helper_seen = False

    # Transition session to 'live'. RETURNING tells us whether this was a
    # genuine draft/ready -> live transition (vs. a helper reconnecting to an
    # already-live session) so the docket heads-up sweep fires exactly once.
    async with acquire() as conn:
        went_live = await conn.fetchval(
            """
            UPDATE sessions
            SET state = 'live', started_at = COALESCE(started_at, now())
            WHERE id = $1 AND state IS DISTINCT FROM 'live'
            RETURNING id
            """,
            session_id,
        )

    if went_live is not None:
        # Surface heads-up cards for entities the docket pre-researched — until
        # now they only warmed the cache. Runs on the worker.
        from glass.workers.arq_settings import _get_pool

        pool = await _get_pool()
        await pool.enqueue_job("docket_heads_ups_job", sid)

    # Look up entity names for this session — pre-researched entities (from
    # the docket OR from earlier trajectory predictions) become Deepgram
    # keyword boosts so the STT prefers their spelling over phonetically
    # similar words. This is the docket → STT feedback loop.
    async with acquire() as conn:
        entity_rows = await conn.fetch(
            "SELECT name FROM entities WHERE session_id = $1", session_id
        )
    keywords = [row["name"] for row in entity_rows]
    log.info("audio_ws.deepgram_keywords", session_id=sid, keywords=keywords)

    # Two Deepgram streams: dg_host for the host mic (channel 0x01), dg_guest
    # for the guest's system audio (channel 0x02). Separate streams keep the
    # two voices cleanly attributed and let each transcribe independently.
    #
    # Receiver-only fallback: when Deepgram refuses (e.g. placeholder API key
    # in dev), drain audio frames so the Mac helper observes a working WS
    # handshake instead of an immediate close. We still surface the failure
    # in logs so it's not silently swallowed.
    dg_host = DeepgramStream(keywords=keywords)
    dg_guest = DeepgramStream(keywords=keywords)
    try:
        await dg_host.open()
        await dg_guest.open()
    except Exception as exc:  # noqa: BLE001 — broad on purpose for graceful degrade
        log.error("audio_ws.deepgram_open_failed", session_id=sid, error=str(exc))
        for stream in (dg_host, dg_guest):
            with contextlib.suppress(Exception):
                await stream.close()
        try:
            await _drain_audio_only(websocket, sid)
        finally:
            with contextlib.suppress(RuntimeError):
                await websocket.close()
        return

    # FastAPI's WebSocket has separate receive_bytes() / receive_text() helpers
    # but they're mutually exclusive — once you start receive_bytes you can't
    # read text on the same socket. One demux task owns ALL WS reads and routes
    # to two queues; consumers don't touch the socket directly.
    audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
    text_q: asyncio.Queue[str] = asyncio.Queue(maxsize=64)

    async def demux_inbound() -> None:
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect()
                if msg.get("bytes") is not None:
                    with contextlib.suppress(asyncio.QueueFull):
                        audio_q.put_nowait(msg["bytes"])
                elif msg.get("text") is not None:
                    with contextlib.suppress(asyncio.QueueFull):
                        text_q.put_nowait(msg["text"])
        except WebSocketDisconnect:
            log.info("audio_ws.client_disconnect", session_id=sid)
            # Wake up consumers so they exit
            with contextlib.suppress(asyncio.QueueFull):
                audio_q.put_nowait(_EOF_BYTES)
            with contextlib.suppress(asyncio.QueueFull):
                text_q.put_nowait(_EOF_TEXT)

    async def forward_audio() -> None:
        """Demux PCM frames to the two Deepgram streams.

        Frame format from the helper: 1 byte channel tag (0x01 mic /
        0x02 system) followed by raw PCM. The mic carries the host, system
        audio carries the guest — each goes to its own Deepgram stream so
        the two voices stay cleanly separated.
        """
        nonlocal helper_seen
        host_frames = 0
        guest_frames = 0
        while True:
            frame = await audio_q.get()
            if frame == _EOF_BYTES:
                log.info(
                    "audio_ws.forward_audio_end",
                    session_id=sid,
                    host_frames=host_frames,
                    guest_frames=guest_frames,
                )
                return  # disconnect sentinel
            if len(frame) < 2:
                continue
            channel_tag = frame[0]
            pcm = frame[1:]
            if channel_tag == 0x01:  # host mic
                await dg_host.send_audio(pcm)
                host_frames += 1
                if host_frames == 1 or host_frames % 250 == 0:
                    log.info(
                        "audio_ws.host_to_deepgram",
                        session_id=sid,
                        host_frames=host_frames,
                        frame_bytes=len(pcm),
                    )
            elif channel_tag == 0x02:  # guest system audio
                if not helper_seen:
                    # First system-audio frame — this connection is the Mac
                    # helper (the browser mic only ever sends 0x01).
                    helper_seen = True
                    await bus.publish(
                        sid, {"kind": "helper_status", "connected": True}
                    )
                await dg_guest.send_audio(pcm)
                guest_frames += 1
                if guest_frames == 1 or guest_frames % 250 == 0:
                    log.info(
                        "audio_ws.guest_to_deepgram",
                        session_id=sid,
                        guest_frames=guest_frames,
                        frame_bytes=len(pcm),
                    )

    async def forward_transcripts(stream: DeepgramStream, role: str) -> None:
        """Publish one Deepgram stream's results.

        role is "host" or "guest" — a stable binary, derived from the audio
        channel (mic vs system), so the label never flips. The host is "You",
        everything on the guest's system-audio stream is "Guest". (Telling
        multiple distinct guests apart reliably needs voice fingerprinting —
        deferred; diarization alone is too unstable.)
        """
        label = "You" if role == "host" else "Guest"
        async for result in stream.results():
            if not result.is_final:
                await bus.publish(
                    sid,
                    {
                        "kind": "transcript_partial",
                        "text": result.text,
                        "start_ms": result.start_ms,
                        "end_ms": result.end_ms,
                        "speaker_label": label,
                    },
                )
                continue

            line = await insert_line(
                sid,
                text=result.text,
                start_ms=result.start_ms,
                end_ms=result.end_ms,
                is_final=True,
                speaker=label,
            )
            await bus.publish(
                sid,
                {
                    "kind": "transcript_line",
                    "id": str(line.id),
                    "text": line.text,
                    "start_ms": line.start_ms,
                    "end_ms": line.end_ms,
                    "speaker_label": label,
                },
            )
            from glass.workers.arq_settings import enqueue_claim_detect

            await enqueue_claim_detect(sid, result.end_ms)
            await _maybe_enqueue_trajectory(sid, result.end_ms)

    async def keepalive_streams() -> None:
        """Ping both Deepgram streams every 5s so an idle one (guest silent,
        nothing playing) doesn't hit Deepgram's ~10s idle timeout — a closed
        stream would end its results() loop and tear the session down."""
        while True:
            await asyncio.sleep(5)
            for stream in (dg_host, dg_guest):
                with contextlib.suppress(Exception):
                    await stream.keep_alive()

    async def process_helper_text() -> None:
        """Drain text frames from the helper (RMS, future kinds)."""
        while True:
            raw = await text_q.get()
            if raw == _EOF_TEXT:
                return  # disconnect sentinel
            try:
                obj = json.loads(raw)
            except (TypeError, ValueError):
                continue
            kind = obj.get("type")
            if kind == "rms":
                await bus.publish(
                    sid,
                    {
                        "kind": "rms",
                        "mic": float(obj.get("mic", 0.0)),
                        "sys": float(obj.get("sys", 0.0)),
                    },
                )
            # Other helper text kinds reserved for Plan D.

    async def forward_control_to_helper() -> None:
        """Subscribe to control channel; forward each message as a text frame.

        Used by POST /sessions/:id/stop to push {"type":"shutdown"} so the
        helper closes its audio engine gracefully.
        """
        async for msg in bus.subscribe_control(sid):
            try:
                await websocket.send_text(json.dumps(msg))
            except Exception as exc:  # noqa: BLE001
                log.warning("audio_ws.control_forward_failed", error=str(exc))
                return

    tasks = {
        asyncio.create_task(demux_inbound()),
        asyncio.create_task(forward_audio()),
        asyncio.create_task(forward_transcripts(dg_host, "host")),
        asyncio.create_task(forward_transcripts(dg_guest, "guest")),
        asyncio.create_task(process_helper_text()),
        asyncio.create_task(forward_control_to_helper()),
        asyncio.create_task(keepalive_streams()),
    }
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # As soon as ANY task completes the WS lifetime is over. If this
        # connection was the helper (it sent system audio), tell the dashboard
        # so it falls back to the browser mic.
        if helper_seen:
            await bus.publish(sid, {"kind": "helper_status", "connected": False})
        for p in pending:
            p.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await p
    finally:
        await dg_host.close()
        await dg_guest.close()
        with contextlib.suppress(RuntimeError):
            await websocket.close()
