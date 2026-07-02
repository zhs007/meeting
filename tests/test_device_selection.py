from __future__ import annotations

import pytest

from meeting_translator.audio_devices import (
    DeviceError,
    normalize_device_rows,
    select_device_by_exact_name,
)


DEVICES = normalize_device_rows(
    [
        {
            "name": "AirPods 4",
            "max_input_channels": 1,
            "max_output_channels": 0,
            "default_samplerate": 48_000,
        },
        {
            "name": "BlackHole 2ch",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "default_samplerate": 48_000,
        },
    ]
)


def test_exact_input_device_name_match() -> None:
    device = select_device_by_exact_name(DEVICES, name="AirPods 4", kind="input")

    assert device.name == "AirPods 4"
    assert device.index == 0


def test_missing_input_device_fails_explicitly() -> None:
    with pytest.raises(DeviceError, match="input device 'Missing Mic' was not found"):
        select_device_by_exact_name(DEVICES, name="Missing Mic", kind="input")


def test_missing_output_device_fails_explicitly() -> None:
    with pytest.raises(DeviceError, match="output device 'Missing Speaker' was not found"):
        select_device_by_exact_name(DEVICES, name="Missing Speaker", kind="output")


def test_no_implicit_default_device_selection() -> None:
    with pytest.raises(DeviceError, match="no default audio device is selected implicitly"):
        select_device_by_exact_name(DEVICES, name=None, kind="input")
