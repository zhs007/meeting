from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from meeting_openai_translator.openai_events import apply_openai_event, parse_openai_event
from meeting_openai_translator.pcm import PCMError, pcm16_to_base64, validate_input_chunk
from meeting_openai_translator.transcript_log import TranscriptLogger


MODEL_NAME = "gpt-realtime-translate"
ENDPOINT = f"wss://api.openai.com/v1/realtime/translations?model={MODEL_NAME}"
SESSION_CLOSE_TIMEOUT_SEC = 30


class OpenAIRealtimeError(RuntimeError):
    """Raised when OpenAI Realtime Translation cannot stream safely."""


@dataclass
class OpenAIRealtimeSendState:
    close_sent: bool = False

    def append_event(self, chunk: bytes) -> dict[str, Any]:
        if self.close_sent:
            raise OpenAIRealtimeError("cannot append audio after session.close was sent")
        try:
            validate_input_chunk(chunk)
        except PCMError as exc:
            raise OpenAIRealtimeError(str(exc)) from exc
        return {
            "type": "session.input_audio_buffer.append",
            "audio": pcm16_to_base64(chunk),
        }

    def close_event(self) -> dict[str, str]:
        self.close_sent = True
        return {"type": "session.close"}


def build_headers(api_key: str, safety_identifier: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Safety-Identifier": safety_identifier,
    }


def build_session_update(target_language: str) -> dict[str, Any]:
    return {
        "type": "session.update",
        "session": {
            "audio": {
                "output": {
                    "language": target_language,
                }
            }
        },
    }


def _openai_error_message(message: dict[str, Any]) -> str:
    error = message.get("error")
    if not isinstance(error, dict):
        return "unknown OpenAI Realtime error"
    code = error.get("code") or error.get("type") or "unknown"
    detail = error.get("message") or "no message"
    return f"{code}: {detail}"


def _loads_message(raw_message: str | bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise OpenAIRealtimeError("OpenAI Realtime returned non-JSON event") from exc
    if not isinstance(value, dict):
        raise OpenAIRealtimeError("OpenAI Realtime event must be a JSON object")
    if value.get("type") == "error":
        raise OpenAIRealtimeError(f"OpenAI Realtime error: {_openai_error_message(value)}")
    return value


async def _connect(**kwargs: Any) -> Any:
    try:
        from websockets.asyncio.client import connect
    except ImportError:
        try:
            from websockets import connect
        except ImportError as exc:
            raise OpenAIRealtimeError("websockets is required; install requirements.txt first.") from exc
    return connect(**kwargs)


async def run_realtime_translation(
    *,
    api_key: str,
    safety_identifier: str,
    target_language: str,
    input_audio_queue: asyncio.Queue[bytes],
    output_audio_queue: asyncio.Queue[bytes],
    transcript_log: TranscriptLogger,
    shutdown_event: asyncio.Event,
) -> None:
    state = OpenAIRealtimeSendState()
    connect_context = await _connect(
        uri=ENDPOINT,
        additional_headers=build_headers(api_key, safety_identifier),
        max_size=None,
    )
    async with connect_context as websocket:
        await websocket.send(json.dumps(build_session_update(target_language)))
        print(f"OpenAI Realtime Translation session started with model {MODEL_NAME}")

        async def sender() -> None:
            while not shutdown_event.is_set() and not state.close_sent:
                chunk = await input_audio_queue.get()
                await websocket.send(json.dumps(state.append_event(chunk)))

        async def receiver() -> None:
            async for raw_message in websocket:
                message = _loads_message(raw_message)
                closed = await apply_openai_event(
                    parse_openai_event(message),
                    output_audio_queue=output_audio_queue,
                    transcript_log=transcript_log,
                )
                if closed:
                    shutdown_event.set()
                    return
            raise OpenAIRealtimeError("OpenAI Realtime socket closed before session.closed")

        sender_task = asyncio.create_task(sender())
        receiver_task = asyncio.create_task(receiver())
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        try:
            done, _pending = await asyncio.wait(
                [sender_task, receiver_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in (sender_task, receiver_task):
                if task in done:
                    task.result()

            if receiver_task.done():
                receiver_task.result()
                return

            if not sender_task.done():
                sender_task.cancel()
                await asyncio.gather(sender_task, return_exceptions=True)

            if not state.close_sent:
                await websocket.send(json.dumps(state.close_event()))

            try:
                await asyncio.wait_for(receiver_task, timeout=SESSION_CLOSE_TIMEOUT_SEC)
            except TimeoutError as exc:
                raise OpenAIRealtimeError(
                    "timed out waiting for session.closed after session.close"
                ) from exc
            receiver_task.result()
        finally:
            shutdown_event.set()
            if not sender_task.done():
                sender_task.cancel()
            if not receiver_task.done():
                receiver_task.cancel()
            shutdown_task.cancel()
            await asyncio.gather(sender_task, receiver_task, shutdown_task, return_exceptions=True)
