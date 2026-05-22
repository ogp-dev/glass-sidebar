import asyncio
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from glass.api.app import create_app
from glass.db import acquire
from glass.events.bus import bus
from glass.stt.deepgram_client import TranscriptResult


class _FakeDeepgramStream:
    def __init__(self, scripted: list[TranscriptResult]) -> None:
        self._scripted = scripted
        self.opened = False
        self.closed = False
        self.received_chunks: list[bytes] = []

    async def open(self) -> None:
        self.opened = True

    async def send_audio(self, frame: bytes) -> None:
        self.received_chunks.append(frame)

    async def results(self):
        for r in self._scripted:
            await asyncio.sleep(0)
            yield r
        # block so the WS doesn't tear down before we observe events
        await asyncio.sleep(60)

    async def keep_alive(self) -> None:
        pass

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
async def _truncate_after():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE claim_sources, claims, transcript_lines, session_speakers, "
            "sessions, users RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    # ws_audio opens two streams in order: host (mic) first, guest (system)
    # second. Hand each its own script so the test can tell them apart.
    host_scripted = [
        TranscriptResult(
            text="hello",
            start_ms=0,
            end_ms=1000,
            is_final=False,
            speaker_label="Speaker 0",
        ),
        TranscriptResult(
            text="hello world",
            start_ms=0,
            end_ms=1500,
            is_final=True,
            speaker_label="Speaker 0",
        ),
    ]
    guest_scripted = [
        TranscriptResult(
            text="guest speaking",
            start_ms=0,
            end_ms=1500,
            is_final=True,
            speaker_label="Speaker 0",
        ),
    ]
    pending = [host_scripted, guest_scripted]

    def _make_stream(**_kwargs):
        script = pending.pop(0) if pending else []
        return _FakeDeepgramStream(script)

    monkeypatch.setattr("glass.api.ws_audio.DeepgramStream", _make_stream)
    return create_app()


async def _setup_session() -> str:
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


@pytest.mark.asyncio
async def test_audio_ws_dual_stream_host_and_guest(app) -> None:
    """Host (mic, 0x01) and guest (system, 0x02) each transcribe on their own
    Deepgram stream, labelled "You" and "Guest" respectively."""
    sid = await _setup_session()

    received: list[dict] = []
    got_both = asyncio.Event()

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)
            finals = [e for e in received if e.get("kind") == "transcript_line"]
            if len(finals) >= 2:
                got_both.set()
                break

    collect_task = asyncio.create_task(collect())
    # Yield so the subscriber queue is registered before we open the WS
    await asyncio.sleep(0)

    transport = ASGIWebSocketTransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws,
    ):
        await ws.send_bytes(b"\x01host-pcm")
        await ws.send_bytes(b"\x02guest-pcm")
        await asyncio.wait_for(got_both.wait(), timeout=5.0)

    await asyncio.wait_for(collect_task, timeout=2.0)

    finals = [e for e in received if e["kind"] == "transcript_line"]
    assert len(finals) == 2
    by_label = {e["speaker_label"]: e["text"] for e in finals}
    assert by_label["You"] == "hello world"
    assert by_label["Guest"] == "guest speaking"

    # Both lines landed in Postgres
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT text FROM transcript_lines WHERE session_id = $1", sid
        )
    assert {r["text"] for r in rows} == {"hello world", "guest speaking"}

    # Session should now be in 'live' state with started_at set
    async with acquire() as conn:
        session_row = await conn.fetchrow(
            "SELECT state, started_at FROM sessions WHERE id = $1", sid
        )
    assert session_row["state"] == "live"
    assert session_row["started_at"] is not None


@pytest_asyncio.fixture
async def _clear_throttle():
    from glass.cache import _client

    redis = await _client()
    await redis.delete("glass:throttle:trajectory:s1")
    yield
    await redis.delete("glass:throttle:trajectory:s1")


@pytest.mark.asyncio
async def test_maybe_enqueue_trajectory_throttles(
    _clear_throttle, monkeypatch: pytest.MonkeyPatch
) -> None:
    from glass.api.ws_audio import _maybe_enqueue_trajectory

    enqueued: list = []

    class _FakePool:
        async def enqueue_job(self, name: str, *args) -> None:
            enqueued.append((name, args))

    async def fake_get_pool():
        return _FakePool()

    monkeypatch.setattr("glass.workers.arq_settings._get_pool", fake_get_pool)

    # First call should enqueue
    first = await _maybe_enqueue_trajectory("s1", 1000)
    assert first is True
    assert len(enqueued) == 1

    # Second call within TTL should NOT enqueue
    second = await _maybe_enqueue_trajectory("s1", 2000)
    assert second is False
    assert len(enqueued) == 1
