from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


DEFAULT_TARGET_LANGUAGE = "en"
DEFAULT_SOURCE_LANGUAGE = "zh-CN"
DEFAULT_VOICE_NAME = "Kore"
AUTO_VOICE_NAME = "auto"
DEFAULT_ECHO_TARGET_LANGUAGE = False
DEFAULT_INPUT_QUEUE_CHUNKS = 8
DEFAULT_OUTPUT_QUEUE_CHUNKS = 8
DEFAULT_OUTPUT_THREAD_QUEUE_CHUNKS = 8
DEFAULT_MAX_PLAYBACK_BUFFER_MS = 800
DEFAULT_METRICS_INTERVAL_SEC = 10.0
DEFAULT_AUTO_RECONNECT = True
DEFAULT_MAX_RECONNECTS = 0
DEFAULT_DEBUG_EVENTS = False


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    api_key: str | None
    input_device: str | None
    output_device: str | None
    source_language: str
    target_language: str
    voice_name: str | None
    echo_target_language: bool
    input_queue_chunks: int
    output_queue_chunks: int
    output_thread_queue_chunks: int
    max_playback_buffer_ms: int
    metrics_interval_sec: float
    auto_reconnect: bool
    max_reconnects: int
    debug_events: bool


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_value(env: Mapping[str, str], name: str) -> str | None:
    return _blank_to_none(env.get(name))


def _choose(
    cli_value: str | None,
    env: Mapping[str, str],
    env_name: str,
    default: str | None = None,
) -> str | None:
    cleaned_cli = _blank_to_none(cli_value)
    if cleaned_cli is not None:
        return cleaned_cli
    env_config = _env_value(env, env_name)
    if env_config is not None:
        return env_config
    return default


def _parse_voice_name(value: str | None) -> str | None:
    cleaned = _blank_to_none(value)
    if cleaned is None:
        return DEFAULT_VOICE_NAME
    if cleaned.lower() == AUTO_VOICE_NAME:
        return None
    return cleaned


def parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean value, got {value!r}")


def _parse_positive_int(value: int | str, name: str) -> int:
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer, got {value!r}") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value!r}")
    return parsed


def _parse_non_negative_int(value: int | str, name: str) -> int:
    try:
        parsed = int(str(value).strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a non-negative integer, got {value!r}") from exc
    if parsed < 0:
        raise ConfigError(f"{name} must be a non-negative integer, got {value!r}")
    return parsed


def _parse_non_negative_float(value: float | str, name: str) -> float:
    try:
        parsed = float(str(value).strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a non-negative number, got {value!r}") from exc
    if parsed < 0:
        raise ConfigError(f"{name} must be a non-negative number, got {value!r}")
    return parsed


def _choose_bool(
    cli_value: bool | None,
    env: Mapping[str, str],
    env_name: str,
    default: bool,
) -> bool:
    if cli_value is not None:
        return cli_value
    env_config = _env_value(env, env_name)
    if env_config is not None:
        return parse_bool(env_config, env_name)
    return default


def _choose_positive_int(
    cli_value: int | str | None,
    env: Mapping[str, str],
    env_name: str,
    default: int,
) -> int:
    if cli_value is not None:
        return _parse_positive_int(cli_value, env_name)
    env_config = _env_value(env, env_name)
    if env_config is not None:
        return _parse_positive_int(env_config, env_name)
    return default


def _choose_non_negative_int(
    cli_value: int | str | None,
    env: Mapping[str, str],
    env_name: str,
    default: int,
) -> int:
    if cli_value is not None:
        return _parse_non_negative_int(cli_value, env_name)
    env_config = _env_value(env, env_name)
    if env_config is not None:
        return _parse_non_negative_int(env_config, env_name)
    return default


def _choose_non_negative_float(
    cli_value: float | str | None,
    env: Mapping[str, str],
    env_name: str,
    default: float,
) -> float:
    if cli_value is not None:
        return _parse_non_negative_float(cli_value, env_name)
    env_config = _env_value(env, env_name)
    if env_config is not None:
        return _parse_non_negative_float(env_config, env_name)
    return default


def load_config(
    *,
    input_device: str | None = None,
    output_device: str | None = None,
    source_language: str | None = None,
    target_language: str | None = None,
    voice_name: str | None = None,
    echo_target_language: bool | None = None,
    input_queue_chunks: int | str | None = None,
    output_queue_chunks: int | str | None = None,
    output_thread_queue_chunks: int | str | None = None,
    max_playback_buffer_ms: int | str | None = None,
    metrics_interval_sec: float | str | None = None,
    auto_reconnect: bool | None = None,
    max_reconnects: int | str | None = None,
    debug_events: bool | None = None,
    env: Mapping[str, str] | None = None,
    dotenv_path: str | Path | None = ".env",
) -> AppConfig:
    if env is None:
        if dotenv_path is not None:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        env = os.environ

    return AppConfig(
        api_key=_env_value(env, "GEMINI_API_KEY"),
        input_device=_choose(input_device, env, "MEETING_INPUT_DEVICE"),
        output_device=_choose(output_device, env, "MEETING_OUTPUT_DEVICE"),
        source_language=_choose(
            source_language,
            env,
            "MEETING_SOURCE_LANGUAGE",
            DEFAULT_SOURCE_LANGUAGE,
        )
        or DEFAULT_SOURCE_LANGUAGE,
        target_language=_choose(
            target_language,
            env,
            "MEETING_TARGET_LANGUAGE",
            DEFAULT_TARGET_LANGUAGE,
        )
        or DEFAULT_TARGET_LANGUAGE,
        voice_name=_parse_voice_name(
            _choose(
                voice_name,
                env,
                "MEETING_VOICE_NAME",
                DEFAULT_VOICE_NAME,
            )
        ),
        echo_target_language=_choose_bool(
            echo_target_language,
            env,
            "MEETING_ECHO_TARGET_LANGUAGE",
            DEFAULT_ECHO_TARGET_LANGUAGE,
        ),
        input_queue_chunks=_choose_positive_int(
            input_queue_chunks,
            env,
            "MEETING_INPUT_QUEUE_CHUNKS",
            DEFAULT_INPUT_QUEUE_CHUNKS,
        ),
        output_queue_chunks=_choose_positive_int(
            output_queue_chunks,
            env,
            "MEETING_OUTPUT_QUEUE_CHUNKS",
            DEFAULT_OUTPUT_QUEUE_CHUNKS,
        ),
        output_thread_queue_chunks=_choose_positive_int(
            output_thread_queue_chunks,
            env,
            "MEETING_OUTPUT_THREAD_QUEUE_CHUNKS",
            DEFAULT_OUTPUT_THREAD_QUEUE_CHUNKS,
        ),
        max_playback_buffer_ms=_choose_positive_int(
            max_playback_buffer_ms,
            env,
            "MEETING_MAX_PLAYBACK_BUFFER_MS",
            DEFAULT_MAX_PLAYBACK_BUFFER_MS,
        ),
        metrics_interval_sec=_choose_non_negative_float(
            metrics_interval_sec,
            env,
            "MEETING_METRICS_INTERVAL_SEC",
            DEFAULT_METRICS_INTERVAL_SEC,
        ),
        auto_reconnect=_choose_bool(
            auto_reconnect,
            env,
            "MEETING_AUTO_RECONNECT",
            DEFAULT_AUTO_RECONNECT,
        ),
        max_reconnects=_choose_non_negative_int(
            max_reconnects,
            env,
            "MEETING_MAX_RECONNECTS",
            DEFAULT_MAX_RECONNECTS,
        ),
        debug_events=_choose_bool(
            debug_events,
            env,
            "MEETING_DEBUG_EVENTS",
            DEFAULT_DEBUG_EVENTS,
        ),
    )


def require_api_key(config: AppConfig) -> str:
    if not config.api_key:
        raise ConfigError(
            "GEMINI_API_KEY is required; set it in the environment or .env. "
            "The key value is never printed."
        )
    return config.api_key


def require_device_name(value: str | None, kind: str) -> str:
    if value:
        return value
    raise ConfigError(
        f"{kind} device is required; pass --{kind}-device or set "
        f"MEETING_{kind.upper()}_DEVICE. Run `python -m meeting_translator devices` "
        "to inspect exact device names."
    )
