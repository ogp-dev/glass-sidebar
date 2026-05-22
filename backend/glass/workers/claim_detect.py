import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

log = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "claim_detect.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

_MODEL = "claude-haiku-4-5-20251001"


def _make_client() -> AsyncAnthropic:
    from glass.config import settings

    return AsyncAnthropic(api_key=settings.anthropic_api_key)


# Lazy client: module-level _client = None until first use. This dodges the
# env-var-at-import-time issue (matches the pattern in db.py / auth.py).
_client: AsyncAnthropic | None = None


def _client_or_init() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class DetectedClaim:
    text: str
    claim_type: str
    speaker: str
    approx_end_ms: int


def parse_detector_output(raw: str) -> list[DetectedClaim]:
    """Parse Claude's JSON response. Tolerant of garbage and md fences."""
    cleaned = _MD_FENCE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("claim_detect.bad_json", body=cleaned[:300])
        return []
    items = data.get("claims") or []
    out: list[DetectedClaim] = []
    for item in items:
        try:
            out.append(
                DetectedClaim(
                    text=item["text"],
                    claim_type=item["type"],
                    speaker=item.get("speaker", "Speaker 0"),
                    approx_end_ms=int(item.get("approx_end_ms", 0)),
                )
            )
        except (KeyError, ValueError, TypeError):
            log.warning("claim_detect.bad_item", item=item)
            continue
    return out


async def detect_claims_in_window(window_text: str) -> list[DetectedClaim]:
    """Send the transcript window to Claude Haiku, return parsed claims.

    Uses prompt caching (ephemeral) on the system prompt so the rolling
    detection cost is dominated by output, not by re-reading the rubric.
    """
    client = _client_or_init()
    msg = await client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": f"Transcript window:\n\n{window_text}"}],
    )
    text = "".join(
        block.text for block in msg.content if isinstance(block, TextBlock)
    )
    return parse_detector_output(text)
