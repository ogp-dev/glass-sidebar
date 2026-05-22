import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

log = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "trajectory.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()
_MODEL = "claude-sonnet-4-6"
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_VALID_KINDS = {"person", "company", "topic", "product"}
_MAX_CANDIDATES = 5

_client: AsyncAnthropic | None = None


def _client_or_init() -> AsyncAnthropic:
    global _client
    if _client is None:
        from glass.config import settings

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass(frozen=True)
class PredictedCandidate:
    name: str
    kind: str
    likelihood: int


def parse_trajectory_output(raw: str) -> list[PredictedCandidate]:
    cleaned = _MD_FENCE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    items = (data.get("candidates") or [])[:_MAX_CANDIDATES]
    out: list[PredictedCandidate] = []
    for item in items:
        try:
            kind = item["kind"]
            if kind not in _VALID_KINDS:
                continue
            lk = max(1, min(10, int(item.get("likelihood", 5))))
            out.append(
                PredictedCandidate(
                    name=str(item["name"]).strip(), kind=kind, likelihood=lk
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return out


async def predict_trajectory(window_text: str) -> list[PredictedCandidate]:
    """Predict next 30-90s topics/entities given the last 2 min of transcript."""
    if not window_text.strip():
        return []
    client = _client_or_init()
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
        messages=[{"role": "user", "content": f"Recent transcript:\n\n{window_text}"}],
    )
    text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
    return parse_trajectory_output(text)
