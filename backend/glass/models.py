import hashlib
import re
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

# Note: ClaimType and ClaimState intentionally share the values "opinion" and
# "heads_up". ClaimType describes what kind of claim was detected; ClaimState
# describes the verification verdict. Opinion-typed claims always end in
# opinion-state (we don't verify opinions). Heads-up-typed entries (anticipatory
# pre-fetched cards) always start in heads-up-state (no claim has been uttered
# yet to verify against). Type+State are still distinct fields, so the only
# coupling is the shared string value.


class ClaimType(StrEnum):
    NUMERIC = "numeric"
    DATE = "date"
    ATTRIBUTION = "attribution"
    EVENT = "event"
    OPINION = "opinion"
    HEADS_UP = "heads_up"


class ClaimState(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    PARTIAL = "partial"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"
    OPINION = "opinion"
    HEADS_UP = "heads_up"


class HostAction(StrEnum):
    DISMISSED = "dismissed"
    SENT_TO_OVERLAY = "sent_to_overlay"
    SAVED = "saved"


class CardSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class CardZone(StrEnum):
    CRITICAL = "critical"
    CALM = "calm"


def zone_for_state(state: "ClaimState") -> "CardZone":
    """Server-side zone classification per Plan C spec §1.

    disputed / partial → critical
    everything else    → calm

    Manual cards always override to critical at insert time (see manual_verify_job).
    """
    if state in (ClaimState.DISPUTED, ClaimState.PARTIAL):
        return CardZone.CRITICAL
    return CardZone.CALM


_NORMALIZE_WS = re.compile(r"\s+")


def hash_claim_text(text: str) -> str:
    """Stable SHA-256 of a claim string.

    Normalizes case and collapses whitespace so semantically identical
    claims hash to the same value. Used as the cache key for the
    anticipatory layer and as the de-dup key for the (session_id,
    claim_hash) unique constraint in the claims table.
    """
    normalized = _NORMALIZE_WS.sub(" ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class TranscriptLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    session_id: UUID
    speaker_id: UUID | None
    speaker: str | None = None  # "You" / "Guest" — see migration 0004
    text: str
    start_ms: int
    end_ms: int
    is_final: bool
    created_at: datetime


class ClaimSource(BaseModel):
    id: UUID
    claim_id: UUID
    url: str
    title: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    excerpt: str | None = None
    rank: int | None = None


class Claim(BaseModel):
    id: UUID
    session_id: UUID
    claim_text: str
    claim_hash: str
    claim_type: ClaimType
    triggered_by: str = "reactive"
    source_line_id: UUID | None = None
    state: ClaimState
    verdict_text: str | None = None
    correction_text: str | None = None
    confidence: int | None = None
    detected_at: datetime
    verified_at: datetime | None = None
    host_action: HostAction | None = None
    host_action_at: datetime | None = None
    pinned: bool = False
    source: CardSource = CardSource.AUTO
    zone: CardZone = CardZone.CALM
    query_echo: str | None = None

    @field_validator("claim_hash")
    @classmethod
    def _check_hash(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("claim_hash must be a 64-char lowercase hex string")
        return v

    @field_validator("claim_text")
    @classmethod
    def _check_claim_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("claim_text cannot be empty")
        return v

    @field_validator("confidence")
    @classmethod
    def _check_confidence(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("confidence must be between 0 and 100")
        return v


class Session(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    state: str
    audio_source: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
