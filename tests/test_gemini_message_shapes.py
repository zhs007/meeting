from __future__ import annotations

import asyncio

from meeting_translator.gemini_live_translate import (
    MODEL_NAME,
    apply_events,
    build_live_config,
    extract_gemini_events,
    go_away_time_left,
    live_translation_config_dict,
)
from meeting_translator.pcm import pcm16_to_base64


def test_fake_input_transcript_event_can_parse() -> None:
    events = extract_gemini_events(
        {"serverContent": {"inputTranscription": {"text": "你好"}}}
    )

    assert events[0].type == "input_transcript"
    assert events[0].text == "你好"


def test_fake_output_transcript_event_can_parse() -> None:
    events = extract_gemini_events(
        {"serverContent": {"outputTranscription": {"text": "hello"}}}
    )

    assert events[0].type == "output_transcript"
    assert events[0].text == "hello"


def test_fake_output_audio_event_can_write_to_output_queue() -> None:
    raw_audio = b"\x01\x02\x03\x04"
    events = extract_gemini_events(
        {
            "serverContent": {
                "modelTurn": {
                    "parts": [
                        {
                            "inlineData": {
                                "data": pcm16_to_base64(raw_audio),
                            }
                        }
                    ]
                }
            }
        }
    )
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    asyncio.run(apply_events(events, output_audio_queue=queue))

    assert queue.get_nowait() == raw_audio


def test_unknown_message_shape_is_reported_as_unsupported() -> None:
    events = extract_gemini_events({"serverContent": {"unexpected": {"value": 1}}})

    assert events[0].type == "unsupported"
    assert "unrecognized" in (events[0].detail or "")


def test_known_top_level_control_message_is_quiet() -> None:
    assert extract_gemini_events({"usageMetadata": {"totalTokenCount": 1}}) == []
    assert extract_gemini_events({"setupComplete": {}}) == []


def test_known_server_content_control_message_is_quiet() -> None:
    assert extract_gemini_events({"serverContent": {"turnComplete": True}}) == []
    assert extract_gemini_events({"serverContent": {"generationComplete": True}}) == []
    assert extract_gemini_events({"serverContent": {"inputTranscription": {"finished": True}}}) == []
    assert extract_gemini_events({"serverContent": {"outputTranscription": {"finished": True}}}) == []


def test_go_away_time_left_can_parse() -> None:
    assert go_away_time_left({"goAway": {"timeLeft": "10s"}}) == "10s"
    assert go_away_time_left({"usageMetadata": {"totalTokenCount": 1}}) is None


def test_live_translation_config_carries_official_wire_shape() -> None:
    config = build_live_config("en", echo_target_language=False)
    translation_config = live_translation_config_dict(config)

    assert MODEL_NAME == "gemini-3.5-live-translate-preview"
    assert translation_config == {
        "targetLanguageCode": "en",
        "echoTargetLanguage": False,
    }
