import json
from pathlib import Path

import pytest
from anthropic.types import TextBlock

from glass.workers.claim_detect import (
    detect_claims_in_window,
    parse_detector_output,
)


def test_parse_detector_output_extracts_claims() -> None:
    raw = json.dumps(
        {
            "claims": [
                {
                    "text": "Cerebras raised $1.2 billion last September",
                    "type": "numeric",
                    "speaker": "Speaker 0",
                    "approx_end_ms": 1500,
                }
            ]
        }
    )
    claims = parse_detector_output(raw)
    assert len(claims) == 1
    assert claims[0].text == "Cerebras raised $1.2 billion last September"
    assert claims[0].claim_type == "numeric"
    assert claims[0].speaker == "Speaker 0"
    assert claims[0].approx_end_ms == 1500


def test_parse_detector_output_reads_you_guest_speaker() -> None:
    """The detector attributes each claim to "You" (host) or "Guest" — the
    speaker tag it copies from the window line (migration 0004)."""
    raw = json.dumps(
        {
            "claims": [
                {
                    "text": "We raised $1.1B",
                    "type": "numeric",
                    "speaker": "You",
                    "approx_end_ms": 100,
                },
                {
                    "text": "NVIDIA is worth $3 trillion",
                    "type": "numeric",
                    "speaker": "Guest",
                    "approx_end_ms": 200,
                },
            ]
        }
    )
    claims = parse_detector_output(raw)
    assert [c.speaker for c in claims] == ["You", "Guest"]


def test_parse_detector_output_handles_empty() -> None:
    assert parse_detector_output(json.dumps({"claims": []})) == []


def test_parse_detector_output_handles_garbage() -> None:
    assert parse_detector_output("not json at all") == []


def test_parse_detector_output_strips_markdown_fences() -> None:
    raw = "```json\n" + json.dumps({"claims": []}) + "\n```"
    assert parse_detector_output(raw) == []


def test_parse_detector_output_skips_malformed_items() -> None:
    """If one claim item is missing required fields, skip it; keep the rest."""
    raw = json.dumps(
        {
            "claims": [
                {"text": "good", "type": "numeric", "speaker": "Speaker 0", "approx_end_ms": 100},
                {"missing_text": "bad item"},
                {"text": "also good", "type": "date", "speaker": "Speaker 1", "approx_end_ms": 200},
            ]
        }
    )
    claims = parse_detector_output(raw)
    assert len(claims) == 2
    assert claims[0].text == "good"
    assert claims[1].text == "also good"


@pytest.mark.asyncio
async def test_detect_claims_in_window_uses_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Path(__file__).parent / "fixtures" / "transcript_with_claims.txt"
    lines_text = fixture.read_text()

    captured_calls: dict = {}

    class _FakeMessage:
        def __init__(self) -> None:
            self.content = [
                TextBlock(
                    type="text",
                    text=json.dumps(
                        {
                            "claims": [
                                {
                                    "text": "Cerebras raised $1.2 billion last September",
                                    "type": "numeric",
                                    "speaker": "Speaker 0",
                                    "approx_end_ms": 1500,
                                }
                            ]
                        }
                    ),
                )
            ]

    class _FakeMessages:
        async def create(self, **kwargs):
            captured_calls.update(kwargs)
            return _FakeMessage()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr("glass.workers.claim_detect._client", _FakeClient())

    claims = await detect_claims_in_window(lines_text)
    assert len(claims) == 1
    assert "Cerebras" in claims[0].text

    # Verify prompt caching was requested on the system prompt
    system = captured_calls.get("system")
    assert isinstance(system, list)
    assert system[0].get("cache_control") == {"type": "ephemeral"}
    # Verify Haiku 4.5 model was requested
    assert "haiku" in captured_calls["model"].lower()
