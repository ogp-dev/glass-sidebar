import pytest

from glass.cache import (
    cache_clear,
    cache_get_claim,
    cache_get_entity,
    cache_set_claim,
    cache_set_entity,
    slugify,
)


@pytest.fixture(autouse=True)
async def _clear_cache():
    yield
    await cache_clear()


def test_slugify_basic() -> None:
    assert slugify("Cerebras Systems") == "cerebras-systems"
    assert slugify("  Jason  CALACANIS  ") == "jason-calacanis"
    assert slugify("AT&T") == "at-t"
    assert slugify("$1.2B raise") == "1-2b-raise"


def test_slugify_strips_leading_trailing_dashes() -> None:
    assert slugify("---Cerebras---") == "cerebras"
    assert slugify("!!!") == ""


def test_coerce_published_at() -> None:
    """Cached source payloads carry published_at as an ISO string; the
    claim_sources insert needs a real date object (asyncpg rejects str)."""
    from datetime import date

    from glass.workers.arq_settings import _coerce_published_at

    assert _coerce_published_at("2026-05-14") == date(2026, 5, 14)
    assert _coerce_published_at("2021-10-30T08:00:00Z") == date(2021, 10, 30)
    assert _coerce_published_at(date(2024, 1, 2)) == date(2024, 1, 2)
    assert _coerce_published_at(None) is None
    assert _coerce_published_at("") is None
    assert _coerce_published_at("not-a-date") is None


@pytest.mark.asyncio
async def test_cache_set_get_entity_roundtrip() -> None:
    payload = {"name": "Cerebras Systems", "kind": "company", "summary": "AI chip co"}
    await cache_set_entity("cerebras-systems", payload, ttl_sec=60)
    got = await cache_get_entity("cerebras-systems")
    assert got == payload


@pytest.mark.asyncio
async def test_cache_miss_returns_none() -> None:
    assert await cache_get_entity("no-such-entity") is None


@pytest.mark.asyncio
async def test_cache_set_get_claim_roundtrip() -> None:
    payload = {"verdict": "verified", "sources": [{"url": "https://x"}]}
    await cache_set_claim("abc123", payload, ttl_sec=60)
    got = await cache_get_claim("abc123")
    assert got == payload


@pytest.mark.asyncio
async def test_cache_clear_wipes_all_glass_keys() -> None:
    await cache_set_entity("a", {"x": 1}, ttl_sec=60)
    await cache_set_claim("b", {"y": 2}, ttl_sec=60)
    await cache_clear()
    assert await cache_get_entity("a") is None
    assert await cache_get_claim("b") is None
