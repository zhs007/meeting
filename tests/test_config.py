from __future__ import annotations

import pytest

from meeting_translator.config import ConfigError, load_config, require_api_key


def test_cli_env_default_priority() -> None:
    env = {
        "GEMINI_API_KEY": "placeholder-key",
        "MEETING_INPUT_DEVICE": "Env Input",
        "MEETING_OUTPUT_DEVICE": "Env Output",
        "MEETING_TARGET_LANGUAGE": "fr",
        "MEETING_ECHO_TARGET_LANGUAGE": "true",
    }

    config = load_config(
        input_device="CLI Input",
        output_device=None,
        target_language="en",
        echo_target_language=False,
        env=env,
    )

    assert config.input_device == "CLI Input"
    assert config.output_device == "Env Output"
    assert config.target_language == "en"
    assert config.echo_target_language is False


def test_empty_device_env_does_not_select_default_device() -> None:
    config = load_config(env={"MEETING_INPUT_DEVICE": "", "MEETING_OUTPUT_DEVICE": ""})

    assert config.input_device is None
    assert config.output_device is None
    assert config.target_language == "en"


def test_dotenv_loads_when_environment_is_absent(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "GEMINI_API_KEY=placeholder-key\n"
        "MEETING_INPUT_DEVICE=Dotenv Input\n"
        "MEETING_OUTPUT_DEVICE=Dotenv Output\n"
        "MEETING_TARGET_LANGUAGE=ja\n",
        encoding="utf-8",
    )
    for name in (
        "GEMINI_API_KEY",
        "MEETING_INPUT_DEVICE",
        "MEETING_OUTPUT_DEVICE",
        "MEETING_TARGET_LANGUAGE",
        "MEETING_ECHO_TARGET_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(dotenv_path=dotenv)

    assert config.api_key == "placeholder-key"
    assert config.input_device == "Dotenv Input"
    assert config.output_device == "Dotenv Output"
    assert config.target_language == "ja"


def test_missing_gemini_key_error_does_not_leak_secret_name_value() -> None:
    config = load_config(env={"GEMINI_API_KEY": ""})

    with pytest.raises(ConfigError) as exc_info:
        require_api_key(config)

    message = str(exc_info.value)
    assert "GEMINI_API_KEY" in message
    assert "placeholder-key" not in message
