import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

log = structlog.get_logger(__name__)

_BASE_URL = "wss://api.deepgram.com/v1/listen"
_BASE_PARAMS = (
    "model=nova-3"
    "&encoding=linear16"  # v1: Mac helper sends raw PCM. Switch to opus when encoder ships.
    "&sample_rate=48000"
    "&channels=1"
    "&interim_results=true"
    "&punctuate=true"
    "&diarize=true"
    "&smart_format=true"
    "&numerals=true"          # $1.2 billion as "$1.2 billion" not "one point two billion"
    "&utterance_end_ms=1500"  # let utterances run longer before finalizing
    "&endpointing=400"        # wait 400ms of silence before declaring end of utterance
)


def _build_url(keywords: list[str] | None = None) -> str:
    """Construct the Deepgram streaming URL.

    keywords: entity names to boost (preferred over phonetically similar words).
    Nova-3 uses the `keyterm` query param (multi-word phrases supported),
    NOT the legacy `keywords` param which Nova-3 explicitly rejects. The
    weight syntax differs too — keyterm has no `:weight` suffix, all
    keyterms get the same boost.
    """
    parts = [_BASE_PARAMS]
    if keywords:
        for k in keywords:
            k_norm = k.strip()
            if not k_norm:
                continue
            parts.append(f"keyterm={quote(k_norm)}")
    return f"{_BASE_URL}?{'&'.join(parts)}"


@dataclass(frozen=True)
class TranscriptResult:
    text: str
    start_ms: int
    end_ms: int
    is_final: bool
    speaker_label: str


def parse_deepgram_message(raw: dict[str, Any]) -> TranscriptResult | None:
    """Convert one Deepgram Results frame into our internal type.

    Returns None for non-Results frames (Metadata, etc.) and for empty
    transcripts. Picks the majority-vote speaker across words when
    diarization is enabled.
    """
    if raw.get("type") != "Results":
        return None
    alt = raw.get("channel", {}).get("alternatives", [{}])[0]
    text = alt.get("transcript", "").strip()
    if not text:
        return None
    start = float(raw.get("start", 0.0))
    duration = float(raw.get("duration", 0.0))

    speaker_int = 0
    words = alt.get("words") or []
    if words:
        speakers = [w.get("speaker", 0) for w in words]
        speaker_int = max(set(speakers), key=speakers.count)

    return TranscriptResult(
        text=text,
        start_ms=int(start * 1000),
        end_ms=int((start + duration) * 1000),
        is_final=bool(raw.get("is_final", False)),
        speaker_label=f"Speaker {speaker_int}",
    )


class DeepgramStream:
    """One streaming session against Deepgram.

    Send PCM frames via send_audio(); iterate results via results().
    Caller must call open() before either, and close() to clean up.

    keywords: optional list of entity names to boost in recognition.
    """

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._ws: ClientConnection | None = None
        self._closed = asyncio.Event()
        self._keywords = keywords or []

    async def open(self) -> None:
        from glass.config import settings

        url = _build_url(self._keywords)
        headers = {"Authorization": f"Token {settings.deepgram_api_key}"}
        self._ws = await websockets.connect(url, additional_headers=headers)
        log.info("deepgram.connected", keyword_count=len(self._keywords))

    async def send_audio(self, frame: bytes) -> None:
        if self._ws is None:
            raise RuntimeError("DeepgramStream.open() must be called first")
        await self._ws.send(frame)

    async def keep_alive(self) -> None:
        """Hold an idle stream open.

        Deepgram closes a streaming connection after ~10s without audio. The
        guest stream legitimately idles (guest silent, nothing playing through
        the speakers), so a periodic KeepAlive keeps it ready to transcribe
        the moment audio resumes — without it the stream would close and the
        whole session would tear down.
        """
        if self._ws is None:
            return
        await self._ws.send(json.dumps({"type": "KeepAlive"}))

    async def results(self) -> AsyncIterator[TranscriptResult]:
        if self._ws is None:
            raise RuntimeError("DeepgramStream.open() must be called first")
        raw_count = 0
        results_count = 0
        empty_count = 0
        try:
            async for msg in self._ws:
                if isinstance(msg, bytes):
                    continue
                try:
                    raw = json.loads(msg)
                except json.JSONDecodeError:
                    log.warning("deepgram.bad_json", body=msg[:200])
                    continue
                raw_count += 1
                mtype = raw.get("type")
                if mtype == "Results":
                    _alt = raw.get("channel", {}).get("alternatives", [{}])[0]
                    if not _alt.get("transcript", "").strip():
                        empty_count += 1
                if raw_count <= 5 or raw_count % 50 == 0:
                    log.info(
                        "deepgram.raw",
                        count=raw_count,
                        type=mtype,
                        empty_results=empty_count,
                    )
                parsed = parse_deepgram_message(raw)
                if parsed is not None:
                    results_count += 1
                    log.info(
                        "deepgram.transcript",
                        is_final=parsed.is_final,
                        text=parsed.text[:80],
                    )
                    yield parsed
        finally:
            log.info(
                "deepgram.stream_end",
                raw_count=raw_count,
                results_count=results_count,
                empty_count=empty_count,
            )
            self._closed.set()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
