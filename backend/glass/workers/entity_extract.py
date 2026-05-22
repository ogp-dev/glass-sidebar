import json
import re
from dataclasses import dataclass
from pathlib import Path

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

log = structlog.get_logger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "entity_extract.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()
_MODEL = "claude-haiku-4-5-20251001"
_MD_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_VALID_KINDS = {"person", "company", "topic", "product"}

_client: AsyncAnthropic | None = None


def _client_or_init() -> AsyncAnthropic:
    global _client
    if _client is None:
        from glass.config import settings

        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


@dataclass(frozen=True)
class ExtractedEntity:
    name: str
    kind: str
    salience: int


def parse_extractor_output(raw: str) -> list[ExtractedEntity]:
    cleaned = _MD_FENCE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    items = data.get("entities") or []
    out: list[ExtractedEntity] = []
    for item in items:
        try:
            kind = item["kind"]
            if kind not in _VALID_KINDS:
                log.warning("entity_extract.bad_kind", kind=kind)
                continue
            sal = int(item.get("salience", 5))
            sal = max(1, min(10, sal))
            out.append(
                ExtractedEntity(name=str(item["name"]).strip(), kind=kind, salience=sal)
            )
        except (KeyError, ValueError, TypeError):
            log.warning("entity_extract.bad_item", item=item)
            continue
    return out


async def extract_entities_from_docket(docket: str) -> list[ExtractedEntity]:
    """Send docket to Claude Haiku, return list of (name, kind, salience)."""
    if not docket.strip():
        return []
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
        messages=[{"role": "user", "content": f"Docket:\n\n{docket}"}],
    )
    text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
    return parse_extractor_output(text)
