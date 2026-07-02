from __future__ import annotations

import pytest

from meeting_translator.pcm import (
    PCMError,
    expected_pcm16_chunk_size,
    pcm16_from_base64,
    pcm16_to_base64,
    validate_input_chunk,
)


def test_16khz_100ms_mono_pcm16_chunk_is_3200_bytes() -> None:
    assert expected_pcm16_chunk_size() == 3_200
    chunk = b"\x00\x01" * 1_600

    assert validate_input_chunk(chunk) == chunk


def test_base64_roundtrip_keeps_pcm_bytes_unchanged() -> None:
    chunk = bytes(range(128)) * 25

    assert pcm16_from_base64(pcm16_to_base64(chunk)) == chunk


def test_non_100ms_chunk_fails_before_send() -> None:
    with pytest.raises(PCMError, match="exactly 3200 bytes"):
        validate_input_chunk(b"\x00" * 3_198)
