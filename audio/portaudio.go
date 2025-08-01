package audio

import (
	"log/slog"
	"time"

	"github.com/gordonklaus/portaudio"
)

func selectDevice(devices []*portaudio.DeviceInfo, deviceName string, isInput bool) *portaudio.DeviceInfo {
	for _, device := range devices {
		if isInput && device.MaxInputChannels > 0 && device.Name == deviceName {
			return device
		} else if !isInput && device.MaxOutputChannels > 0 && device.Name == deviceName {
			return device
		}
	}

	return nil
}

func Init(inDeviceName string, outDeviceName string, sampleRate int, channels int, bitDepth int, duration time.Duration, chanIn chan []int16) (*In, *Out, error) {
	if err := portaudio.Initialize(); err != nil {
		slog.Error("PortAudio initialize failed", "error", err)

		return nil, nil, err
	}

	devices, err := portaudio.Devices()
	if err != nil {
		slog.Error("PortAudio get devices failed", "error", err)
	}

	inDevice := selectDevice(devices, inDeviceName, true)
	if inDevice == nil {
		slog.Error("PortAudio input device not found", "name", inDeviceName)

		return nil, nil, err
	}

	in, err := NewIn(inDevice, sampleRate, channels, bitDepth, duration, chanIn)
	if err != nil {
		slog.Error("NewIn failed", "error", err)

		return nil, nil, err
	}

	outDevice := selectDevice(devices, outDeviceName, false)
	if outDevice == nil {
		slog.Error("PortAudio output device not found", "name", outDeviceName)

		return nil, nil, err
	}

	out, err := NewOut(outDevice, sampleRate, channels, bitDepth, duration)
	if err != nil {
		slog.Error("NewOut failed", "error", err)

		return nil, nil, err
	}

	return in, out, nil
}

func Terminate() {
	if err := portaudio.Terminate(); err != nil {
		slog.Error("PortAudio terminate failed", "error", err)
	}
}
