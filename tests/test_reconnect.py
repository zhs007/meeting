from __future__ import annotations

import asyncio
from typing import Any

from meeting_translator.audio_io import AudioRuntimeStats
from meeting_translator.gemini_live_translate import (
    GeminiRuntimeStats,
    drain_input_audio_queue,
    run_live_translation,
)
from meeting_translator.transcript_log import TranscriptLogger


class FakeLiveSession:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.closed = False

    async def __aenter__(self) -> FakeLiveSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True

    async def receive(self):
        for response in self.responses:
            await asyncio.sleep(0)
            yield response

    async def send_realtime_input(self, *, audio: Any) -> None:
        return None


async def _run_with_fake_sessions(
    tmp_path,
    sessions: list[FakeLiveSession],
    *,
    auto_reconnect: bool = True,
    max_reconnects: int = 0,
) -> tuple[list[FakeLiveSession], GeminiRuntimeStats, AudioRuntimeStats, list[str]]:
    created: list[FakeLiveSession] = []

    def session_factory() -> FakeLiveSession:
        session = sessions.pop(0)
        created.append(session)
        return session

    stale_clear_calls: list[str] = []
    input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
    output_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
    output_queue.put_nowait(b"stale-output")
    shutdown_event = asyncio.Event()
    capture_active_event = asyncio.Event()
    gemini_stats = GeminiRuntimeStats()
    audio_stats = AudioRuntimeStats()
    transcript_log = TranscriptLogger(
        input_device="Fake Input",
        output_device="Fake Output",
        target_language="en",
        log_dir=tmp_path,
    )

    await run_live_translation(
        api_key="unused",
        target_language="en",
        echo_target_language=False,
        input_audio_queue=input_queue,
        output_audio_queue=output_queue,
        transcript_log=transcript_log,
        shutdown_event=shutdown_event,
        gemini_stats=gemini_stats,
        audio_stats=audio_stats,
        auto_reconnect=auto_reconnect,
        max_reconnects=max_reconnects,
        clear_stale_audio=lambda: stale_clear_calls.append("called"),
        capture_active_event=capture_active_event,
        session_factory=session_factory,
    )

    assert output_queue.empty()
    assert not capture_active_event.is_set()
    return created, gemini_stats, audio_stats, stale_clear_calls


def test_goaway_auto_reconnect_creates_second_session_and_clears_stale_output(tmp_path) -> None:
    created, gemini_stats, audio_stats, stale_clear_calls = asyncio.run(
        _run_with_fake_sessions(
            tmp_path,
            [
                FakeLiveSession([{"goAway": {"timeLeft": "10s"}}]),
                FakeLiveSession([{"usageMetadata": {"totalTokenCount": 1}}]),
            ],
        )
    )

    assert len(created) == 2
    assert all(session.closed for session in created)
    assert gemini_stats.goaway_count == 1
    assert gemini_stats.reconnect_count == 1
    assert gemini_stats.session_count == 2
    assert audio_stats.output_stale_cleared_chunks == 1
    assert stale_clear_calls == ["called"]


def test_goaway_without_auto_reconnect_ends_normally(tmp_path) -> None:
    created, gemini_stats, audio_stats, stale_clear_calls = asyncio.run(
        _run_with_fake_sessions(
            tmp_path,
            [FakeLiveSession([{"goAway": {"timeLeft": "10s"}}])],
            auto_reconnect=False,
        )
    )

    assert len(created) == 1
    assert gemini_stats.goaway_count == 1
    assert gemini_stats.reconnect_count == 0
    assert gemini_stats.last_session_end_reason == "closed_after_goaway"
    assert audio_stats.output_stale_cleared_chunks == 1
    assert stale_clear_calls == ["called"]


def test_goaway_reconnect_limit_is_explicit(tmp_path) -> None:
    created, gemini_stats, _audio_stats, _stale_clear_calls = asyncio.run(
        _run_with_fake_sessions(
            tmp_path,
            [
                FakeLiveSession([{"goAway": {"timeLeft": "10s"}}]),
                FakeLiveSession([{"goAway": {"timeLeft": "9s"}}]),
            ],
            max_reconnects=1,
        )
    )

    assert len(created) == 2
    assert gemini_stats.goaway_count == 2
    assert gemini_stats.reconnect_count == 1
    assert gemini_stats.last_session_end_reason == "reconnect_limit_reached_after_goaway"


def test_stale_input_queue_is_counted_when_drained_before_reconnect() -> None:
    input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=8)
    input_queue.put_nowait(b"stale-input")
    audio_stats = AudioRuntimeStats()

    drained = drain_input_audio_queue(input_queue, audio_stats=audio_stats)

    assert drained == 1
    assert input_queue.empty()
    assert audio_stats.input_stale_cleared_chunks == 1
    assert audio_stats.input_stale_cleared_bytes == len(b"stale-input")
