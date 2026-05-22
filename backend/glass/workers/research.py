import asyncio
import random
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

import structlog
from exa_py import Exa

log = structlog.get_logger(__name__)

_exa: Any = None  # Lazy-initialized below


def _exa_or_init() -> Any:
    global _exa
    if _exa is None:
        from glass.config import settings

        _exa = Exa(settings.exa_api_key)
    return _exa


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    publisher: str
    published_at: date | None
    excerpt: str


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _publisher_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")


async def search_for_claim(
    claim_text: str, *, num_results: int = 4
) -> list[SearchResult]:
    """Search Exa for sources backing a claim. Returns top `num_results`.

    Exa SDK is synchronous — we offload to a thread to stay async-clean.
    """
    exa = _exa_or_init()
    loop = asyncio.get_running_loop()

    def _do_search() -> Any:
        return exa.search_and_contents(
            claim_text, num_results=num_results, text=True
        )

    raw = None
    for attempt in range(4):
        try:
            raw = await loop.run_in_executor(None, _do_search)
            break
        except ValueError as exc:
            # Exa raises ValueError("Request failed with status code 429 ...")
            # when its 10 req/s rate limit is exceeded — a docket fan-out
            # bursts past it. Back off (jittered, so retries don't re-burst
            # in lockstep) and retry; the burst clears within ~1s.
            if "429" not in str(exc) or attempt == 3:
                raise
            await asyncio.sleep(1.0 + attempt + random.random())
    assert raw is not None  # the loop above either set raw or raised

    out: list[SearchResult] = []
    for r in raw.results:
        out.append(
            SearchResult(
                url=r.url,
                title=getattr(r, "title", "") or "",
                publisher=_publisher_from_url(r.url),
                published_at=_parse_date(getattr(r, "published_date", None)),
                excerpt=(getattr(r, "text", "") or "")[:600],
            )
        )
    return out
