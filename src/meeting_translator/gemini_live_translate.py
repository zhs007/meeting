from __future__ import annotations

import asyncio
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, AsyncContextManager, Callable, Iterator, Literal

from meeting_translator.audio_io import AudioRuntimeStats
from meeting_translator.pcm import INPUT_MIME_TYPE, PCMError, pcm16_from_base64, validate_input_chunk
from meeting_translator.transcript_log import TranscriptLogger


MODEL_NAME = "gemini-3.5-live-translate-preview"

EventType = Literal["input_transcript", "output_transcript", "audio", "unsupported"]
SessionEndReason = Literal["shutdown", "goaway", "ended"]


class GeminiLiveError(RuntimeError):
    """Raised when Gemini Live Translation cannot be configured or streamed safely."""


@dataclass(frozen=True)
class GeminiEvent:
    type: EventType
    text: str | None = None
    audio: bytes | None = None
    detail: str | None = None


@dataclass
class GeminiRuntimeStats:
    input_chunks_sent: int = 0
    output_audio_chunks_received: int = 0
    output_audio_bytes_received: int = 0
    unsupported_event_count: int = 0
    first_unsupported_event: str | None = None
    goaway_count: int = 0
    reconnect_count: int = 0
    session_count: int = 0
    session_resumption_updates: int = 0
    last_goaway_time_left: str | None = None
    last_session_end_reason: str | None = None
    last_error_classification: str | None = None

    def record_unsupported_event(self, detail: str) -> None:
        self.unsupported_event_count += 1
        if self.first_unsupported_event is None:
            self.first_unsupported_event = detail


@dataclass(frozen=True)
class LiveSessionResult:
    reason: SessionEndReason
    goaway_time_left: str | None = None


@dataclass(frozen=True)
class FallbackAudioBlob:
    data: bytes
    mime_type: str


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


def _source_language_guard_instruction(source_language: str, target_language: str) -> str:
    return (
        "You are a live meeting translator. "
        f"The expected source language is {source_language}. "
        f"Translate only clear speech from that source language to {target_language}. "
        "Ignore silence, breathing, microphone noise, and unclear audio; do not invent transcript text. "
        "Do not switch to another source language because of silence, noise, or prior transcript artifacts."
    )


def build_live_config(
    target_language: str,
    *,
    source_language: str = "zh-CN",
    voice_name: str | None = "Kore",
    echo_target_language: bool = False,
) -> Any:
    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiLiveError("google-genai is required; install requirements.txt first.") from exc

    speech_config = None
    if voice_name is not None:
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice_name,
                ),
            ),
        )

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=_source_language_guard_instruction(source_language, target_language),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=speech_config,
        realtime_input_config=types.RealtimeInputConfig(
            turn_coverage=types.TurnCoverage.TURN_INCLUDES_ONLY_ACTIVITY,
        ),
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


def has_session_resumption_update(response: Any) -> bool:
    return _has_non_empty_field(
        response,
        "session_resumption_update",
        "sessionResumptionUpdate",
    )


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
    gemini_stats: GeminiRuntimeStats | None = None,
    audio_stats: AudioRuntimeStats | None = None,
    debug_events: bool = False,
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
            if gemini_stats is not None:
                gemini_stats.output_audio_chunks_received += 1
                gemini_stats.output_audio_bytes_received += len(event.audio)
            _put_latest_audio(output_audio_queue, event.audio, audio_stats=audio_stats)
            if transcript_log:
                transcript_log.output_audio(len(event.audio))
        elif event.type == "unsupported":
            detail = event.detail or "unknown event"
            if gemini_stats is not None:
                gemini_stats.record_unsupported_event(detail)
            if debug_events:
                print(f"Unsupported Gemini event: {detail}")


def _put_latest_audio(
    output_audio_queue: asyncio.Queue[bytes],
    chunk: bytes,
    *,
    audio_stats: AudioRuntimeStats | None = None,
) -> None:
    while True:
        try:
            output_audio_queue.put_nowait(chunk)
            break
        except asyncio.QueueFull:
            try:
                dropped = output_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                continue
            if audio_stats is not None:
                audio_stats.record_output_drop(dropped)
    if audio_stats is not None:
        audio_stats.note_output_async_queue_depth(output_audio_queue.qsize())


def drain_output_audio_queue(
    output_audio_queue: asyncio.Queue[bytes],
    *,
    audio_stats: AudioRuntimeStats | None = None,
) -> int:
    drained = 0
    while True:
        try:
            dropped = output_audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        drained += 1
        if audio_stats is not None:
            audio_stats.record_output_drop(dropped, stale=True)
    return drained


def drain_input_audio_queue(
    input_audio_queue: asyncio.Queue[bytes],
    *,
    audio_stats: AudioRuntimeStats | None = None,
) -> int:
    drained = 0
    while True:
        try:
            dropped = input_audio_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        drained += 1
        if audio_stats is not None:
            audio_stats.record_input_stale_drop(dropped)
    return drained


def classify_gemini_exception(exc: BaseException) -> str:
    message = str(exc).lower()
    if any(token in message for token in ("unauth", "permission", "api key", "apikey")):
        return "auth"
    if any(token in message for token in ("quota", "rate limit", "resource exhausted")):
        return "quota_or_rate_limit"
    if any(token in message for token in ("policy", "1008")):
        return "policy_or_websocket_close"
    if any(token in message for token in ("dns", "name resolution", "proxy", "network", "timeout")):
        return "network"
    return type(exc).__name__


async def run_single_live_translation_session(
    *,
    session_factory: Callable[[], AsyncContextManager[Any]],
    blob_factory: Callable[[bytes], Any],
    input_audio_queue: asyncio.Queue[bytes],
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger,
    shutdown_event: asyncio.Event,
    gemini_stats: GeminiRuntimeStats,
    audio_stats: AudioRuntimeStats | None = None,
    capture_active_event: asyncio.Event | None = None,
    debug_events: bool = False,
) -> LiveSessionResult:
    gemini_stats.session_count += 1
    with _suppress_google_genai_translation_config_warning():
        async with session_factory() as session:
            print(f"Gemini Live Translation session started with model {MODEL_NAME}")

            async def sender() -> None:
                while not shutdown_event.is_set():
                    try:
                        chunk = await asyncio.wait_for(input_audio_queue.get(), timeout=0.1)
                    except TimeoutError:
                        continue
                    try:
                        validate_input_chunk(chunk)
                    except PCMError as exc:
                        raise GeminiLiveError(str(exc)) from exc
                    await session.send_realtime_input(audio=blob_factory(chunk))
                    gemini_stats.input_chunks_sent += 1
                    if audio_stats is not None:
                        audio_stats.note_input_queue_depth(input_audio_queue.qsize())

            async def receiver() -> LiveSessionResult:
                async for response in session.receive():
                    if shutdown_event.is_set():
                        return LiveSessionResult(reason="shutdown")
                    if has_session_resumption_update(response):
                        gemini_stats.session_resumption_updates += 1
                    time_left = go_away_time_left(response)
                    if time_left is not None:
                        gemini_stats.goaway_count += 1
                        gemini_stats.last_goaway_time_left = time_left
                        return LiveSessionResult(reason="goaway", goaway_time_left=time_left)

                    events = extract_gemini_events(response)
                    await apply_events(
                        events,
                        output_audio_queue=output_audio_queue,
                        transcript_log=transcript_log,
                        gemini_stats=gemini_stats,
                        audio_stats=audio_stats,
                        debug_events=debug_events,
                    )
                    if shutdown_event.is_set():
                        return LiveSessionResult(reason="shutdown")
                return LiveSessionResult(reason="ended")

            shutdown_task = asyncio.create_task(shutdown_event.wait())
            stream_tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
            tasks = [*stream_tasks, shutdown_task]
            if capture_active_event is not None:
                capture_active_event.set()
            try:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if shutdown_task in done:
                    return LiveSessionResult(reason="shutdown")
                for task in stream_tasks:
                    if task.done():
                        result = task.result()
                        if isinstance(result, LiveSessionResult):
                            return result
                return LiveSessionResult(reason="ended")
            finally:
                if capture_active_event is not None:
                    capture_active_event.clear()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)


def _default_session_factory(
    *,
    api_key: str,
    source_language: str,
    target_language: str,
    voice_name: str | None,
    echo_target_language: bool,
) -> tuple[Callable[[], AsyncContextManager[Any]], Callable[[bytes], Any]]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise GeminiLiveError("google-genai is required; install requirements.txt first.") from exc

    config = build_live_config(
        target_language,
        source_language=source_language,
        voice_name=voice_name,
        echo_target_language=echo_target_language,
    )
    client = genai.Client(api_key=api_key)

    def session_factory() -> AsyncContextManager[Any]:
        return client.aio.live.connect(model=MODEL_NAME, config=config)

    def blob_factory(chunk: bytes) -> Any:
        return types.Blob(data=chunk, mime_type=INPUT_MIME_TYPE)

    return session_factory, blob_factory


async def run_live_translation(
    *,
    api_key: str,
    source_language: str,
    target_language: str,
    voice_name: str | None,
    echo_target_language: bool,
    input_audio_queue: asyncio.Queue[bytes],
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger,
    shutdown_event: asyncio.Event,
    gemini_stats: GeminiRuntimeStats | None = None,
    audio_stats: AudioRuntimeStats | None = None,
    auto_reconnect: bool = True,
    max_reconnects: int = 0,
    debug_events: bool = False,
    clear_stale_audio: Callable[[], None] | None = None,
    capture_active_event: asyncio.Event | None = None,
    session_factory: Callable[[], AsyncContextManager[Any]] | None = None,
    blob_factory: Callable[[bytes], Any] | None = None,
) -> None:
    gemini_stats = gemini_stats or GeminiRuntimeStats()
    if session_factory is None:
        session_factory, default_blob_factory = _default_session_factory(
            api_key=api_key,
            source_language=source_language,
            target_language=target_language,
            voice_name=voice_name,
            echo_target_language=echo_target_language,
        )
        blob_factory = blob_factory or default_blob_factory
    else:
        blob_factory = blob_factory or (
            lambda chunk: FallbackAudioBlob(data=chunk, mime_type=INPUT_MIME_TYPE)
        )

    while not shutdown_event.is_set():
        try:
            result = await run_single_live_translation_session(
                session_factory=session_factory,
                blob_factory=blob_factory,
                input_audio_queue=input_audio_queue,
                output_audio_queue=output_audio_queue,
                transcript_log=transcript_log,
                shutdown_event=shutdown_event,
                gemini_stats=gemini_stats,
                audio_stats=audio_stats,
                capture_active_event=capture_active_event,
                debug_events=debug_events,
            )
        except GeminiLiveError:
            raise
        except Exception as exc:
            classification = classify_gemini_exception(exc)
            gemini_stats.last_error_classification = classification
            raise GeminiLiveError(
                f"Gemini Live Translation failed ({classification}): {exc}"
            ) from exc

        gemini_stats.last_session_end_reason = result.reason
        if result.reason == "goaway":
            drained_input = drain_input_audio_queue(input_audio_queue, audio_stats=audio_stats)
            drained = drain_output_audio_queue(output_audio_queue, audio_stats=audio_stats)
            if clear_stale_audio is not None:
                clear_stale_audio()
            if auto_reconnect and (max_reconnects == 0 or gemini_stats.reconnect_count < max_reconnects):
                gemini_stats.reconnect_count += 1
                print(
                    "Gemini sent GoAway; reconnecting before timeout. "
                    f"time_left={result.goaway_time_left}; "
                    f"cleared_stale_input_chunks={drained_input}; "
                    f"cleared_stale_async_chunks={drained}"
                )
                continue
            if auto_reconnect:
                gemini_stats.last_session_end_reason = "reconnect_limit_reached_after_goaway"
                print(
                    "Gemini sent GoAway; reconnect limit reached. "
                    f"time_left={result.goaway_time_left}; "
                    f"cleared_stale_input_chunks={drained_input}; "
                    f"cleared_stale_async_chunks={drained}"
                )
            else:
                gemini_stats.last_session_end_reason = "closed_after_goaway"
                print(
                    "Gemini sent GoAway; closing session before timeout. "
                    f"time_left={result.goaway_time_left}; "
                    f"cleared_stale_input_chunks={drained_input}; "
                    f"cleared_stale_async_chunks={drained}"
                )
            return
        return
