from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


DEFAULT_TARGET_LANGUAGE = "en"
DEFAULT_SAFETY_IDENTIFIER = "local-user-hash-placeholder"


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    api_key: str | None
    safety_identifier: str
    input_device: str | None
    output_device: str | None
    target_language: str


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


def _safety_identifier(value: str | None) -> str:
    identifier = _blank_to_none(value) or DEFAULT_SAFETY_IDENTIFIER
    if "@" in identifier:
        raise ConfigError("OPENAI_SAFETY_IDENTIFIER must not contain directly identifying data.")
    return identifier


def load_config(
    *,
    input_device: str | None = None,
    output_device: str | None = None,
    target_language: str | None = None,
    env: Mapping[str, str] | None = None,
    dotenv_path: str | Path | None = ".env",
) -> AppConfig:
    if env is None:
        if dotenv_path is not None:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        env = os.environ

    return AppConfig(
        api_key=_env_value(env, "OPENAI_API_KEY"),
        safety_identifier=_safety_identifier(_env_value(env, "OPENAI_SAFETY_IDENTIFIER")),
        input_device=_choose(input_device, env, "MEETING_OPENAI_INPUT_DEVICE")
        or _choose(input_device, env, "MEETING_INPUT_DEVICE"),
        output_device=_choose(output_device, env, "MEETING_OPENAI_OUTPUT_DEVICE")
        or _choose(output_device, env, "MEETING_OUTPUT_DEVICE"),
        target_language=_choose(
            target_language,
            env,
            "MEETING_OPENAI_TARGET_LANGUAGE",
        )
        or _choose(target_language, env, "MEETING_TARGET_LANGUAGE", DEFAULT_TARGET_LANGUAGE)
        or DEFAULT_TARGET_LANGUAGE,
    )


def require_api_key(config: AppConfig) -> str:
    if not config.api_key:
        raise ConfigError(
            "OPENAI_API_KEY is missing; set it in the environment or .env. "
            "The key value is never printed."
        )
    return config.api_key


def require_device_name(value: str | None, kind: str) -> str:
    if value:
        return value
    raise ConfigError(
        f"{kind} device is required; pass --{kind}-device or set "
        f"MEETING_OPENAI_{kind.upper()}_DEVICE. Run "
        "`python -m meeting_openai_translator devices` to inspect exact device names."
    )
