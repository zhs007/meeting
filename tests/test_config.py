from __future__ import annotations

import pytest

from meeting_translator.config import (
    DEFAULT_INPUT_QUEUE_CHUNKS,
    DEFAULT_MAX_PLAYBACK_BUFFER_MS,
    DEFAULT_OUTPUT_QUEUE_CHUNKS,
    ConfigError,
    load_config,
    require_api_key,
)


def test_cli_env_default_priority() -> None:
    env = {
        "GEMINI_API_KEY": "placeholder-key",
        "MEETING_INPUT_DEVICE": "Env Input",
        "MEETING_OUTPUT_DEVICE": "Env Output",
        "MEETING_SOURCE_LANGUAGE": "ja",
        "MEETING_TARGET_LANGUAGE": "fr",
        "MEETING_VOICE_NAME": "Puck",
        "MEETING_ECHO_TARGET_LANGUAGE": "true",
    }

    config = load_config(
        input_device="CLI Input",
        output_device=None,
        source_language="zh-CN",
        target_language="en",
        voice_name="Kore",
        echo_target_language=False,
        env=env,
    )

    assert config.input_device == "CLI Input"
    assert config.output_device == "Env Output"
    assert config.source_language == "zh-CN"
    assert config.target_language == "en"
    assert config.voice_name == "Kore"
    assert config.echo_target_language is False
    assert config.input_queue_chunks == DEFAULT_INPUT_QUEUE_CHUNKS
    assert config.output_queue_chunks == DEFAULT_OUTPUT_QUEUE_CHUNKS
    assert config.max_playback_buffer_ms == DEFAULT_MAX_PLAYBACK_BUFFER_MS


def test_empty_device_env_does_not_select_default_device() -> None:
    config = load_config(env={"MEETING_INPUT_DEVICE": "", "MEETING_OUTPUT_DEVICE": ""})

    assert config.input_device is None
    assert config.output_device is None
    assert config.source_language == "zh-CN"
    assert config.target_language == "en"
    assert config.voice_name == "Kore"


def test_dotenv_loads_when_environment_is_absent(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "GEMINI_API_KEY=placeholder-key\n"
        "MEETING_INPUT_DEVICE=Dotenv Input\n"
        "MEETING_OUTPUT_DEVICE=Dotenv Output\n"
        "MEETING_SOURCE_LANGUAGE=ko\n"
        "MEETING_TARGET_LANGUAGE=ja\n"
        "MEETING_VOICE_NAME=Charon\n",
        encoding="utf-8",
    )
    for name in (
        "GEMINI_API_KEY",
        "MEETING_INPUT_DEVICE",
        "MEETING_OUTPUT_DEVICE",
        "MEETING_SOURCE_LANGUAGE",
        "MEETING_TARGET_LANGUAGE",
        "MEETING_VOICE_NAME",
        "MEETING_ECHO_TARGET_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config(dotenv_path=dotenv)

    assert config.api_key == "placeholder-key"
    assert config.input_device == "Dotenv Input"
    assert config.output_device == "Dotenv Output"
    assert config.source_language == "ko"
    assert config.target_language == "ja"
    assert config.voice_name == "Charon"


def test_low_latency_config_cli_env_dotenv_default_priority(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "GEMINI_API_KEY=placeholder-key\n"
        "MEETING_INPUT_QUEUE_CHUNKS=5\n"
        "MEETING_OUTPUT_QUEUE_CHUNKS=6\n"
        "MEETING_OUTPUT_THREAD_QUEUE_CHUNKS=7\n"
        "MEETING_MAX_PLAYBACK_BUFFER_MS=600\n"
        "MEETING_METRICS_INTERVAL_SEC=3.5\n"
        "MEETING_AUTO_RECONNECT=false\n"
        "MEETING_MAX_RECONNECTS=2\n"
        "MEETING_DEBUG_EVENTS=true\n",
        encoding="utf-8",
    )
    names = (
        "GEMINI_API_KEY",
        "MEETING_INPUT_QUEUE_CHUNKS",
        "MEETING_OUTPUT_QUEUE_CHUNKS",
        "MEETING_OUTPUT_THREAD_QUEUE_CHUNKS",
        "MEETING_MAX_PLAYBACK_BUFFER_MS",
        "MEETING_METRICS_INTERVAL_SEC",
        "MEETING_AUTO_RECONNECT",
        "MEETING_MAX_RECONNECTS",
        "MEETING_DEBUG_EVENTS",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MEETING_INPUT_QUEUE_CHUNKS", "9")

    config = load_config(output_queue_chunks=11, dotenv_path=dotenv)

    assert config.input_queue_chunks == 9
    assert config.output_queue_chunks == 11
    assert config.output_thread_queue_chunks == 7
    assert config.max_playback_buffer_ms == 600
    assert config.metrics_interval_sec == 3.5
    assert config.auto_reconnect is False
    assert config.max_reconnects == 2
    assert config.debug_events is True


def test_low_latency_config_rejects_non_positive_queue_size() -> None:
    with pytest.raises(ConfigError, match="MEETING_OUTPUT_QUEUE_CHUNKS"):
        load_config(env={"MEETING_OUTPUT_QUEUE_CHUNKS": "0"})


def test_low_latency_config_rejects_invalid_boolean() -> None:
    with pytest.raises(ConfigError, match="MEETING_AUTO_RECONNECT"):
        load_config(env={"MEETING_AUTO_RECONNECT": "maybe"})


def test_missing_gemini_key_error_does_not_leak_secret_name_value() -> None:
    config = load_config(env={"GEMINI_API_KEY": ""})

    with pytest.raises(ConfigError) as exc_info:
        require_api_key(config)

    message = str(exc_info.value)
    assert "GEMINI_API_KEY" in message
    assert "placeholder-key" not in message
