from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from dataclasses import asdict

from meeting_translator import __version__
from meeting_translator.audio_devices import (
    DeviceError,
    format_devices_table,
    list_devices,
    validate_input_device,
    validate_output_device,
)
from meeting_translator.audio_io import AudioRuntimeStats, RawAudioInput, RawAudioOutput
from meeting_translator.config import ConfigError, load_config, require_api_key, require_device_name
from meeting_translator.gemini_live_translate import (
    GeminiLiveError,
    GeminiRuntimeStats,
    MODEL_NAME,
    build_live_config,
    live_translation_config_dict,
    run_live_translation,
)
from meeting_translator.pcm import expected_pcm16_chunk_size
from meeting_translator.transcript_log import TranscriptLogger


def _display_voice_name(voice_name: str | None) -> str:
    return voice_name or "auto"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting_translator")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="List local audio devices")

    def add_runtime_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--input-device", default=None)
        command.add_argument("--output-device", default=None)
        command.add_argument(
            "--source-language",
            default=None,
            help="BCP-47 language code hint for the Gemini input audio",
        )
        command.add_argument("--target-language", default=None)
        command.add_argument(
            "--voice-name",
            default=None,
            help="Fixed Gemini output voice name; use 'auto' for Gemini default voice behavior",
        )
        command.add_argument(
            "--echo-target-language",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Echo audio already spoken in the target language",
        )
        command.add_argument("--input-queue-chunks", type=int, default=None)
        command.add_argument("--output-queue-chunks", type=int, default=None)
        command.add_argument("--output-thread-queue-chunks", type=int, default=None)
        command.add_argument("--max-playback-buffer-ms", type=int, default=None)
        command.add_argument("--metrics-interval-sec", type=float, default=None)
        command.add_argument(
            "--auto-reconnect",
            action=argparse.BooleanOptionalAction,
            default=None,
        )
        command.add_argument("--max-reconnects", type=int, default=None)
        command.add_argument(
            "--debug-events",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Print full unsupported Gemini event diagnostics",
        )

    check_parser = subparsers.add_parser("check", help="Validate one-way translation setup")
    add_runtime_options(check_parser)

    run_parser = subparsers.add_parser("run", help="Run one-way Gemini Live Translation")
    add_runtime_options(run_parser)
    return parser


def _config_from_args(args: argparse.Namespace):
    return load_config(
        input_device=getattr(args, "input_device", None),
        output_device=getattr(args, "output_device", None),
        source_language=getattr(args, "source_language", None),
        target_language=getattr(args, "target_language", None),
        voice_name=getattr(args, "voice_name", None),
        echo_target_language=getattr(args, "echo_target_language", None),
        input_queue_chunks=getattr(args, "input_queue_chunks", None),
        output_queue_chunks=getattr(args, "output_queue_chunks", None),
        output_thread_queue_chunks=getattr(args, "output_thread_queue_chunks", None),
        max_playback_buffer_ms=getattr(args, "max_playback_buffer_ms", None),
        metrics_interval_sec=getattr(args, "metrics_interval_sec", None),
        auto_reconnect=getattr(args, "auto_reconnect", None),
        max_reconnects=getattr(args, "max_reconnects", None),
        debug_events=getattr(args, "debug_events", None),
    )


def devices_command() -> int:
    devices = list_devices()
    print(format_devices_table(devices))
    return 0


def check_command(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    require_api_key(config)
    input_name = require_device_name(config.input_device, "input")
    output_name = require_device_name(config.output_device, "output")

    input_device = validate_input_device(input_name)
    output_device = validate_output_device(output_name)
    chunk_size = expected_pcm16_chunk_size()
    live_config = build_live_config(
        config.target_language,
        source_language=config.source_language,
        voice_name=config.voice_name,
        echo_target_language=config.echo_target_language,
    )
    translation_config = live_translation_config_dict(live_config)

    print("GEMINI_API_KEY: present (value hidden)")
    print(
        "Input device OK: "
        f"name={input_device.name!r}, index={input_device.index}, "
        "sample_rate=16000, channels=1, dtype=int16"
    )
    print(
        "Output device OK: "
        f"name={output_device.name!r}, index={output_device.index}, "
        "sample_rate=24000, channels=1, dtype=int16"
    )
    print(f"PCM chunk OK: 100ms input chunk is {chunk_size} bytes")
    print(
        "Gemini config OK: "
        f"model={MODEL_NAME}, "
        f"source_language={config.source_language}, "
        f"target_language_code={translation_config['targetLanguageCode']}, "
        f"voice_name={_display_voice_name(config.voice_name)}, "
        f"echo_target_language={translation_config['echoTargetLanguage']}, "
        f"config={type(live_config).__name__}"
    )
    print(
        "Low latency config OK: "
        f"input_queue_chunks={config.input_queue_chunks}, "
        f"output_queue_chunks={config.output_queue_chunks}, "
        f"output_thread_queue_chunks={config.output_thread_queue_chunks}, "
        f"max_playback_buffer_ms={config.max_playback_buffer_ms}, "
        f"metrics_interval_sec={config.metrics_interval_sec:g}, "
        f"auto_reconnect={config.auto_reconnect}, "
        f"max_reconnects={config.max_reconnects}, "
        f"debug_events={config.debug_events}"
    )
    return 0


def _collect_runtime_metrics(
    *,
    config,
    audio_stats: AudioRuntimeStats,
    gemini_stats: GeminiRuntimeStats,
    input_queue: asyncio.Queue[bytes],
    output_queue: asyncio.Queue[bytes],
    audio_output: RawAudioOutput,
) -> dict[str, object]:
    audio_stats.note_input_queue_depth(input_queue.qsize())
    audio_stats.note_output_async_queue_depth(output_queue.qsize())
    audio_stats.note_output_thread_queue_depth(audio_output.thread_queue_depth())
    return {
        "config": {
            "input_queue_chunks": config.input_queue_chunks,
            "output_queue_chunks": config.output_queue_chunks,
            "output_thread_queue_chunks": config.output_thread_queue_chunks,
            "max_playback_buffer_ms": config.max_playback_buffer_ms,
            "metrics_interval_sec": config.metrics_interval_sec,
            "auto_reconnect": config.auto_reconnect,
            "max_reconnects": config.max_reconnects,
            "debug_events": config.debug_events,
        },
        "current": {
            "input_queue_depth": input_queue.qsize(),
            "output_queue_depth": output_queue.qsize(),
            "thread_queue_depth": audio_output.thread_queue_depth(),
            "playback_buffer_ms": audio_output.playback_buffer_ms(),
        },
        "audio": asdict(audio_stats),
        "gemini": asdict(gemini_stats),
    }


async def _metrics_reporter(
    *,
    interval_sec: float,
    shutdown_event: asyncio.Event,
    config,
    audio_stats: AudioRuntimeStats,
    gemini_stats: GeminiRuntimeStats,
    input_queue: asyncio.Queue[bytes],
    output_queue: asyncio.Queue[bytes],
    audio_output: RawAudioOutput,
) -> None:
    if interval_sec <= 0:
        return
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval_sec)
        except TimeoutError:
            metrics = _collect_runtime_metrics(
                config=config,
                audio_stats=audio_stats,
                gemini_stats=gemini_stats,
                input_queue=input_queue,
                output_queue=output_queue,
                audio_output=audio_output,
            )
            current = metrics["current"]
            audio = metrics["audio"]
            gemini = metrics["gemini"]
            if not isinstance(current, dict) or not isinstance(audio, dict):
                continue
            if not isinstance(gemini, dict):
                continue
            print(
                "metrics: "
                f"input_q={current['input_queue_depth']}/{config.input_queue_chunks} "
                f"output_q={current['output_queue_depth']}/{config.output_queue_chunks} "
                f"thread_q={current['thread_queue_depth']}/{config.output_thread_queue_chunks} "
                f"playback_buffer_ms={current['playback_buffer_ms']} "
                f"dropped_output={audio['output_dropped_chunks']} "
                f"input_overflows={audio['input_overflows']} "
                f"reconnects={gemini['reconnect_count']} "
                f"unsupported_events={gemini['unsupported_event_count']}"
            )


async def run_command(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    api_key = require_api_key(config)
    input_name = require_device_name(config.input_device, "input")
    output_name = require_device_name(config.output_device, "output")

    input_device = validate_input_device(input_name)
    output_device = validate_output_device(output_name)
    input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=config.input_queue_chunks)
    output_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=config.output_queue_chunks)
    shutdown_event = asyncio.Event()
    input_overflow_event = asyncio.Event()
    capture_active_event = asyncio.Event()
    stats = AudioRuntimeStats()
    gemini_stats = GeminiRuntimeStats()
    transcript_log = TranscriptLogger(
        input_device=input_device.name,
        output_device=output_device.name,
        source_language=config.source_language,
        target_language=config.target_language,
        voice_name=_display_voice_name(config.voice_name),
    )

    loop = asyncio.get_running_loop()
    audio_input = RawAudioInput(
        device_index=input_device.index,
        output_queue=input_queue,
        loop=loop,
        stats=stats,
        overflow_event=input_overflow_event,
        capture_enabled_event=capture_active_event,
    )
    audio_output = RawAudioOutput(
        device_index=output_device.index,
        input_queue=output_queue,
        stats=stats,
        thread_queue_size=config.output_thread_queue_chunks,
        max_playback_buffer_ms=config.max_playback_buffer_ms,
    )

    def request_shutdown() -> None:
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass

    error_status: str | None = None
    metrics_task: asyncio.Task[None] | None = None
    audio_input_started = False
    try:
        audio_output.start()
        metrics_task = asyncio.create_task(
            _metrics_reporter(
                interval_sec=config.metrics_interval_sec,
                shutdown_event=shutdown_event,
                config=config,
                audio_stats=stats,
                gemini_stats=gemini_stats,
                input_queue=input_queue,
                output_queue=output_queue,
                audio_output=audio_output,
            )
        )
        translation_task = asyncio.create_task(
            run_live_translation(
                api_key=api_key,
                source_language=config.source_language,
                target_language=config.target_language,
                voice_name=config.voice_name,
                echo_target_language=config.echo_target_language,
                input_audio_queue=input_queue,
                output_audio_queue=output_queue,
                transcript_log=transcript_log,
                shutdown_event=shutdown_event,
                gemini_stats=gemini_stats,
                audio_stats=stats,
                auto_reconnect=config.auto_reconnect,
                max_reconnects=config.max_reconnects,
                debug_events=config.debug_events,
                clear_stale_audio=audio_output.clear_pending,
                capture_active_event=capture_active_event,
            )
        )
        input_overflow_task = asyncio.create_task(input_overflow_event.wait())
        capture_ready_task = asyncio.create_task(capture_active_event.wait())
        try:
            while not audio_input_started:
                done, _pending = await asyncio.wait(
                    [translation_task, input_overflow_task, capture_ready_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if translation_task in done:
                    translation_task.result()
                    break
                if input_overflow_task in done and input_overflow_event.is_set():
                    shutdown_event.set()
                    error_status = stats.input_overflow_error or "input audio queue overflowed"
                    translation_task.cancel()
                    await asyncio.gather(translation_task, return_exceptions=True)
                    raise GeminiLiveError(error_status)
                if capture_ready_task in done:
                    if capture_active_event.is_set():
                        audio_input.start()
                        audio_input_started = True
                        print("Audio input capture started after Gemini session became ready.")
                        break
                    capture_ready_task = asyncio.create_task(capture_active_event.wait())

            if audio_input_started:
                done, _pending = await asyncio.wait(
                    [translation_task, input_overflow_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if input_overflow_task in done and input_overflow_event.is_set():
                    shutdown_event.set()
                    error_status = stats.input_overflow_error or "input audio queue overflowed"
                    translation_task.cancel()
                    await asyncio.gather(translation_task, return_exceptions=True)
                    raise GeminiLiveError(error_status)
                translation_task.result()
        finally:
            capture_ready_task.cancel()
            await asyncio.gather(capture_ready_task, return_exceptions=True)
            input_overflow_task.cancel()
            await asyncio.gather(input_overflow_task, return_exceptions=True)
    except KeyboardInterrupt:
        error_status = "interrupted"
        shutdown_event.set()
    except Exception as exc:
        if error_status is None:
            error_status = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        shutdown_event.set()
        capture_active_event.clear()
        if metrics_task is not None:
            metrics_task.cancel()
            await asyncio.gather(metrics_task, return_exceptions=True)
        try:
            if audio_input_started:
                audio_input.stop()
        finally:
            audio_input.close()
        await audio_output.stop()
        audio_output.close()
        metrics = _collect_runtime_metrics(
            config=config,
            audio_stats=stats,
            gemini_stats=gemini_stats,
            input_queue=input_queue,
            output_queue=output_queue,
            audio_output=audio_output,
        )
        summary = transcript_log.close(error_status=error_status, metrics=metrics)
        print(f"Run summary: {asdict(summary)}")
        if stats.callback_errors:
            print(f"Audio callback warnings: {stats.callback_errors}", file=sys.stderr)
        if stats.input_overflows:
            print(f"Input queue overflows: {stats.input_overflows}", file=sys.stderr)
        if stats.input_dropped_while_disconnected:
            print(
                "Input chunks dropped while Gemini session was disconnected: "
                f"{stats.input_dropped_while_disconnected}",
                file=sys.stderr,
            )
        if stats.input_stale_cleared_chunks:
            print(
                "Input stale chunks cleared before reconnect: "
                f"{stats.input_stale_cleared_chunks} "
                f"({stats.input_stale_cleared_bytes} bytes)",
                file=sys.stderr,
            )
        if stats.output_dropped_chunks:
            print(
                "Output dropped chunks: "
                f"{stats.output_dropped_chunks} ({stats.output_dropped_bytes} bytes)",
                file=sys.stderr,
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "devices":
            return devices_command()
        if args.command == "check":
            return check_command(args)
        if args.command == "run":
            return asyncio.run(run_command(args))
    except (ConfigError, DeviceError, GeminiLiveError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - top-level CLI must make failures explicit.
        print(f"error: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
