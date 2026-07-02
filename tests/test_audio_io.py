from __future__ import annotations

import queue

from meeting_translator.audio_io import AudioRuntimeStats, RawAudioOutput


def test_output_callback_buffers_partial_chunks_across_callbacks() -> None:
    output = object.__new__(RawAudioOutput)
    output._thread_queue = queue.Queue()
    output._playback_buffer = bytearray()
    output._stats = AudioRuntimeStats()
    output._thread_queue.put(b"abcdef")

    first = bytearray(4)
    second = bytearray(4)

    output._callback(first, frames=2, time_info=None, status=None)
    output._callback(second, frames=2, time_info=None, status=None)

    assert first == b"abcd"
    assert second == b"ef\x00\x00"
