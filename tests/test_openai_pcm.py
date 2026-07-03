from __future__ import annotations

import pytest

from meeting_openai_translator.pcm import (
    PCMError,
    expected_pcm16_chunk_size,
    pcm16_from_base64,
    pcm16_to_base64,
    validate_input_chunk,
)


def test_openai_24khz_100ms_mono_pcm16_chunk_is_4800_bytes() -> None:
    assert expected_pcm16_chunk_size() == 4_800
    chunk = b"\x00\x01" * 2_400

    assert validate_input_chunk(chunk) == chunk


def test_openai_base64_roundtrip_keeps_pcm_bytes_unchanged() -> None:
    chunk = bytes(range(128)) * 38

    assert pcm16_from_base64(pcm16_to_base64(chunk)) == chunk


def test_openai_non_100ms_chunk_fails_before_send() -> None:
    with pytest.raises(PCMError, match="exactly 4800 bytes"):
        validate_input_chunk(b"\x00" * 4_798)
