from glass.stt.deepgram_client import TranscriptResult, parse_deepgram_message


def test_parse_partial_message() -> None:
    raw = {
        "type": "Results",
        "channel": {
            "alternatives": [
                {"transcript": "hello", "confidence": 0.95, "words": []}
            ]
        },
        "is_final": False,
        "start": 0.0,
        "duration": 1.2,
        "channel_index": [0, 2],
    }
    result = parse_deepgram_message(raw)
    assert result == TranscriptResult(
        text="hello",
        start_ms=0,
        end_ms=1200,
        is_final=False,
        speaker_label="Speaker 0",
    )


def test_parse_final_message_with_diarization() -> None:
    raw = {
        "type": "Results",
        "channel": {
            "alternatives": [
                {
                    "transcript": "yes that's right",
                    "confidence": 0.99,
                    "words": [
                        {"word": "yes", "start": 5.0, "end": 5.4, "speaker": 1},
                        {"word": "that's", "start": 5.4, "end": 5.8, "speaker": 1},
                        {"word": "right", "start": 5.8, "end": 6.2, "speaker": 1},
                    ],
                }
            ]
        },
        "is_final": True,
        "start": 5.0,
        "duration": 1.2,
    }
    result = parse_deepgram_message(raw)
    assert result == TranscriptResult(
        text="yes that's right",
        start_ms=5000,
        end_ms=6200,
        is_final=True,
        speaker_label="Speaker 1",
    )


def test_parse_majority_vote_speaker() -> None:
    raw = {
        "type": "Results",
        "channel": {
            "alternatives": [
                {
                    "transcript": "mixed speakers",
                    "confidence": 0.9,
                    "words": [
                        {"word": "mixed", "start": 0, "end": 1, "speaker": 0},
                        {"word": "speakers", "start": 1, "end": 2, "speaker": 1},
                        {"word": "again", "start": 2, "end": 3, "speaker": 1},
                    ],
                }
            ]
        },
        "is_final": True,
        "start": 0.0,
        "duration": 3.0,
    }
    result = parse_deepgram_message(raw)
    assert result is not None
    assert result.speaker_label == "Speaker 1"  # majority


def test_parse_non_results_returns_none() -> None:
    raw = {"type": "Metadata", "request_id": "abc"}
    assert parse_deepgram_message(raw) is None


def test_parse_empty_transcript_returns_none() -> None:
    raw = {
        "type": "Results",
        "channel": {"alternatives": [{"transcript": "", "confidence": 0.0, "words": []}]},
        "is_final": True,
        "start": 0,
        "duration": 0,
    }
    assert parse_deepgram_message(raw) is None


def test_parse_whitespace_only_transcript_returns_none() -> None:
    raw = {
        "type": "Results",
        "channel": {"alternatives": [{"transcript": "   \n  ", "confidence": 0.0}]},
        "is_final": True,
        "start": 0,
        "duration": 0,
    }
    assert parse_deepgram_message(raw) is None


def test_parse_missing_words_defaults_to_speaker_0() -> None:
    raw = {
        "type": "Results",
        "channel": {"alternatives": [{"transcript": "no words array"}]},
        "is_final": True,
        "start": 1.0,
        "duration": 0.5,
    }
    result = parse_deepgram_message(raw)
    assert result is not None
    assert result.speaker_label == "Speaker 0"


def test_build_url_no_keywords() -> None:
    from glass.stt.deepgram_client import _build_url

    url = _build_url(None)
    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in url
    assert "numerals=true" in url
    assert "utterance_end_ms=1500" in url
    assert "endpointing=400" in url
    assert "keyterm=" not in url


def test_build_url_with_keywords() -> None:
    from glass.stt.deepgram_client import _build_url

    url = _build_url(["Cerebras", "Andrew Feldman", "WSE-3"])
    assert "keyterm=Cerebras" in url
    # Spaces URL-encoded
    assert "keyterm=Andrew%20Feldman" in url
    # WSE-3 has a hyphen — quote() shouldn't escape ASCII alnum + - . _ ~
    assert "keyterm=WSE-3" in url


def test_build_url_skips_empty_keywords() -> None:
    from glass.stt.deepgram_client import _build_url

    url = _build_url(["Cerebras", "", "  ", "NVIDIA"])
    assert "keyterm=Cerebras" in url
    assert "keyterm=NVIDIA" in url
    # Should only have 2 keyword params, not 4
    assert url.count("keyterm=") == 2
