from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass, field
from typing import Any

from meeting_translator.pcm import (
    INPUT_CHANNELS,
    INPUT_DTYPE,
    INPUT_SAMPLE_RATE,
    INPUT_SAMPLES_PER_CHUNK,
    OUTPUT_CHANNELS,
    OUTPUT_DTYPE,
    OUTPUT_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
)


@dataclass
class AudioRuntimeStats:
    input_overflows: int = 0
    output_silence_callbacks: int = 0
    output_dropped_chunks: int = 0
    callback_errors: list[str] = field(default_factory=list)


class RawAudioInput:
    def __init__(
        self,
        *,
        device_index: int,
        output_queue: asyncio.Queue[bytes],
        loop: asyncio.AbstractEventLoop,
        stats: AudioRuntimeStats,
    ) -> None:
        import sounddevice as sd

        self._queue = output_queue
        self._loop = loop
        self._stats = stats
        self._stream = sd.RawInputStream(
            device=device_index,
            samplerate=INPUT_SAMPLE_RATE,
            channels=INPUT_CHANNELS,
            dtype=INPUT_DTYPE,
            blocksize=INPUT_SAMPLES_PER_CHUNK,
            callback=self._callback,
        )

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status:
            self._stats.callback_errors.append(f"input callback status: {status}")
        chunk = bytes(indata)

        def offer() -> None:
            try:
                self._queue.put_nowait(chunk)
            except asyncio.QueueFull:
                self._stats.input_overflows += 1

        self._loop.call_soon_threadsafe(offer)

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()


class RawAudioOutput:
    def __init__(
        self,
        *,
        device_index: int,
        input_queue: asyncio.Queue[bytes],
        stats: AudioRuntimeStats,
        thread_queue_size: int = 50,
    ) -> None:
        import sounddevice as sd

        self._async_queue = input_queue
        self._thread_queue: queue.Queue[bytes] = queue.Queue(maxsize=thread_queue_size)
        self._playback_buffer = bytearray()
        self._stats = stats
        self._closed = asyncio.Event()
        self._pump_task: asyncio.Task[None] | None = None
        self._stream = sd.RawOutputStream(
            device=device_index,
            samplerate=OUTPUT_SAMPLE_RATE,
            channels=OUTPUT_CHANNELS,
            dtype=OUTPUT_DTYPE,
            blocksize=1_200,
            callback=self._callback,
        )

    def _callback(self, outdata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status:
            self._stats.callback_errors.append(f"output callback status: {status}")
        expected = frames * OUTPUT_CHANNELS * PCM16_BYTES_PER_SAMPLE
        while len(self._playback_buffer) < expected:
            try:
                self._playback_buffer.extend(self._thread_queue.get_nowait())
            except queue.Empty:
                break

        if len(self._playback_buffer) >= expected:
            outdata[:] = self._playback_buffer[:expected]
            del self._playback_buffer[:expected]
            return

        available = bytes(self._playback_buffer)
        self._playback_buffer.clear()
        if available:
            outdata[:] = available + (b"\x00" * (expected - len(available)))
        else:
            outdata[:] = b"\x00" * expected
            self._stats.output_silence_callbacks += 1

    async def _pump(self) -> None:
        while not self._closed.is_set():
            chunk = await self._async_queue.get()
            try:
                self._thread_queue.put_nowait(chunk)
            except queue.Full:
                self._stats.output_dropped_chunks += 1

    def start(self) -> None:
        self._stream.start()
        self._pump_task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        self._closed.set()
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()
