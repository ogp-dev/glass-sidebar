import asyncio
import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from glass.api.app import create_app
from glass.events.bus import bus


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_dashboard_ws_receives_published_events(app) -> None:
    sid = str(uuid4())
    transport = ASGIWebSocketTransport(app=app)

    received: list[dict] = []

    async def publish_later() -> None:
        await asyncio.sleep(0.1)
        await bus.publish(sid, {"kind": "transcript_line", "text": "hi"})
        await bus.publish(sid, {"kind": "card", "id": "x"})

    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"/ws/dashboard/{sid}", client) as ws,
    ):
        publisher = asyncio.create_task(publish_later())
        for _ in range(2):
            msg = await asyncio.wait_for(ws.receive_text(), timeout=3.0)
            received.append(json.loads(msg))
        await publisher

    assert received == [
        {"kind": "transcript_line", "text": "hi"},
        {"kind": "card", "id": "x"},
    ]


@pytest.mark.asyncio
async def test_dashboard_ws_isolates_sessions(app) -> None:
    """A subscriber for session A should not receive events for session B."""
    sid_a = str(uuid4())
    sid_b = str(uuid4())
    transport = ASGIWebSocketTransport(app=app)

    received_a: list[dict] = []

    async def publish_to_b() -> None:
        await asyncio.sleep(0.05)
        await bus.publish(sid_b, {"kind": "irrelevant"})
        await asyncio.sleep(0.05)
        await bus.publish(sid_a, {"kind": "expected", "n": 1})

    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        aconnect_ws(f"/ws/dashboard/{sid_a}", client) as ws,
    ):
        publisher = asyncio.create_task(publish_to_b())
        msg = await asyncio.wait_for(ws.receive_text(), timeout=3.0)
        received_a.append(json.loads(msg))
        await publisher

    assert received_a == [{"kind": "expected", "n": 1}]
