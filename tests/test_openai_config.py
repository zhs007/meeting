from __future__ import annotations

import pytest

from meeting_openai_translator.config import (
    DEFAULT_SAFETY_IDENTIFIER,
    ConfigError,
    load_config,
    require_api_key,
)


def test_openai_cli_env_default_priority() -> None:
    env = {
        "OPENAI_API_KEY": "placeholder-openai-key",
        "OPENAI_SAFETY_IDENTIFIER": "stable-local-id",
        "MEETING_OPENAI_INPUT_DEVICE": "Env OpenAI Input",
        "MEETING_OPENAI_OUTPUT_DEVICE": "Env OpenAI Output",
        "MEETING_OPENAI_TARGET_LANGUAGE": "fr",
    }

    config = load_config(
        input_device="CLI Input",
        output_device=None,
        target_language="en",
        env=env,
    )

    assert config.api_key == "placeholder-openai-key"
    assert config.safety_identifier == "stable-local-id"
    assert config.input_device == "CLI Input"
    assert config.output_device == "Env OpenAI Output"
    assert config.target_language == "en"


def test_openai_falls_back_to_shared_device_env_without_default_device() -> None:
    config = load_config(
        env={
            "OPENAI_API_KEY": "placeholder-openai-key",
            "MEETING_INPUT_DEVICE": "Shared Input",
            "MEETING_OUTPUT_DEVICE": "Shared Output",
        }
    )

    assert config.input_device == "Shared Input"
    assert config.output_device == "Shared Output"
    assert config.target_language == "en"


def test_openai_empty_device_env_does_not_select_default_device() -> None:
    config = load_config(
        env={
            "MEETING_OPENAI_INPUT_DEVICE": "",
            "MEETING_OPENAI_OUTPUT_DEVICE": "",
            "MEETING_INPUT_DEVICE": "",
            "MEETING_OUTPUT_DEVICE": "",
        }
    )

    assert config.input_device is None
    assert config.output_device is None


def test_missing_openai_key_error_does_not_leak_value() -> None:
    config = load_config(env={"OPENAI_API_KEY": ""})

    with pytest.raises(ConfigError) as exc_info:
        require_api_key(config)

    message = str(exc_info.value)
    assert "OPENAI_API_KEY" in message
    assert "placeholder-openai-key" not in message


def test_blank_openai_safety_identifier_uses_non_identifying_placeholder() -> None:
    config = load_config(env={"OPENAI_SAFETY_IDENTIFIER": ""})

    assert config.safety_identifier == DEFAULT_SAFETY_IDENTIFIER
    assert "@" not in config.safety_identifier


def test_openai_safety_identifier_rejects_email_like_value() -> None:
    with pytest.raises(ConfigError, match="must not contain"):
        load_config(env={"OPENAI_SAFETY_IDENTIFIER": "person@example.com"})
