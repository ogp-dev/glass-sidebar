import asyncio

import pytest


@pytest.mark.asyncio
async def test_control_publish_received_by_subscriber():
    from glass.events.bus import bus

    sid = "test-session-control-1"
    received: list[dict] = []

    async def consume():
        async for msg in bus.subscribe_control(sid):
            received.append(msg)
            return

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.1)  # let subscription register

    await bus.publish_control(sid, {"type": "shutdown"})
    await asyncio.wait_for(consumer, timeout=2.0)

    assert received == [{"type": "shutdown"}]


@pytest.mark.asyncio
async def test_control_channel_isolated_from_event_channel():
    """Publishing to the dashboard channel must NOT leak into control subscribers."""
    from glass.events.bus import bus

    sid = "test-session-control-2"
    received: list[dict] = []

    async def consume():
        async for msg in bus.subscribe_control(sid):
            received.append(msg)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    # publish to the DASHBOARD channel — control subscriber should NOT see it
    await bus.publish(sid, {"kind": "card", "id": "x"})
    await asyncio.sleep(0.15)

    consumer.cancel()
    try:
        await consumer
    except asyncio.CancelledError:
        pass
    assert received == []


@pytest.mark.asyncio
async def test_event_channel_isolated_from_control_channel():
    """Publishing to control channel must NOT leak into dashboard subscribers."""
    from glass.events.bus import bus

    sid = "test-session-control-3"
    received: list[dict] = []

    async def consume():
        async for msg in bus.subscribe(sid):
            received.append(msg)

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.1)

    await bus.publish_control(sid, {"type": "shutdown"})
    await asyncio.sleep(0.15)

    consumer.cancel()
    try:
        await consumer
    except asyncio.CancelledError:
        pass
    assert received == []
