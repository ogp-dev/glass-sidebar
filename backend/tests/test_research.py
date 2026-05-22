from datetime import date

import pytest

from glass.workers.research import SearchResult, search_for_claim


@pytest.mark.asyncio
async def test_search_for_claim_returns_top_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeExaResult:
        def __init__(self, url: str, title: str, text: str, published_date: str) -> None:
            self.url = url
            self.title = title
            self.text = text
            self.published_date = published_date

    class _FakeExaResponse:
        def __init__(self, results: list) -> None:
            self.results = results

    class _FakeExa:
        def search_and_contents(self, query: str, **kwargs) -> _FakeExaResponse:
            return _FakeExaResponse(
                [
                    _FakeExaResult(
                        "https://www.bloomberg.com/x",
                        "Cerebras raises $1.1B Series F",
                        "Cerebras Systems closed a $1.1 billion Series F round...",
                        "2024-09-12",
                    ),
                    _FakeExaResult(
                        "https://cerebras.net/press",
                        "Cerebras announces funding",
                        "Today Cerebras announced the close of...",
                        "2024-09-12",
                    ),
                ]
            )

    monkeypatch.setattr("glass.workers.research._exa", _FakeExa())

    results = await search_for_claim("Cerebras raised $1.2 billion")
    assert len(results) == 2
    assert isinstance(results[0], SearchResult)
    assert results[0].publisher == "bloomberg.com"  # www. stripped
    assert results[0].published_at == date(2024, 9, 12)
    assert "Cerebras" in results[0].excerpt


@pytest.mark.asyncio
async def test_search_for_claim_handles_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Bare:
        def __init__(self, url: str) -> None:
            self.url = url
            self.title = None
            self.text = None
            self.published_date = None

    class _FakeExa:
        def search_and_contents(self, query: str, **kwargs):
            class R:
                pass
            r = R()
            r.results = [_Bare("https://example.com/x")]
            return r

    monkeypatch.setattr("glass.workers.research._exa", _FakeExa())

    results = await search_for_claim("anything")
    assert len(results) == 1
    assert results[0].publisher == "example.com"
    assert results[0].published_at is None
    assert results[0].excerpt == ""
    assert results[0].title == ""


@pytest.mark.asyncio
async def test_search_for_claim_handles_bad_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Result:
        def __init__(self) -> None:
            self.url = "https://x.com/y"
            self.title = "ok"
            self.text = "ok"
            self.published_date = "definitely not a date"

    class _FakeExa:
        def search_and_contents(self, query: str, **kwargs):
            class R:
                pass
            r = R()
            r.results = [_Result()]
            return r

    monkeypatch.setattr("glass.workers.research._exa", _FakeExa())

    results = await search_for_claim("foo")
    assert results[0].published_at is None  # graceful fallback


@pytest.mark.asyncio
async def test_excerpt_is_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _R:
        def __init__(self) -> None:
            self.url = "https://x.com/a"
            self.title = "t"
            self.text = "x" * 5000
            self.published_date = "2024-01-01"

    class _FakeExa:
        def search_and_contents(self, query, **kwargs):
            class Resp:
                pass
            r = Resp()
            r.results = [_R()]
            return r

    monkeypatch.setattr("glass.workers.research._exa", _FakeExa())

    results = await search_for_claim("q")
    assert len(results[0].excerpt) <= 600
