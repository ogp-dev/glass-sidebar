import json

import pytest

from glass.workers.trajectory import (
    parse_trajectory_output,
    predict_trajectory,
)


def test_parse_trajectory_output_basic() -> None:
    raw = json.dumps(
        {
            "candidates": [
                {"name": "Cerebras IPO", "kind": "topic", "likelihood": 9},
                {"name": "Sam Altman", "kind": "person", "likelihood": 7},
            ]
        }
    )
    cands = parse_trajectory_output(raw)
    assert len(cands) == 2
    assert cands[0].name == "Cerebras IPO"
    assert cands[0].kind == "topic"
    assert cands[0].likelihood == 9


def test_parse_trajectory_empty() -> None:
    assert parse_trajectory_output(json.dumps({"candidates": []})) == []


def test_parse_trajectory_garbage() -> None:
    assert parse_trajectory_output("not json") == []


def test_parse_trajectory_md_fences() -> None:
    raw = "```json\n" + json.dumps({"candidates": []}) + "\n```"
    assert parse_trajectory_output(raw) == []


def test_parse_trajectory_invalid_kind_skipped() -> None:
    raw = json.dumps(
        {"candidates": [{"name": "X", "kind": "alien", "likelihood": 5}]}
    )
    assert parse_trajectory_output(raw) == []


def test_parse_trajectory_clamps_likelihood() -> None:
    raw = json.dumps(
        {
            "candidates": [
                {"name": "A", "kind": "topic", "likelihood": 99},
                {"name": "B", "kind": "topic", "likelihood": -3},
            ]
        }
    )
    out = parse_trajectory_output(raw)
    assert out[0].likelihood == 10
    assert out[1].likelihood == 1


def test_parse_trajectory_caps_at_5() -> None:
    """Hard-cap at 5 even if the LLM ignores the limit."""
    raw = json.dumps(
        {
            "candidates": [
                {"name": f"X{i}", "kind": "topic", "likelihood": 5} for i in range(8)
            ]
        }
    )
    assert len(parse_trajectory_output(raw)) == 5


@pytest.mark.asyncio
async def test_predict_trajectory_calls_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic.types

    captured: dict = {}

    class _FakeMsg:
        content = [
            anthropic.types.TextBlock(
                text=json.dumps(
                    {
                        "candidates": [
                            {"name": "Cerebras IPO", "kind": "topic", "likelihood": 9}
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

    monkeypatch.setattr("glass.workers.trajectory._client", _FakeClient())

    cands = await predict_trajectory(
        "[Speaker 0 @ 50000] So tell me about that Cerebras round.\n"
        "[Speaker 1 @ 53000] Yeah, the WSE-3 is really impressive."
    )
    assert len(cands) == 1
    assert cands[0].name == "Cerebras IPO"
    assert "sonnet" in captured["model"].lower()
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_predict_trajectory_empty_transcript_returns_empty() -> None:
    cands = await predict_trajectory("")
    assert cands == []
