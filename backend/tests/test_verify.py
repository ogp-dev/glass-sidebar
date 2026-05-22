import json

import pytest

from glass.workers.research import SearchResult
from glass.workers.verify import (
    VerificationResult,
    parse_verify_output,
    verify_claim,
)


def test_parse_verify_output_verified() -> None:
    raw = json.dumps(
        {
            "state": "verified",
            "verdict": "Claim matches.",
            "correction": None,
            "confidence": 90,
        }
    )
    result = parse_verify_output(raw)
    assert result == VerificationResult(
        state="verified", verdict="Claim matches.", correction=None, confidence=90
    )


def test_parse_verify_output_partial() -> None:
    raw = json.dumps(
        {
            "state": "partial",
            "verdict": "Close — wrong amount.",
            "correction": "Actually $1.1B (Sept 2024)",
            "confidence": 88,
        }
    )
    result = parse_verify_output(raw)
    assert result.state == "partial"
    assert result.correction == "Actually $1.1B (Sept 2024)"


def test_parse_verify_output_low_confidence_becomes_unverified() -> None:
    raw = json.dumps(
        {
            "state": "verified",
            "verdict": "Maybe.",
            "correction": None,
            "confidence": 30,
        }
    )
    result = parse_verify_output(raw)
    assert result.state == "unverified"
    assert result.confidence == 30


def test_parse_verify_output_invalid_state_becomes_unverified() -> None:
    raw = json.dumps(
        {
            "state": "obliterated",
            "verdict": "What?",
            "correction": None,
            "confidence": 80,
        }
    )
    result = parse_verify_output(raw)
    assert result.state == "unverified"


def test_parse_verify_output_garbage_returns_unverified() -> None:
    result = parse_verify_output("not json")
    assert result.state == "unverified"
    assert result.confidence == 0


def test_parse_verify_output_strips_md_fences() -> None:
    raw = "```json\n" + json.dumps(
        {"state": "verified", "verdict": "ok", "correction": None, "confidence": 80}
    ) + "\n```"
    result = parse_verify_output(raw)
    assert result.state == "verified"


@pytest.mark.asyncio
async def test_verify_claim_calls_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anthropic.types

    captured: dict = {}

    class _FakeMsg:
        content = [
            anthropic.types.TextBlock(
                text=json.dumps(
                    {
                        "state": "partial",
                        "verdict": "Wrong amount.",
                        "correction": "Actually $1.1B",
                        "confidence": 92,
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

    monkeypatch.setattr("glass.workers.verify._client", _FakeClient())

    result = await verify_claim(
        "Cerebras raised $1.2 billion",
        [
            SearchResult(
                url="https://bloomberg.com/x",
                title="Cerebras raises $1.1B Series F",
                publisher="bloomberg.com",
                published_at=None,
                excerpt="Cerebras closed a $1.1B round",
            )
        ],
    )
    assert result.state == "partial"
    assert result.correction == "Actually $1.1B"
    assert "sonnet" in captured["model"].lower()


@pytest.mark.asyncio
async def test_verify_claim_no_sources_returns_unverified() -> None:
    result = await verify_claim("any claim", [])
    assert result.state == "unverified"
    assert result.confidence == 0
    assert "no sources" in result.verdict.lower()


def test_zone_for_state():
    from glass.models import CardZone, ClaimState, zone_for_state

    assert zone_for_state(ClaimState.DISPUTED) is CardZone.CRITICAL
    assert zone_for_state(ClaimState.PARTIAL) is CardZone.CRITICAL
    assert zone_for_state(ClaimState.VERIFIED) is CardZone.CALM
    assert zone_for_state(ClaimState.HEADS_UP) is CardZone.CALM
    assert zone_for_state(ClaimState.OPINION) is CardZone.CALM
    assert zone_for_state(ClaimState.UNVERIFIED) is CardZone.CALM
    assert zone_for_state(ClaimState.PENDING) is CardZone.CALM
