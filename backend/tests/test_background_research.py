from uuid import uuid4

import pytest

from glass.cache import cache_clear, cache_get_entity
from glass.db import acquire
from glass.workers.background_research import research_entity
from glass.workers.research import SearchResult


@pytest.fixture(autouse=True)
async def _truncate_and_clear():
    yield
    async with acquire() as conn:
        await conn.execute(
            "TRUNCATE entities, claim_sources, claims, transcript_lines, "
            "session_speakers, sessions, users RESTART IDENTITY CASCADE"
        )
    await cache_clear()


@pytest.fixture
async def session_id() -> str:
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


@pytest.fixture
async def pending_entity(session_id: str) -> tuple[str, str]:
    """Insert an entity row in 'pending' state. Returns (session_id, entity_id)."""
    async with acquire() as conn:
        eid = await conn.fetchval(
            """
            INSERT INTO entities (session_id, slug, name, kind)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            session_id,
            "cerebras-systems",
            "Cerebras Systems",
            "company",
        )
    return session_id, str(eid)


@pytest.mark.asyncio
async def test_research_entity_writes_db_and_cache(
    pending_entity: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, eid = pending_entity

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://bloomberg.com/cerebras",
                title="Cerebras raises Series F",
                publisher="bloomberg.com",
                published_at=None,
                excerpt="Cerebras Systems closed a $1.1B Series F",
            ),
            SearchResult(
                url="https://cerebras.net/about",
                title="About Cerebras",
                publisher="cerebras.net",
                published_at=None,
                excerpt="We build the world's largest chip",
            ),
        ]

    monkeypatch.setattr(
        "glass.workers.background_research.search_for_claim", fake_search
    )

    await research_entity(sid, eid)

    # DB updated
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT slug, research_state, background, researched_at FROM entities WHERE id = $1",
            eid,
        )
        assert row["research_state"] == "done"
        assert row["researched_at"] is not None
        background = row["background"]
        # asyncpg returns jsonb as either dict or string depending on codec setup
        import json as _json

        if isinstance(background, str):
            background = _json.loads(background)
        assert background["name"] == "Cerebras Systems"
        assert len(background["sources"]) == 2

    # Cache populated
    cached = await cache_get_entity("cerebras-systems")
    assert cached is not None
    assert cached["name"] == "Cerebras Systems"
    assert len(cached["sources"]) == 2


@pytest.mark.asyncio
async def test_research_entity_no_results_marks_failed(
    pending_entity: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, eid = pending_entity

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return []

    monkeypatch.setattr(
        "glass.workers.background_research.search_for_claim", fake_search
    )

    await research_entity(sid, eid)

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT research_state FROM entities WHERE id = $1", eid
        )
        assert row["research_state"] == "failed"

    cached = await cache_get_entity("cerebras-systems")
    assert cached is None


@pytest.mark.asyncio
async def test_research_entity_missing_id_is_noop(session_id: str) -> None:
    """If the entity row was deleted between enqueue and run, don't crash."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    await research_entity(session_id, fake_uuid)


@pytest.mark.asyncio
async def test_research_entity_emits_heads_up_for_live_session(
    pending_entity: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, eid = pending_entity

    async with acquire() as conn:
        await conn.execute("UPDATE sessions SET state = 'live' WHERE id = $1", sid)

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://bloomberg.com/cerebras",
                title="Cerebras Series F",
                publisher="bloomberg.com",
                published_at=None,
                excerpt="...",
            )
        ]

    async def fake_notability(name: str, kind: str) -> int:
        return 3  # obscure → heads-up should be shown

    monkeypatch.setattr(
        "glass.workers.background_research.search_for_claim", fake_search
    )
    monkeypatch.setattr(
        "glass.workers.background_research.assess_notability", fake_notability
    )

    from glass.events.bus import bus

    received: list = []

    async def collect() -> None:
        async for ev in bus.subscribe(sid):
            received.append(ev)
            if any(e.get("state") == "heads_up" for e in received):
                break

    import asyncio

    collect_task = asyncio.create_task(collect())
    await asyncio.sleep(0.1)  # let Redis pubsub register

    await research_entity(sid, eid)
    await asyncio.wait_for(collect_task, timeout=3.0)

    heads_ups = [e for e in received if e.get("state") == "heads_up"]
    assert len(heads_ups) == 1
    assert heads_ups[0]["claim_text"] == "Cerebras Systems"
    assert heads_ups[0]["claim_type"] == "heads_up"
    assert heads_ups[0]["entity_kind"] == "company"
    assert heads_ups[0]["verdict"] == "Cerebras Series F (bloomberg.com)"


@pytest.mark.asyncio
async def test_research_entity_suppresses_heads_up_for_household_name(
    pending_entity: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live session still suppresses the heads-up card when the entity is a
    household name — a primer on a famous entity is noise. Research still runs,
    so the cache is warmed even though no card is surfaced."""
    sid, eid = pending_entity

    async with acquire() as conn:
        await conn.execute("UPDATE sessions SET state = 'live' WHERE id = $1", sid)

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://nvidia.com",
                title="NVIDIA",
                publisher="nvidia.com",
                published_at=None,
                excerpt="...",
            )
        ]

    async def fake_notability(name: str, kind: str) -> int:
        return 9  # household name → heads-up should be suppressed

    monkeypatch.setattr(
        "glass.workers.background_research.search_for_claim", fake_search
    )
    monkeypatch.setattr(
        "glass.workers.background_research.assess_notability", fake_notability
    )

    import asyncio
    import contextlib

    from glass.events.bus import bus

    received: list = []

    async def collect_for_a_bit() -> None:
        with contextlib.suppress(asyncio.CancelledError):
            async for ev in bus.subscribe(sid):
                received.append(ev)

    collect_task = asyncio.create_task(collect_for_a_bit())
    await asyncio.sleep(0.1)

    await research_entity(sid, eid)
    await asyncio.sleep(0.3)  # generous drain time
    collect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collect_task

    assert all(e.get("state") != "heads_up" for e in received)

    # Research still ran — the cache is warmed even though the card is hidden.
    cached = await cache_get_entity("cerebras-systems")
    assert cached is not None


@pytest.mark.asyncio
async def test_emit_docket_heads_ups_gates_by_notability(
    session_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On go-live, docket entities already researched pre-show surface as
    heads-up cards — but the notability gate still hides household names."""
    import json as _json

    bg = _json.dumps(
        {
            "name": "x",
            "kind": "company",
            "sources": [
                {
                    "url": "https://x.com",
                    "title": "T",
                    "publisher": "x.com",
                    "published_at": None,
                    "excerpt": "...",
                }
            ],
        }
    )
    async with acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET state = 'live' WHERE id = $1", session_id
        )
        await conn.execute(
            """
            INSERT INTO entities
                (session_id, slug, name, kind, research_state, background)
            VALUES
                ($1, 'nvidia', 'NVIDIA', 'company', 'done', $2::jsonb),
                ($1, 'tiny-startup', 'Tiny Startup', 'company', 'done', $2::jsonb)
            """,
            session_id,
            bg,
        )

    async def fake_notability(name: str, kind: str) -> int:
        return 9 if name == "NVIDIA" else 3

    monkeypatch.setattr(
        "glass.workers.background_research.assess_notability", fake_notability
    )

    import asyncio
    import contextlib

    from glass.events.bus import bus
    from glass.workers.background_research import emit_docket_heads_ups

    received: list = []

    async def collect_for_a_bit() -> None:
        with contextlib.suppress(asyncio.CancelledError):
            async for ev in bus.subscribe(session_id):
                received.append(ev)

    collect_task = asyncio.create_task(collect_for_a_bit())
    await asyncio.sleep(0.1)

    await emit_docket_heads_ups(session_id)
    await asyncio.sleep(0.3)
    collect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collect_task

    heads_ups = [e for e in received if e.get("state") == "heads_up"]
    assert len(heads_ups) == 1
    assert heads_ups[0]["claim_text"] == "Tiny Startup"


@pytest.mark.asyncio
async def test_research_entity_no_heads_up_for_draft_session(
    pending_entity: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-show research (session state='draft' or 'ready') warms the cache
    but should NOT publish heads-up cards."""
    sid, eid = pending_entity

    async def fake_search(query: str, *, num_results: int = 4) -> list[SearchResult]:
        return [
            SearchResult(
                url="https://x.com/y",
                title="Some Source",
                publisher="x.com",
                published_at=None,
                excerpt="...",
            )
        ]

    monkeypatch.setattr(
        "glass.workers.background_research.search_for_claim", fake_search
    )

    import asyncio
    import contextlib

    from glass.events.bus import bus

    received: list = []

    async def collect_for_a_bit() -> None:
        with contextlib.suppress(asyncio.CancelledError):
            async for ev in bus.subscribe(sid):
                received.append(ev)

    collect_task = asyncio.create_task(collect_for_a_bit())
    await asyncio.sleep(0.1)

    await research_entity(sid, eid)
    await asyncio.sleep(0.3)  # generous drain time
    collect_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collect_task

    assert all(e.get("state") != "heads_up" for e in received)
