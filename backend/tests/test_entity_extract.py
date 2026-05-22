import json

import pytest

from glass.workers.entity_extract import (
    ExtractedEntity,
    extract_entities_from_docket,
    parse_extractor_output,
)


def test_parse_extractor_output_basic() -> None:
    raw = json.dumps(
        {
            "entities": [
                {"name": "Cerebras Systems", "kind": "company", "salience": 9},
                {"name": "Jason Calacanis", "kind": "person", "salience": 8},
            ]
        }
    )
    entities: list[ExtractedEntity] = parse_extractor_output(raw)
    assert len(entities) == 2
    assert entities[0].name == "Cerebras Systems"
    assert entities[0].kind == "company"
    assert entities[0].salience == 9


def test_parse_extractor_output_empty() -> None:
    assert parse_extractor_output(json.dumps({"entities": []})) == []


def test_parse_extractor_output_garbage_returns_empty() -> None:
    assert parse_extractor_output("not json") == []


def test_parse_extractor_output_strips_md_fences() -> None:
    raw = "```json\n" + json.dumps({"entities": []}) + "\n```"
    assert parse_extractor_output(raw) == []


def test_parse_extractor_output_rejects_invalid_kind() -> None:
    raw = json.dumps(
        {"entities": [{"name": "X", "kind": "alien", "salience": 5}]}
    )
    assert parse_extractor_output(raw) == []


def test_parse_extractor_output_clamps_salience() -> None:
    raw = json.dumps(
        {
            "entities": [
                {"name": "A", "kind": "person", "salience": 99},
                {"name": "B", "kind": "person", "salience": -3},
            ]
        }
    )
    out = parse_extractor_output(raw)
    assert out[0].salience == 10
    assert out[1].salience == 1


@pytest.mark.asyncio
async def test_extract_entities_calls_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic.types

    captured: dict = {}

    class _FakeMsg:
        content = [
            anthropic.types.TextBlock(
                text=json.dumps(
                    {
                        "entities": [
                            {"name": "Cerebras Systems", "kind": "company", "salience": 9}
                        ]
                    }
                ),
                type="text",
                citations=None,
            )
        ]

    class _FakeMessages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeMsg()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr("glass.workers.entity_extract._client", _FakeClient())

    entities = await extract_entities_from_docket(
        "TWiST E2289: Cerebras IPO, talking with Jason. Section on the WSE-3 chip."
    )
    assert len(entities) == 1
    assert entities[0].name == "Cerebras Systems"
    assert "haiku" in captured["model"].lower()
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
