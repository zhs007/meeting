from __future__ import annotations

import asyncio

from meeting_translator.gemini_live_translate import (
    GeminiEvent,
    GeminiRuntimeStats,
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
    assert extract_gemini_events({"sessionResumptionUpdate": {"newHandle": "abc"}}) == []
    assert extract_gemini_events({"voiceActivity": {"activity": "START"}}) == []
    assert extract_gemini_events({"voiceActivityDetectionSignal": {"signal": "END"}}) == []


def test_known_server_content_control_message_is_quiet() -> None:
    assert extract_gemini_events({"serverContent": {"turnComplete": True}}) == []
    assert extract_gemini_events({"serverContent": {"generationComplete": True}}) == []
    assert extract_gemini_events({"serverContent": {"waitingForInput": True}}) == []
    assert extract_gemini_events({"serverContent": {"inputTranscription": {"finished": True}}}) == []
    assert extract_gemini_events({"serverContent": {"outputTranscription": {"finished": True}}}) == []


def test_unknown_event_is_counted_without_default_stdout(capsys) -> None:
    stats = GeminiRuntimeStats()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    asyncio.run(
        apply_events(
            [GeminiEvent(type="unsupported", detail="unrecognized Gemini response shape")],
            output_audio_queue=queue,
            gemini_stats=stats,
        )
    )

    assert "Unsupported Gemini event" not in capsys.readouterr().out
    assert stats.unsupported_event_count == 1
    assert stats.first_unsupported_event == "unrecognized Gemini response shape"


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


def test_live_translation_config_uses_supported_transcription_config_and_voice() -> None:
    config = build_live_config(
        "en",
        source_language="zh-CN",
        voice_name="Kore",
        echo_target_language=False,
    )

    assert config.input_audio_transcription.language_codes is None
    assert "expected source language is zh-CN" in config.system_instruction
    assert "single-speaker meeting" in config.system_instruction
    assert "stable interpreter persona" in config.system_instruction
    assert "do not invent transcript text" in config.system_instruction
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Kore"
    assert config.realtime_input_config.activity_handling == "NO_INTERRUPTION"
    activity_detection = config.realtime_input_config.automatic_activity_detection
    assert activity_detection.end_of_speech_sensitivity == "END_SENSITIVITY_LOW"
    assert activity_detection.silence_duration_ms == 1200
    assert config.realtime_input_config.turn_coverage == "TURN_INCLUDES_ONLY_ACTIVITY"


def test_live_translation_config_can_restore_gemini_default_voice_behavior() -> None:
    config = build_live_config("en", source_language="zh-CN", voice_name=None)

    assert config.input_audio_transcription.language_codes is None
    assert config.speech_config is None


def test_live_translation_config_can_omit_custom_activity_detection() -> None:
    config = build_live_config(
        "en",
        source_language="zh-CN",
        activity_handling=None,
        end_sensitivity=None,
        silence_duration_ms=0,
    )

    assert config.realtime_input_config.activity_handling is None
    assert config.realtime_input_config.automatic_activity_detection is None
