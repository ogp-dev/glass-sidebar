import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

import redis.asyncio as aioredis


def _json_default(obj: Any) -> str:
    """JSON encoder for types asyncpg returns from jsonb_agg (date, datetime)."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


_CHANNEL_PREFIX = "glass:events:"
_CONTROL_PREFIX = "glass:control:"


def _channel(session_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{session_id}"


def _control_channel(session_id: str) -> str:
    return f"{_CONTROL_PREFIX}{session_id}"


class EventBus:
    """Cross-process pub/sub keyed by session_id, backed by Redis.

    Backend (uvicorn) and worker (arq) run as separate Python processes —
    in-process queues would never see each other. Redis Pub/Sub gives both
    a shared channel namespace. v1.x; full streaming with replay (Streams)
    is a Phase 3 upgrade if we need durability across reconnects.

    Usage::

        async for event in bus.subscribe(session_id):
            handle(event)
            if done:
                break

    The Redis pubsub connection is unsubscribed + closed as soon as the
    ``async for`` loop exits (try/finally inside __anext__'s generator).
    """

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def _redis(self) -> aioredis.Redis:
        if self._client is None:
            from glass.config import settings

            self._client = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        client = await self._redis()
        payload = json.dumps(event, default=_json_default)
        await client.publish(_channel(session_id), payload)

    def subscribe(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Return an async iterator for *session_id* events."""
        return _Subscription(self, session_id)

    async def publish_control(self, session_id: str, msg: dict[str, Any]) -> None:
        """Publish to the separate control channel used by ws_audio to receive
        out-of-band commands (e.g. shutdown from POST /stop).
        """
        client = await self._redis()
        payload = json.dumps(msg, default=_json_default)
        await client.publish(_control_channel(session_id), payload)

    def subscribe_control(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Return an async iterator for *session_id* control-channel messages."""
        return _Subscription(self, session_id, channel_fn=_control_channel)


class _Subscription:
    """Async iterator that owns a dedicated Redis pubsub connection.

    Cleanup happens in __anext__'s finally when the consumer breaks out of
    the async for loop, AND in __del__ as a belt-and-suspenders fallback.
    """

    def __init__(
        self,
        bus: EventBus,
        session_id: str,
        channel_fn: "callable[[str], str]" = _channel,  # type: ignore[name-defined]
    ) -> None:
        self._bus = bus
        self._session_id = session_id
        self._channel_fn = channel_fn
        self._pubsub: aioredis.client.PubSub | None = None
        self._task: asyncio.Task[None] | None = None
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        self._closed = False

    def __aiter__(self) -> "_Subscription":
        return self

    async def _ensure_started(self) -> None:
        if self._pubsub is not None:
            return
        client = await self._bus._redis()
        self._pubsub = client.pubsub()
        await self._pubsub.subscribe(self._channel_fn(self._session_id))
        # Background pump: read from pubsub, push to our local queue
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message is None or message.get("type") != "message":
                    continue
                raw = message.get("data")
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                with contextlib.suppress(asyncio.QueueFull):
                    self._q.put_nowait(event)
        except asyncio.CancelledError:
            return

    async def __anext__(self) -> dict[str, Any]:
        await self._ensure_started()
        try:
            return await self._q.get()
        except asyncio.CancelledError:
            await self._aclose()
            raise

    async def _aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self._channel_fn(self._session_id))
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()
            self._pubsub = None

    def __del__(self) -> None:
        if self._closed or self._task is None:
            return
        with contextlib.suppress(Exception):
            self._task.cancel()


# Process-wide singleton. Both backend and worker reach the same Redis
# server, so a publish from one is seen by subscribers in the other.
bus = EventBus()
