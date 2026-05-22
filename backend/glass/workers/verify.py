import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from glass.workers.research import SearchResult

log = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "verify.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_MODEL = "claude-sonnet-4-6"
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_VALID_STATES = {"verified", "partial", "disputed", "unverified", "opinion"}

_client: AsyncAnthropic | None = None


def _client_or_init() -> AsyncAnthropic:
    global _client
    if _client is None:
        from glass.config import settings

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass(frozen=True)
class VerificationResult:
    state: str
    verdict: str
    correction: str | None
    confidence: int


def parse_verify_output(raw: str) -> VerificationResult:
    cleaned = _MD_FENCE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return VerificationResult(
            state="unverified", verdict="", correction=None, confidence=0
        )
    state = data.get("state")
    try:
        confidence = int(data.get("confidence") or 0)
    except (ValueError, TypeError):
        confidence = 0
    if state not in _VALID_STATES:
        state = "unverified"
    if confidence < 50:
        state = "unverified"
    return VerificationResult(
        state=state,
        verdict=str(data.get("verdict") or ""),
        correction=data.get("correction"),
        confidence=confidence,
    )


def _format_sources(sources: list[SearchResult]) -> str:
    blocks = []
    for i, s in enumerate(sources, 1):
        blocks.append(
            f"[Source {i}] {s.publisher} — {s.title}\n"
            f"  url: {s.url}\n"
            f"  published: {s.published_at or 'unknown'}\n"
            f"  excerpt: {s.excerpt[:500]}"
        )
    return "\n\n".join(blocks)


async def verify_claim(
    claim_text: str, sources: list[SearchResult]
) -> VerificationResult:
    if not sources:
        return VerificationResult(
            state="unverified",
            verdict="No sources found.",
            correction=None,
            confidence=0,
        )
    client = _client_or_init()
    user_msg = f"Claim: {claim_text}\n\nSources:\n\n{_format_sources(sources)}"
    msg = await client.messages.create(
        model=_MODEL,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(
        block.text for block in msg.content if isinstance(block, TextBlock)
    )
    return parse_verify_output(text)
