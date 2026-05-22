import asyncio
import contextlib
import json
from uuid import uuid4

import httpx
import pytest
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from glass.api.app import create_app
from glass.db import acquire
from glass.events.bus import bus
from glass.stt.deepgram_client import TranscriptResult


class _FakeDeepgramStream:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def send_audio(self, frame: bytes) -> None:
        pass

    async def results(self):
        # block forever — these tests don't care about transcripts
        await asyncio.sleep(60)
        if False:
            yield TranscriptResult(text="", start_ms=0, end_ms=0, is_final=True, speaker_label="")

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
    monkeypatch.setattr(
        "glass.api.ws_audio.DeepgramStream",
        lambda **kwargs: _FakeDeepgramStream(),
    )
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
async def test_helper_status_connected_emitted_on_first_system_frame(app) -> None:
    """helper_status:connected lands on the bus when the helper's first
    system-audio (0x02) frame arrives — the helper is the only client that
    sends that channel."""
    sid = await _setup_session()

    received: list[dict] = []
    got_connected = asyncio.Event()

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)
            if ev.get("kind") == "helper_status" and ev.get("connected") is True:
                got_connected.set()
                return

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    transport = ASGIWebSocketTransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws,
    ):
        await ws.send_bytes(b"\x02guest-pcm")
        await asyncio.wait_for(got_connected.wait(), timeout=3.0)

    await asyncio.wait_for(collect_task, timeout=2.0)

    assert any(
        e.get("kind") == "helper_status" and e.get("connected") is True
        for e in received
    )


@pytest.mark.asyncio
async def test_browser_mic_connection_emits_no_helper_status(app) -> None:
    """A client that only sends host-mic (0x01) frames — i.e. the browser mic —
    must NOT trigger any helper_status event. Emitting one on the bare
    connection made the browser mic look like the helper and drove a
    reconnect loop."""
    sid = await _setup_session()

    received: list[dict] = []

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    transport = ASGIWebSocketTransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        async with aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws:
            await ws.send_bytes(b"\x01host-pcm")
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.2)

    collect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collect_task

    assert not any(e.get("kind") == "helper_status" for e in received)


@pytest.mark.asyncio
async def test_helper_status_disconnected_emitted_when_helper_ws_closes(app) -> None:
    """After the helper has been seen (it sent a system-audio frame), closing
    its WS emits helper_status:disconnected."""
    sid = await _setup_session()

    received: list[dict] = []
    got_disconnected = asyncio.Event()

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)
            if ev.get("kind") == "helper_status" and ev.get("connected") is False:
                got_disconnected.set()
                return

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    transport = ASGIWebSocketTransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws:
            await ws.send_bytes(b"\x02guest-pcm")
            await asyncio.sleep(0.1)
        # WS closed here; disconnect fires because the helper was seen
        await asyncio.wait_for(got_disconnected.wait(), timeout=3.0)

    await asyncio.wait_for(collect_task, timeout=2.0)

    assert any(
        e.get("kind") == "helper_status" and e.get("connected") is False
        for e in received
    )


@pytest.mark.asyncio
async def test_rms_text_frame_from_helper_forwarded_to_dashboard(app) -> None:
    """Helper sends `{"type":"rms",...}` as a text frame → backend publishes
    `{"kind":"rms",...}` on the dashboard channel."""
    sid = await _setup_session()

    received: list[dict] = []
    got_rms = asyncio.Event()

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)
            if ev.get("kind") == "rms":
                got_rms.set()
                return

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0)

    transport = ASGIWebSocketTransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws,
    ):
        await ws.send_text(json.dumps({"type": "rms", "mic": 0.42, "sys": 0.08, "ts_ms": 12345}))
        await asyncio.wait_for(got_rms.wait(), timeout=3.0)

    await asyncio.wait_for(collect_task, timeout=2.0)

    rms = next((e for e in received if e["kind"] == "rms"), None)
    assert rms is not None
    assert rms["mic"] == pytest.approx(0.42)
    assert rms["sys"] == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_control_shutdown_forwarded_as_text_frame_to_helper(app) -> None:
    """When backend publishes to the control channel, the helper's WS receives
    the JSON as a text frame."""
    sid = await _setup_session()

    transport = ASGIWebSocketTransport(app=app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"http://test/ws/audio/{sid}", client) as ws,
    ):
        # Give the audio WS a tick to register its control subscription
        await asyncio.sleep(0.15)

        await bus.publish_control(sid, {"type": "shutdown"})

        # Helper-side: read a text frame off the WS
        msg = await asyncio.wait_for(ws.receive_text(), timeout=3.0)
        parsed = json.loads(msg)
        assert parsed == {"type": "shutdown"}
