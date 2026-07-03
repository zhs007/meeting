from __future__ import annotations

import base64


INPUT_SAMPLE_RATE = 24_000
INPUT_CHANNELS = 1
INPUT_DTYPE = "int16"
INPUT_CHUNK_MS = 100
INPUT_SAMPLES_PER_CHUNK = 2_400

OUTPUT_SAMPLE_RATE = 24_000
OUTPUT_CHANNELS = 1
OUTPUT_DTYPE = "int16"

PCM16_BYTES_PER_SAMPLE = 2


class PCMError(ValueError):
    """Raised when raw PCM bytes do not match the OpenAI wire format."""


def expected_pcm16_chunk_size(
    *,
    sample_rate: int = INPUT_SAMPLE_RATE,
    channels: int = INPUT_CHANNELS,
    chunk_ms: int = INPUT_CHUNK_MS,
) -> int:
    samples = sample_rate * chunk_ms // 1000
    return samples * channels * PCM16_BYTES_PER_SAMPLE


def validate_input_chunk(chunk: bytes) -> bytes:
    expected = expected_pcm16_chunk_size()
    if len(chunk) != expected:
        raise PCMError(
            "OpenAI Realtime Translation input chunk must be exactly "
            f"{expected} bytes for 24kHz mono PCM16 100ms audio; got {len(chunk)} bytes."
        )
    return chunk


def pcm16_to_base64(chunk: bytes) -> str:
    return base64.b64encode(chunk).decode("ascii")


def pcm16_from_base64(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise PCMError("invalid base64 PCM payload") from exc
