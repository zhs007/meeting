from __future__ import annotations

import asyncio

import pytest

from meeting_openai_translator.openai_events import apply_openai_event, parse_openai_event
from meeting_openai_translator.openai_realtime_translate import (
    ENDPOINT,
    MODEL_NAME,
    OpenAIRealtimeError,
    OpenAIRealtimeSendState,
    build_session_update,
)
from meeting_openai_translator.pcm import pcm16_from_base64, pcm16_to_base64


def test_openai_input_transcript_delta_can_parse() -> None:
    event = parse_openai_event({"type": "session.input_transcript.delta", "delta": "你好"})

    assert event.type == "input_transcript"
    assert event.text == "你好"


def test_openai_output_transcript_delta_can_parse() -> None:
    event = parse_openai_event({"type": "session.output_transcript.delta", "delta": "hello"})

    assert event.type == "output_transcript"
    assert event.text == "hello"


def test_openai_output_audio_delta_can_write_to_output_queue() -> None:
    raw_audio = b"\x01\x02\x03\x04"
    event = parse_openai_event(
        {"type": "session.output_audio.delta", "delta": pcm16_to_base64(raw_audio)}
    )
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    asyncio.run(apply_openai_event(event, output_audio_queue=queue))

    assert queue.get_nowait() == raw_audio


def test_openai_session_closed_triggers_closed_state() -> None:
    event = parse_openai_event({"type": "session.closed"})
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    closed = asyncio.run(apply_openai_event(event, output_audio_queue=queue))

    assert closed is True


def test_openai_unknown_message_shape_is_reported_as_unsupported() -> None:
    event = parse_openai_event({"type": "unknown.event", "value": 1})

    assert event.type == "unsupported"
    assert "unknown.event" in (event.detail or "")


def test_openai_known_control_events_are_quiet() -> None:
    queue: asyncio.Queue[bytes] = asyncio.Queue()
    for event_type in ("session.created", "session.updated"):
        event = parse_openai_event({"type": event_type})

        assert event.type == "control"
        assert asyncio.run(apply_openai_event(event, output_audio_queue=queue)) is False


def test_openai_session_update_uses_translation_endpoint_and_model() -> None:
    assert MODEL_NAME == "gpt-realtime-translate"
    assert "/v1/realtime/translations" in ENDPOINT
    assert "/v1/realtime?" not in ENDPOINT
    assert build_session_update("en") == {
        "type": "session.update",
        "session": {"audio": {"output": {"language": "en"}}},
    }


def test_openai_append_event_uses_base64_pcm_and_session_input_audio_append() -> None:
    state = OpenAIRealtimeSendState()
    chunk = b"\x00\x01" * 2_400
    event = state.append_event(chunk)

    assert event["type"] == "session.input_audio_buffer.append"
    assert pcm16_from_base64(str(event["audio"])) == chunk


def test_openai_session_close_prevents_later_append() -> None:
    state = OpenAIRealtimeSendState()

    assert state.close_event() == {"type": "session.close"}
    with pytest.raises(OpenAIRealtimeError, match="cannot append audio"):
        state.append_event(b"\x00\x01" * 2_400)
