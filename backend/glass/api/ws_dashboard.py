import asyncio
import contextlib
import json
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from glass.events.bus import bus

log = structlog.get_logger(__name__)

router = APIRouter()


@router.websocket("/ws/dashboard/{session_id}")
async def dashboard_ws(websocket: WebSocket, session_id: UUID) -> None:
    await websocket.accept()
    sid = str(session_id)

    async def send_events() -> None:
        async for event in bus.subscribe(sid):
            await websocket.send_text(json.dumps(event))

    async def wait_for_disconnect() -> None:
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            log.info("dashboard_ws.disconnect", session_id=sid)

    send_task = asyncio.create_task(send_events())
    disconnect_task = asyncio.create_task(wait_for_disconnect())

    _, pending = await asyncio.wait(
        {send_task, disconnect_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    with contextlib.suppress(RuntimeError):
        await websocket.close()
