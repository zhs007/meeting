from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from meeting_openai_translator.pcm import PCMError, pcm16_from_base64
from meeting_openai_translator.transcript_log import TranscriptLogger


EventType = Literal[
    "input_transcript",
    "output_transcript",
    "audio",
    "closed",
    "control",
    "unsupported",
]


class OpenAIEventError(RuntimeError):
    """Raised when an OpenAI Realtime event cannot be handled safely."""


@dataclass(frozen=True)
class OpenAIEvent:
    type: EventType
    text: str | None = None
    audio: bytes | None = None
    detail: str | None = None


def _text_delta(message: dict[str, Any]) -> str | None:
    for key in ("delta", "text", "transcript"):
        value = message.get(key)
        if value is not None:
            return str(value)
    return None


def _audio_delta(message: dict[str, Any]) -> bytes:
    payload = message.get("delta") or message.get("audio")
    if not isinstance(payload, str):
        raise OpenAIEventError("session.output_audio.delta is missing a base64 delta string.")
    try:
        return pcm16_from_base64(payload)
    except PCMError as exc:
        raise OpenAIEventError(str(exc)) from exc


def parse_openai_event(message: dict[str, Any]) -> OpenAIEvent:
    event_type = message.get("type")
    if event_type == "session.input_transcript.delta":
        return OpenAIEvent(type="input_transcript", text=_text_delta(message))
    if event_type == "session.output_transcript.delta":
        return OpenAIEvent(type="output_transcript", text=_text_delta(message))
    if event_type == "session.output_audio.delta":
        return OpenAIEvent(type="audio", audio=_audio_delta(message))
    if event_type == "session.closed":
        return OpenAIEvent(type="closed")
    if event_type in {
        "session.created",
        "session.updated",
        "session.input_audio_buffer.committed",
        "session.input_audio_buffer.cleared",
    }:
        return OpenAIEvent(type="control", detail=f"control event: {event_type}")
    return OpenAIEvent(type="unsupported", detail=f"unsupported event: {event_type!r}")


async def apply_openai_event(
    event: OpenAIEvent,
    *,
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger | None = None,
) -> bool:
    if event.type == "input_transcript" and event.text:
        print(f"Input transcript: {event.text}")
        if transcript_log:
            transcript_log.input_transcript(event.text)
    elif event.type == "output_transcript" and event.text:
        print(f"Output transcript: {event.text}")
        if transcript_log:
            transcript_log.output_transcript(event.text)
    elif event.type == "audio" and event.audio is not None:
        await output_audio_queue.put(event.audio)
        if transcript_log:
            transcript_log.output_audio(len(event.audio))
    elif event.type == "closed":
        return True
    elif event.type == "control":
        return False
    elif event.type == "unsupported":
        detail = event.detail or "unknown event"
        print(f"Unsupported OpenAI event: {detail}")
    return False
