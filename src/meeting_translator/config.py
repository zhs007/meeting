from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


DEFAULT_TARGET_LANGUAGE = "en"
DEFAULT_ECHO_TARGET_LANGUAGE = False


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    api_key: str | None
    input_device: str | None
    output_device: str | None
    target_language: str
    echo_target_language: bool


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


def parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean value, got {value!r}")


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


def load_config(
    *,
    input_device: str | None = None,
    output_device: str | None = None,
    target_language: str | None = None,
    echo_target_language: bool | None = None,
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
        target_language=_choose(
            target_language,
            env,
            "MEETING_TARGET_LANGUAGE",
            DEFAULT_TARGET_LANGUAGE,
        )
        or DEFAULT_TARGET_LANGUAGE,
        echo_target_language=_choose_bool(
            echo_target_language,
            env,
            "MEETING_ECHO_TARGET_LANGUAGE",
            DEFAULT_ECHO_TARGET_LANGUAGE,
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
