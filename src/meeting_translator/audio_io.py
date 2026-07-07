from __future__ import annotations

import asyncio
import math
import queue
from dataclasses import dataclass, field
from typing import Any

from meeting_translator.pcm import (
    INPUT_CHANNELS,
    INPUT_CHUNK_MS,
    INPUT_DTYPE,
    INPUT_SAMPLE_RATE,
    INPUT_SAMPLES_PER_CHUNK,
    OUTPUT_CHANNELS,
    OUTPUT_DTYPE,
    OUTPUT_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
)


def output_bytes_to_ms(byte_count: int) -> int:
    bytes_per_second = OUTPUT_SAMPLE_RATE * OUTPUT_CHANNELS * PCM16_BYTES_PER_SAMPLE
    return round(byte_count * 1000 / bytes_per_second)


def pcm16_rms(chunk: bytes) -> int:
    if not chunk:
        return 0
    even_byte_count = len(chunk) - (len(chunk) % PCM16_BYTES_PER_SAMPLE)
    if even_byte_count == 0:
        return 0
    samples = memoryview(chunk[:even_byte_count]).cast("h")
    if len(samples) == 0:
        return 0
    return round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))


@dataclass
class AudioRuntimeStats:
    input_chunks_captured: int = 0
    input_chunks_queued: int = 0
    input_dropped_while_disconnected: int = 0
    input_gate_suppressed_chunks: int = 0
    input_gate_suppressed_bytes: int = 0
    input_gate_hangover_kept_chunks: int = 0
    input_last_rms: int = 0
    input_max_rms: int = 0
    input_stale_cleared_chunks: int = 0
    input_stale_cleared_bytes: int = 0
    input_overflows: int = 0
    input_overflow_error: str | None = None
    input_max_queue_depth: int = 0
    output_chunks_enqueued_to_thread: int = 0
    output_audio_callbacks_with_audio: int = 0
    output_audio_bytes_played: int = 0
    output_silence_callbacks: int = 0
    output_dropped_chunks: int = 0
    output_dropped_bytes: int = 0
    output_stale_cleared_chunks: int = 0
    output_stale_cleared_bytes: int = 0
    output_max_async_queue_depth: int = 0
    output_max_thread_queue_depth: int = 0
    output_max_playback_buffer_ms: int = 0
    output_prebuffer_silence_callbacks: int = 0
    output_prebuffer_forced_starts: int = 0
    callback_errors: list[str] = field(default_factory=list)

    def note_input_queue_depth(self, depth: int) -> None:
        self.input_max_queue_depth = max(self.input_max_queue_depth, depth)

    def record_input_drop_while_disconnected(self, chunk: bytes) -> None:
        self.input_dropped_while_disconnected += 1

    def note_input_rms(self, rms: int) -> None:
        self.input_last_rms = rms
        self.input_max_rms = max(self.input_max_rms, rms)

    def record_input_gate_suppression(self, chunk: bytes, *, rms: int) -> None:
        self.input_gate_suppressed_chunks += 1
        self.input_gate_suppressed_bytes += len(chunk)
        self.note_input_rms(rms)

    def record_input_gate_hangover_keep(self, *, rms: int) -> None:
        self.input_gate_hangover_kept_chunks += 1
        self.note_input_rms(rms)

    def record_input_stale_drop(self, chunk: bytes) -> None:
        self.input_stale_cleared_chunks += 1
        self.input_stale_cleared_bytes += len(chunk)

    def note_output_async_queue_depth(self, depth: int) -> None:
        self.output_max_async_queue_depth = max(self.output_max_async_queue_depth, depth)

    def note_output_thread_queue_depth(self, depth: int) -> None:
        self.output_max_thread_queue_depth = max(self.output_max_thread_queue_depth, depth)

    def note_playback_buffer_bytes(self, byte_count: int) -> None:
        self.output_max_playback_buffer_ms = max(
            self.output_max_playback_buffer_ms,
            output_bytes_to_ms(byte_count),
        )

    def record_output_drop(self, chunk: bytes, *, stale: bool = False) -> None:
        self.output_dropped_chunks += 1
        self.output_dropped_bytes += len(chunk)
        if stale:
            self.output_stale_cleared_chunks += 1
            self.output_stale_cleared_bytes += len(chunk)


class RawAudioInput:
    def __init__(
        self,
        *,
        device_index: int,
        output_queue: asyncio.Queue[bytes],
        loop: asyncio.AbstractEventLoop,
        stats: AudioRuntimeStats,
        overflow_event: asyncio.Event | None = None,
        capture_enabled_event: asyncio.Event | None = None,
        input_gate_rms: int = 0,
        input_gate_hangover_ms: int = 800,
    ) -> None:
        import sounddevice as sd

        self._queue = output_queue
        self._loop = loop
        self._stats = stats
        self._overflow_event = overflow_event
        self._capture_enabled_event = capture_enabled_event
        self._input_gate_rms = input_gate_rms
        self._input_gate_hangover_chunks = max(
            0,
            math.ceil(input_gate_hangover_ms / INPUT_CHUNK_MS),
        )
        self._input_gate_hangover_remaining = 0
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
        self._stats.input_chunks_captured += 1

        def offer() -> None:
            queued_chunk = chunk
            if (
                self._capture_enabled_event is not None
                and not self._capture_enabled_event.is_set()
            ):
                self._stats.record_input_drop_while_disconnected(queued_chunk)
                return
            rms = pcm16_rms(queued_chunk)
            if self._input_gate_rms > 0:
                if rms >= self._input_gate_rms:
                    self._input_gate_hangover_remaining = self._input_gate_hangover_chunks
                    self._stats.note_input_rms(rms)
                elif self._input_gate_hangover_remaining > 0:
                    self._input_gate_hangover_remaining -= 1
                    self._stats.record_input_gate_hangover_keep(rms=rms)
                else:
                    self._stats.record_input_gate_suppression(queued_chunk, rms=rms)
                    return
            else:
                self._stats.note_input_rms(rms)
            try:
                self._queue.put_nowait(queued_chunk)
                self._stats.input_chunks_queued += 1
                self._stats.note_input_queue_depth(self._queue.qsize())
            except asyncio.QueueFull:
                self._stats.input_overflows += 1
                self._stats.input_overflow_error = (
                    f"input audio queue overflowed at maxsize={self._queue.maxsize}; "
                    "Gemini sender is not keeping up with capture."
                )
                if self._overflow_event is not None:
                    self._overflow_event.set()

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
        thread_queue_size: int,
        max_playback_buffer_ms: int,
        output_prebuffer_ms: int = 0,
    ) -> None:
        import sounddevice as sd

        self._async_queue = input_queue
        self._thread_queue: queue.Queue[bytes] = queue.Queue(maxsize=thread_queue_size)
        self._playback_buffer = bytearray()
        self._max_playback_buffer_bytes = (
            OUTPUT_SAMPLE_RATE
            * OUTPUT_CHANNELS
            * PCM16_BYTES_PER_SAMPLE
            * max_playback_buffer_ms
            // 1000
        )
        self._output_prebuffer_bytes = (
            OUTPUT_SAMPLE_RATE
            * OUTPUT_CHANNELS
            * PCM16_BYTES_PER_SAMPLE
            * output_prebuffer_ms
            // 1000
        )
        self._playback_started = output_prebuffer_ms <= 0
        self._prebuffer_wait_bytes = 0
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

    def _trim_playback_buffer_for_latency(self) -> None:
        if len(self._playback_buffer) <= self._max_playback_buffer_bytes:
            self._stats.note_playback_buffer_bytes(len(self._playback_buffer))
            return
        drop_bytes = len(self._playback_buffer) - self._max_playback_buffer_bytes
        dropped = bytes(self._playback_buffer[:drop_bytes])
        del self._playback_buffer[:drop_bytes]
        self._stats.record_output_drop(dropped)
        self._stats.note_playback_buffer_bytes(len(self._playback_buffer) + drop_bytes)

    def _enqueue_thread_chunk(self, chunk: bytes) -> None:
        try:
            self._thread_queue.put_nowait(chunk)
        except queue.Full:
            try:
                dropped = self._thread_queue.get_nowait()
            except queue.Empty:
                dropped = b""
            if dropped:
                self._stats.record_output_drop(dropped)
            self._thread_queue.put_nowait(chunk)
        self._stats.output_chunks_enqueued_to_thread += 1
        self._stats.note_output_thread_queue_depth(self._thread_queue.qsize())

    def clear_pending(self) -> None:
        while True:
            try:
                dropped = self._thread_queue.get_nowait()
            except queue.Empty:
                break
            self._stats.record_output_drop(dropped, stale=True)
        if self._playback_buffer:
            dropped = bytes(self._playback_buffer)
            self._playback_buffer.clear()
            self._stats.record_output_drop(dropped, stale=True)
        self._playback_started = self._output_prebuffer_bytes <= 0
        self._prebuffer_wait_bytes = 0

    def thread_queue_depth(self) -> int:
        return self._thread_queue.qsize()

    def playback_buffer_ms(self) -> int:
        return output_bytes_to_ms(len(self._playback_buffer))

    def _drain_thread_queue_until(self, minimum_bytes: int) -> None:
        while len(self._playback_buffer) < minimum_bytes:
            try:
                self._playback_buffer.extend(self._thread_queue.get_nowait())
                self._stats.note_output_thread_queue_depth(self._thread_queue.qsize())
                self._stats.note_playback_buffer_bytes(len(self._playback_buffer))
            except queue.Empty:
                break

    def _hold_for_prebuffer(self, outdata: Any, expected: int) -> bool:
        prebuffer_bytes = getattr(self, "_output_prebuffer_bytes", 0)
        if prebuffer_bytes <= 0 or getattr(self, "_playback_started", True):
            return False
        if len(self._playback_buffer) >= prebuffer_bytes:
            self._playback_started = True
            self._prebuffer_wait_bytes = 0
            return False
        if not self._playback_buffer:
            self._prebuffer_wait_bytes = 0
            return False
        self._prebuffer_wait_bytes += expected
        if self._prebuffer_wait_bytes >= prebuffer_bytes:
            self._playback_started = True
            self._prebuffer_wait_bytes = 0
            self._stats.output_prebuffer_forced_starts += 1
            return False
        outdata[:] = b"\x00" * expected
        self._stats.output_silence_callbacks += 1
        self._stats.output_prebuffer_silence_callbacks += 1
        return True

    def _callback(self, outdata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status:
            self._stats.callback_errors.append(f"output callback status: {status}")
        expected = frames * OUTPUT_CHANNELS * PCM16_BYTES_PER_SAMPLE
        prebuffer_bytes = getattr(self, "_output_prebuffer_bytes", 0)
        minimum_bytes = expected
        if prebuffer_bytes > 0 and not getattr(self, "_playback_started", True):
            minimum_bytes = max(expected, prebuffer_bytes)
        self._drain_thread_queue_until(minimum_bytes)
        self._trim_playback_buffer_for_latency()
        if self._hold_for_prebuffer(outdata, expected):
            return

        if len(self._playback_buffer) >= expected:
            outdata[:] = self._playback_buffer[:expected]
            del self._playback_buffer[:expected]
            self._stats.output_audio_callbacks_with_audio += 1
            self._stats.output_audio_bytes_played += expected
            return

        available = bytes(self._playback_buffer)
        self._playback_buffer.clear()
        if available:
            outdata[:] = available + (b"\x00" * (expected - len(available)))
            self._stats.output_audio_callbacks_with_audio += 1
            self._stats.output_audio_bytes_played += len(available)
            self._playback_started = prebuffer_bytes <= 0
        else:
            outdata[:] = b"\x00" * expected
            self._stats.output_silence_callbacks += 1
            self._playback_started = prebuffer_bytes <= 0
        self._prebuffer_wait_bytes = 0

    async def _pump(self) -> None:
        while not self._closed.is_set():
            chunk = await self._async_queue.get()
            self._enqueue_thread_chunk(chunk)

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
