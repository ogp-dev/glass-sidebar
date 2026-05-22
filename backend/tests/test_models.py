import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from glass.models import Claim, ClaimState, ClaimType, hash_claim_text


def test_hash_claim_text_is_deterministic() -> None:
    a = hash_claim_text("Cerebras raised $1.2 billion")
    b = hash_claim_text("Cerebras raised $1.2 billion")
    assert a == b


def test_hash_claim_text_normalizes_whitespace_and_case() -> None:
    a = hash_claim_text("Cerebras raised $1.2 billion")
    b = hash_claim_text("  CEREBRAS   raised  $1.2 billion  ")
    assert a == b


def test_hash_claim_text_distinguishes_different_claims() -> None:
    a = hash_claim_text("Cerebras raised $1.2 billion")
    b = hash_claim_text("Cerebras raised $1.5 billion")
    assert a != b


def test_hash_claim_text_returns_64_char_hex() -> None:
    h = hash_claim_text("anything")
    assert len(h) == 64
    int(h, 16)  # must be valid hex


def test_claim_model_round_trip() -> None:
    sid = UUID("00000000-0000-0000-0000-000000000001")
    c = Claim(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        session_id=sid,
        claim_text="Cerebras raised $1.2B",
        claim_hash=hash_claim_text("Cerebras raised $1.2B"),
        claim_type=ClaimType.NUMERIC,
        state=ClaimState.PENDING,
        detected_at=datetime.datetime(2026, 5, 16, tzinfo=datetime.UTC),
    )
    dumped = c.model_dump()
    assert dumped["claim_type"] == "numeric"
    assert dumped["state"] == "pending"

    rebuilt = Claim.model_validate(dumped)
    assert rebuilt == c


def test_claim_rejects_bad_hash() -> None:
    with pytest.raises(ValidationError, match="64-char lowercase hex"):
        Claim(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            session_id=UUID("00000000-0000-0000-0000-000000000001"),
            claim_text="x",
            claim_hash="not-a-hash",
            claim_type=ClaimType.NUMERIC,
            state=ClaimState.PENDING,
            detected_at=datetime.datetime(2026, 5, 16, tzinfo=datetime.UTC),
        )


def test_claim_rejects_empty_claim_text() -> None:
    with pytest.raises(ValidationError, match="cannot be empty"):
        Claim(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            session_id=UUID("00000000-0000-0000-0000-000000000001"),
            claim_text="   ",
            claim_hash="a" * 64,
            claim_type=ClaimType.NUMERIC,
            state=ClaimState.PENDING,
            detected_at=datetime.datetime(2026, 5, 16, tzinfo=datetime.UTC),
        )


def test_claim_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError, match="between 0 and 100"):
        Claim(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            session_id=UUID("00000000-0000-0000-0000-000000000001"),
            claim_text="x",
            claim_hash="a" * 64,
            claim_type=ClaimType.NUMERIC,
            state=ClaimState.PENDING,
            confidence=150,
            detected_at=datetime.datetime(2026, 5, 16, tzinfo=datetime.UTC),
        )


def test_claim_accepts_valid_confidence() -> None:
    c = Claim(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        claim_text="x",
        claim_hash="a" * 64,
        claim_type=ClaimType.NUMERIC,
        state=ClaimState.PENDING,
        confidence=75,
        detected_at=datetime.datetime(2026, 5, 16, tzinfo=datetime.UTC),
    )
    assert c.confidence == 75


def test_claim_defaults_for_new_fields():
    from datetime import datetime, timezone
    from uuid import uuid4

    from glass.models import CardSource, CardZone, Claim, ClaimState, ClaimType
    from glass.models import hash_claim_text

    c = Claim(
        id=uuid4(),
        session_id=uuid4(),
        claim_text="x",
        claim_hash=hash_claim_text("x"),
        claim_type=ClaimType.NUMERIC,
        state=ClaimState.PENDING,
        detected_at=datetime.now(timezone.utc),
    )
    assert c.pinned is False
    assert c.source is CardSource.AUTO
    assert c.zone is CardZone.CALM
    assert c.query_echo is None
