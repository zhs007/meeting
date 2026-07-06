from __future__ import annotations

import asyncio
import queue

from meeting_translator.audio_io import AudioRuntimeStats, RawAudioInput, RawAudioOutput, pcm16_rms
from meeting_translator.config import (
    DEFAULT_MAX_PLAYBACK_BUFFER_MS,
    DEFAULT_OUTPUT_QUEUE_CHUNKS,
    DEFAULT_OUTPUT_THREAD_QUEUE_CHUNKS,
)
from meeting_translator.pcm import INPUT_CHUNK_MS


def test_output_callback_buffers_partial_chunks_across_callbacks() -> None:
    output = object.__new__(RawAudioOutput)
    output._thread_queue = queue.Queue()
    output._playback_buffer = bytearray()
    output._max_playback_buffer_bytes = 10_000
    output._stats = AudioRuntimeStats()
    output._thread_queue.put(b"abcdef")

    first = bytearray(4)
    second = bytearray(4)

    output._callback(first, frames=2, time_info=None, status=None)
    output._callback(second, frames=2, time_info=None, status=None)

    assert first == b"abcd"
    assert second == b"ef\x00\x00"


def test_output_thread_queue_full_drops_oldest_chunk() -> None:
    output = object.__new__(RawAudioOutput)
    output._thread_queue = queue.Queue(maxsize=1)
    output._playback_buffer = bytearray()
    output._max_playback_buffer_bytes = 10_000
    output._stats = AudioRuntimeStats()
    output._thread_queue.put(b"old")

    output._enqueue_thread_chunk(b"new")

    assert output._thread_queue.get_nowait() == b"new"
    assert output._stats.output_dropped_chunks == 1
    assert output._stats.output_dropped_bytes == 3


def test_output_callback_drops_oldest_playback_buffer_when_latency_cap_is_exceeded() -> None:
    output = object.__new__(RawAudioOutput)
    output._thread_queue = queue.Queue()
    output._playback_buffer = bytearray(b"abcdefgh")
    output._max_playback_buffer_bytes = 4
    output._stats = AudioRuntimeStats()
    outdata = bytearray(2)

    output._callback(outdata, frames=1, time_info=None, status=None)

    assert outdata == b"ef"
    assert output._playback_buffer == bytearray(b"gh")
    assert output._stats.output_dropped_chunks == 1
    assert output._stats.output_dropped_bytes == 4


def test_default_output_latency_budget_is_below_five_seconds() -> None:
    queue_ms = (DEFAULT_OUTPUT_QUEUE_CHUNKS + DEFAULT_OUTPUT_THREAD_QUEUE_CHUNKS) * INPUT_CHUNK_MS
    total_ms = queue_ms + DEFAULT_MAX_PLAYBACK_BUFFER_MS

    assert total_ms < 5_000


def test_input_queue_full_records_overflow_and_sets_error_signal() -> None:
    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Event]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=1)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = None
        input_audio._input_gate_rms = 0
        input_audio._input_gate_hangover_chunks = 0
        input_audio._input_gate_hangover_remaining = 0
        await input_audio._queue.put(b"old")

        input_audio._callback(b"new", frames=1, time_info=None, status=None)
        await asyncio.sleep(0)

        return input_audio._stats, input_audio._overflow_event

    stats, overflow_event = asyncio.run(exercise())

    assert overflow_event.is_set()
    assert stats.input_overflows == 1
    assert stats.input_overflow_error is not None


def test_input_callback_drops_while_capture_is_disconnected_without_overflow() -> None:
    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Queue[bytes], asyncio.Event]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=1)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = asyncio.Event()
        input_audio._input_gate_rms = 0
        input_audio._input_gate_hangover_chunks = 0
        input_audio._input_gate_hangover_remaining = 0
        await input_audio._queue.put(b"old")

        input_audio._callback(b"new", frames=1, time_info=None, status=None)
        await asyncio.sleep(0)

        return input_audio._stats, input_audio._queue, input_audio._overflow_event

    stats, input_queue, overflow_event = asyncio.run(exercise())

    assert input_queue.qsize() == 1
    assert not overflow_event.is_set()
    assert stats.input_dropped_while_disconnected == 1
    assert stats.input_overflows == 0


def test_pcm16_rms_calculates_input_energy() -> None:
    assert pcm16_rms(b"\x00\x00\x00\x00") == 0
    assert pcm16_rms((1000).to_bytes(2, "little", signed=True) * 4) == 1000


def test_input_gate_suppresses_idle_low_rms_chunks_before_queueing() -> None:
    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Queue[bytes]]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=2)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = None
        input_audio._input_gate_rms = 300
        input_audio._input_gate_hangover_chunks = 8
        input_audio._input_gate_hangover_remaining = 0

        input_audio._callback(b"\x00\x00" * 1600, frames=1600, time_info=None, status=None)
        await asyncio.sleep(0)

        return input_audio._stats, input_audio._queue

    stats, input_queue = asyncio.run(exercise())

    assert input_queue.qsize() == 0
    assert stats.input_gate_suppressed_chunks == 1
    assert stats.input_gate_suppressed_bytes == 3200
    assert stats.input_chunks_queued == 0


def test_input_gate_allows_high_rms_chunks_to_queue() -> None:
    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Queue[bytes]]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=2)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = None
        input_audio._input_gate_rms = 300
        input_audio._input_gate_hangover_chunks = 8
        input_audio._input_gate_hangover_remaining = 0
        chunk = (1000).to_bytes(2, "little", signed=True) * 1600

        input_audio._callback(chunk, frames=1600, time_info=None, status=None)
        await asyncio.sleep(0)

        return input_audio._stats, input_audio._queue

    stats, input_queue = asyncio.run(exercise())

    assert input_queue.qsize() == 1
    assert stats.input_gate_suppressed_chunks == 0
    assert stats.input_chunks_queued == 1
    assert stats.input_last_rms == 1000


def test_input_gate_hangover_keeps_low_rms_chunks_after_speech() -> None:
    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Queue[bytes], int]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=4)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = None
        input_audio._input_gate_rms = 300
        input_audio._input_gate_hangover_chunks = 2
        input_audio._input_gate_hangover_remaining = 0
        loud = (1000).to_bytes(2, "little", signed=True) * 1600
        quiet = (100).to_bytes(2, "little", signed=True) * 1600

        input_audio._callback(loud, frames=1600, time_info=None, status=None)
        input_audio._callback(quiet, frames=1600, time_info=None, status=None)
        await asyncio.sleep(0)

        return (
            input_audio._stats,
            input_audio._queue,
            input_audio._input_gate_hangover_remaining,
        )

    stats, input_queue, remaining = asyncio.run(exercise())

    assert input_queue.qsize() == 2
    assert stats.input_gate_hangover_kept_chunks == 1
    assert stats.input_gate_suppressed_chunks == 0
    assert remaining == 1


def test_input_gate_suppresses_low_rms_after_hangover_expires() -> None:
    loud = (1000).to_bytes(2, "little", signed=True) * 1600
    quiet = (100).to_bytes(2, "little", signed=True) * 1600

    async def exercise() -> tuple[AudioRuntimeStats, asyncio.Queue[bytes]]:
        input_audio = object.__new__(RawAudioInput)
        input_audio._queue = asyncio.Queue(maxsize=4)
        input_audio._loop = asyncio.get_running_loop()
        input_audio._stats = AudioRuntimeStats()
        input_audio._overflow_event = asyncio.Event()
        input_audio._capture_enabled_event = None
        input_audio._input_gate_rms = 300
        input_audio._input_gate_hangover_chunks = 1
        input_audio._input_gate_hangover_remaining = 0

        input_audio._callback(loud, frames=1600, time_info=None, status=None)
        input_audio._callback(quiet, frames=1600, time_info=None, status=None)
        input_audio._callback(quiet, frames=1600, time_info=None, status=None)
        await asyncio.sleep(0)

        return input_audio._stats, input_audio._queue

    stats, input_queue = asyncio.run(exercise())

    assert input_queue.qsize() == 2
    assert stats.input_gate_hangover_kept_chunks == 1
    assert stats.input_gate_suppressed_chunks == 1
    assert input_queue.get_nowait() == loud
    assert input_queue.get_nowait() == quiet
