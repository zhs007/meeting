from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from meeting_translator.pcm import (
    INPUT_CHANNELS,
    INPUT_DTYPE,
    INPUT_SAMPLE_RATE,
    OUTPUT_CHANNELS,
    OUTPUT_DTYPE,
    OUTPUT_SAMPLE_RATE,
)


class SoundDeviceModule(Protocol):
    def query_devices(self) -> Any: ...

    def check_input_settings(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
    ) -> None: ...

    def check_output_settings(
        self,
        *,
        device: int,
        channels: int,
        samplerate: int,
        dtype: str,
    ) -> None: ...


class DeviceError(RuntimeError):
    """Raised when an exact audio device or required audio format is unavailable."""


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float

    @property
    def can_input(self) -> bool:
        return self.max_input_channels > 0

    @property
    def can_output(self) -> bool:
        return self.max_output_channels > 0


def _import_sounddevice() -> SoundDeviceModule:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise DeviceError(
            "sounddevice is required for audio device inspection; install requirements.txt first."
        ) from exc
    return sd


def normalize_device_rows(raw_devices: Iterable[dict[str, Any]]) -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    for index, device in enumerate(raw_devices):
        devices.append(
            DeviceInfo(
                index=index,
                name=str(device.get("name", "")),
                max_input_channels=int(device.get("max_input_channels", 0)),
                max_output_channels=int(device.get("max_output_channels", 0)),
                default_samplerate=float(device.get("default_samplerate", 0.0)),
            )
        )
    return devices


def list_devices(sd_module: SoundDeviceModule | None = None) -> list[DeviceInfo]:
    sd = sd_module or _import_sounddevice()
    return normalize_device_rows(sd.query_devices())


def format_devices_table(devices: Iterable[DeviceInfo]) -> str:
    lines = [
        "index | input | output | default_rate | can_input | can_output | name",
        "----- | ----- | ------ | ------------ | --------- | ---------- | ----",
    ]
    for device in devices:
        lines.append(
            f"{device.index:>5} | "
            f"{device.max_input_channels:>5} | "
            f"{device.max_output_channels:>6} | "
            f"{device.default_samplerate:>12.0f} | "
            f"{'yes' if device.can_input else 'no':>9} | "
            f"{'yes' if device.can_output else 'no':>10} | "
            f"{device.name}"
        )
    return "\n".join(lines)


def select_device_by_exact_name(
    devices: Iterable[DeviceInfo],
    *,
    name: str | None,
    kind: str,
) -> DeviceInfo:
    if not name:
        raise DeviceError(
            f"{kind} device name is required; no default audio device is selected implicitly."
        )

    matches = [device for device in devices if device.name == name]
    if not matches:
        raise DeviceError(
            f"{kind} device {name!r} was not found. Run `python -m meeting_translator devices` "
            "and pass the exact device name."
        )

    capable = [
        device
        for device in matches
        if (device.can_input if kind == "input" else device.can_output)
    ]
    if not capable:
        raise DeviceError(f"{kind} device {name!r} exists but has no {kind} channels.")
    if len(capable) > 1:
        indexes = ", ".join(str(device.index) for device in capable)
        raise DeviceError(
            f"{kind} device name {name!r} matches multiple devices at indexes {indexes}; "
            "rename the device or remove the duplicate before running."
        )
    return capable[0]


def validate_input_device(
    name: str,
    *,
    sd_module: SoundDeviceModule | None = None,
) -> DeviceInfo:
    sd = sd_module or _import_sounddevice()
    device = select_device_by_exact_name(list_devices(sd), name=name, kind="input")
    try:
        sd.check_input_settings(
            device=device.index,
            channels=INPUT_CHANNELS,
            samplerate=INPUT_SAMPLE_RATE,
            dtype=INPUT_DTYPE,
        )
    except Exception as exc:  # noqa: BLE001 - sounddevice raises host-specific exceptions.
        raise DeviceError(
            "input device cannot be opened with "
            f"name={device.name!r}, index={device.index}, sample_rate={INPUT_SAMPLE_RATE}, "
            f"channels={INPUT_CHANNELS}, dtype={INPUT_DTYPE}: {exc}"
        ) from exc
    return device


def validate_output_device(
    name: str,
    *,
    sd_module: SoundDeviceModule | None = None,
) -> DeviceInfo:
    sd = sd_module or _import_sounddevice()
    device = select_device_by_exact_name(list_devices(sd), name=name, kind="output")
    try:
        sd.check_output_settings(
            device=device.index,
            channels=OUTPUT_CHANNELS,
            samplerate=OUTPUT_SAMPLE_RATE,
            dtype=OUTPUT_DTYPE,
        )
    except Exception as exc:  # noqa: BLE001 - sounddevice raises host-specific exceptions.
        raise DeviceError(
            "output device cannot be opened with "
            f"name={device.name!r}, index={device.index}, sample_rate={OUTPUT_SAMPLE_RATE}, "
            f"channels={OUTPUT_CHANNELS}, dtype={OUTPUT_DTYPE}: {exc}"
        ) from exc
    return device
