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
    MODEL_NAME,
    build_live_config,
    live_translation_config_dict,
    run_live_translation,
)
from meeting_translator.pcm import expected_pcm16_chunk_size
from meeting_translator.transcript_log import TranscriptLogger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting_translator")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="List local audio devices")

    def add_runtime_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--input-device", default=None)
        command.add_argument("--output-device", default=None)
        command.add_argument("--target-language", default=None)
        command.add_argument(
            "--echo-target-language",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Echo audio already spoken in the target language",
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
        target_language=getattr(args, "target_language", None),
        echo_target_language=getattr(args, "echo_target_language", None),
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
        f"target_language_code={translation_config['targetLanguageCode']}, "
        f"echo_target_language={translation_config['echoTargetLanguage']}, "
        f"config={type(live_config).__name__}"
    )
    return 0


async def run_command(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    api_key = require_api_key(config)
    input_name = require_device_name(config.input_device, "input")
    output_name = require_device_name(config.output_device, "output")

    input_device = validate_input_device(input_name)
    output_device = validate_output_device(output_name)
    input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
    output_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
    shutdown_event = asyncio.Event()
    stats = AudioRuntimeStats()
    transcript_log = TranscriptLogger(
        input_device=input_device.name,
        output_device=output_device.name,
        target_language=config.target_language,
    )

    loop = asyncio.get_running_loop()
    audio_input = RawAudioInput(
        device_index=input_device.index,
        output_queue=input_queue,
        loop=loop,
        stats=stats,
    )
    audio_output = RawAudioOutput(
        device_index=output_device.index,
        input_queue=output_queue,
        stats=stats,
    )

    def request_shutdown() -> None:
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass

    error_status: str | None = None
    try:
        audio_input.start()
        audio_output.start()
        await run_live_translation(
            api_key=api_key,
            target_language=config.target_language,
            echo_target_language=config.echo_target_language,
            input_audio_queue=input_queue,
            output_audio_queue=output_queue,
            transcript_log=transcript_log,
            shutdown_event=shutdown_event,
        )
    except KeyboardInterrupt:
        error_status = "interrupted"
        shutdown_event.set()
    except Exception as exc:
        error_status = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        shutdown_event.set()
        try:
            audio_input.stop()
        finally:
            audio_input.close()
        await audio_output.stop()
        audio_output.close()
        summary = transcript_log.close(error_status=error_status)
        print(f"Run summary: {asdict(summary)}")
        if stats.callback_errors:
            print(f"Audio callback warnings: {stats.callback_errors}", file=sys.stderr)
        if stats.input_overflows:
            print(f"Input queue overflows: {stats.input_overflows}", file=sys.stderr)
        if stats.output_dropped_chunks:
            print(f"Output dropped chunks: {stats.output_dropped_chunks}", file=sys.stderr)
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
