package audio

import (
	"log/slog"
	"time"

	"github.com/gordonklaus/portaudio"
)

func Init(sampleRate int, channels int, bitDepth int, duration time.Duration, chanIn chan []int16) (*In, *Out, error) {
	if err := portaudio.Initialize(); err != nil {
		slog.Error("PortAudio initialize failed", "error", err)

		return nil, nil, err
	}

	in, err := NewIn(sampleRate, channels, chanIn)
	if err != nil {
		slog.Error("NewIn failed", "error", err)

		return nil, nil, err
	}

	out, err := NewOut(sampleRate, channels, bitDepth, duration)
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
