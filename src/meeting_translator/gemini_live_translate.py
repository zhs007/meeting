from __future__ import annotations

import asyncio
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from meeting_translator.pcm import INPUT_MIME_TYPE, PCMError, pcm16_from_base64, validate_input_chunk
from meeting_translator.transcript_log import TranscriptLogger


MODEL_NAME = "gemini-3.5-live-translate-preview"

EventType = Literal["input_transcript", "output_transcript", "audio", "unsupported"]


class GeminiLiveError(RuntimeError):
    """Raised when Gemini Live Translation cannot be configured or streamed safely."""


@dataclass(frozen=True)
class GeminiEvent:
    type: EventType
    text: str | None = None
    audio: bytes | None = None
    detail: str | None = None


def _field(value: Any, snake_name: str, camel_name: str | None = None) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        if snake_name in value:
            return value[snake_name]
        if camel_name and camel_name in value:
            return value[camel_name]
        return None
    if hasattr(value, snake_name):
        return getattr(value, snake_name)
    if camel_name and hasattr(value, camel_name):
        return getattr(value, camel_name)
    return None


def _has_non_empty_field(value: Any, snake_name: str, camel_name: str | None = None) -> bool:
    field_value = _field(value, snake_name, camel_name)
    if field_value is None:
        return False
    if isinstance(field_value, bool):
        return field_value
    return True


def _text(value: Any) -> str | None:
    text = _field(value, "text")
    if text is None:
        return None
    return str(text)


def _has_transcription_marker(value: Any) -> bool:
    return value is not None and (_field(value, "finished") is not None or _text(value) is not None)


def _decode_audio(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return pcm16_from_base64(data)
    raise GeminiLiveError(f"unsupported inline audio payload type: {type(data).__name__}")


def build_live_config(target_language: str, *, echo_target_language: bool = False) -> Any:
    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiLiveError("google-genai is required; install requirements.txt first.") from exc

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )
    # google-genai 1.75.0 does not expose TranslationConfig yet, while the
    # Live Translation API already expects this official wire field.
    config.generation_config = {
        "translationConfig": {
            "targetLanguageCode": target_language,
            "echoTargetLanguage": echo_target_language,
        }
    }
    return config


def live_translation_config_dict(config: Any) -> dict[str, Any]:
    generation_config = _field(config, "generation_config", "generationConfig")
    if not isinstance(generation_config, dict):
        raise GeminiLiveError("Live config generation_config must carry translationConfig.")
    translation_config = generation_config.get("translationConfig")
    if not isinstance(translation_config, dict):
        raise GeminiLiveError("Live config is missing generationConfig.translationConfig.")
    return translation_config


def _is_known_top_level_control_message(response: Any) -> bool:
    return any(
        _has_non_empty_field(response, snake_name, camel_name)
        for snake_name, camel_name in (
            ("setup_complete", "setupComplete"),
            ("usage_metadata", "usageMetadata"),
            ("go_away", "goAway"),
            ("session_resumption_update", "sessionResumptionUpdate"),
            ("voice_activity_detection_signal", "voiceActivityDetectionSignal"),
            ("voice_activity", "voiceActivity"),
        )
    )


def _is_known_server_content_control_message(server_content: Any) -> bool:
    input_transcription = _field(server_content, "input_transcription", "inputTranscription")
    output_transcription = _field(server_content, "output_transcription", "outputTranscription")
    if _has_transcription_marker(input_transcription) or _has_transcription_marker(
        output_transcription
    ):
        return True

    return any(
        _has_non_empty_field(server_content, snake_name, camel_name)
        for snake_name, camel_name in (
            ("turn_complete", "turnComplete"),
            ("generation_complete", "generationComplete"),
            ("interrupted", "interrupted"),
            ("waiting_for_input", "waitingForInput"),
            ("grounding_metadata", "groundingMetadata"),
            ("url_context_metadata", "urlContextMetadata"),
            ("turn_complete_reason", "turnCompleteReason"),
        )
    )


def go_away_time_left(response: Any) -> str | None:
    go_away = _field(response, "go_away", "goAway")
    if go_away is None:
        return None
    time_left = _field(go_away, "time_left", "timeLeft")
    return str(time_left) if time_left is not None else "unknown"


@contextmanager
def _suppress_google_genai_translation_config_warning() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Pydantic serializer warnings:",
            category=UserWarning,
            module=r"pydantic\.main",
        )
        yield


def extract_gemini_events(response: Any) -> list[GeminiEvent]:
    server_content = _field(response, "server_content", "serverContent")
    if server_content is None:
        if _is_known_top_level_control_message(response):
            return []
        return [GeminiEvent(type="unsupported", detail="response has no server_content")]

    events: list[GeminiEvent] = []
    input_transcription = _field(server_content, "input_transcription", "inputTranscription")
    input_text = _text(input_transcription)
    if input_text:
        events.append(GeminiEvent(type="input_transcript", text=input_text))

    output_transcription = _field(server_content, "output_transcription", "outputTranscription")
    output_text = _text(output_transcription)
    if output_text:
        events.append(GeminiEvent(type="output_transcript", text=output_text))

    model_turn = _field(server_content, "model_turn", "modelTurn")
    parts = _field(model_turn, "parts") or []
    for part in parts:
        inline_data = _field(part, "inline_data", "inlineData")
        if inline_data is None:
            continue
        data = _field(inline_data, "data")
        if data is None:
            events.append(GeminiEvent(type="unsupported", detail="inline_data has no data"))
            continue
        events.append(GeminiEvent(type="audio", audio=_decode_audio(data)))

    if not events and not _is_known_server_content_control_message(server_content):
        events.append(GeminiEvent(type="unsupported", detail="unrecognized Gemini response shape"))
    return events


async def apply_events(
    events: list[GeminiEvent],
    *,
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger | None = None,
) -> None:
    for event in events:
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
        elif event.type == "unsupported":
            detail = event.detail or "unknown event"
            print(f"Unsupported Gemini event: {detail}")


async def run_live_translation(
    *,
    api_key: str,
    target_language: str,
    echo_target_language: bool,
    input_audio_queue: asyncio.Queue[bytes],
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger,
    shutdown_event: asyncio.Event,
) -> None:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiLiveError("google-genai is required; install requirements.txt first.") from exc

    config = build_live_config(target_language, echo_target_language=echo_target_language)
    client = genai.Client(api_key=api_key)

    with _suppress_google_genai_translation_config_warning():
        async with client.aio.live.connect(model=MODEL_NAME, config=config) as session:
            print(f"Gemini Live Translation session started with model {MODEL_NAME}")

            async def sender() -> None:
                while not shutdown_event.is_set():
                    chunk = await input_audio_queue.get()
                    try:
                        validate_input_chunk(chunk)
                    except PCMError as exc:
                        raise GeminiLiveError(str(exc)) from exc
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type=INPUT_MIME_TYPE)
                    )

            async def receiver() -> None:
                async for response in session.receive():
                    time_left = go_away_time_left(response)
                    if time_left is not None:
                        print(f"Gemini sent GoAway; closing session before timeout. time_left={time_left}")
                        shutdown_event.set()
                        break

                    events = extract_gemini_events(response)
                    await apply_events(
                        events,
                        output_audio_queue=output_audio_queue,
                        transcript_log=transcript_log,
                    )
                    if shutdown_event.is_set():
                        break

            shutdown_task = asyncio.create_task(shutdown_event.wait())
            stream_tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
            tasks = [*stream_tasks, shutdown_task]
            try:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if shutdown_task in done:
                    return
                for task in stream_tasks:
                    if task.done():
                        task.result()
            finally:
                shutdown_event.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
