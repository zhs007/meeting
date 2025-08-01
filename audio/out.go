package audio

import (
	"bytes"
	"sync"
	"time"

	"log/slog"

	"github.com/gordonklaus/portaudio"
)

type Out struct {
	stream          *portaudio.Stream
	chanBuffer      chan []byte
	buffer          *bytes.Buffer
	mux             sync.Mutex
	bytesPerBuffer  int
	framesPerBuffer int
}

func (o *Out) Write(data []byte) error {
	if len(data) == 0 {
		return nil
	}

	o.chanBuffer <- data

	return nil
}

func (o *Out) onWrite() {
	for {
		data, ok := <-o.chanBuffer
		if !ok {
			return
		}

		o.mux.Lock()
		if _, err := o.buffer.Write(data); err != nil {
			o.mux.Unlock()
			continue
		}
		o.mux.Unlock()
	}
}

func (o *Out) processAudio(out []float32) {
	o.mux.Lock()
	defer o.mux.Unlock()

	for i := 0; i < o.framesPerBuffer; i++ {
		val, err := ReadInt16(o.buffer)
		if err != nil {
			for j := i; j < o.framesPerBuffer; j++ {
				out[j] = 0.0
			}

			slog.Info("ReadInt16 ", "len", i)

			return
		}

		out[i] = float32(val) / 32768.0
	}

	slog.Info("ReadInt16 ", "len", o.framesPerBuffer, "buffer_len", o.buffer.Len())
}

func NewOut(device *portaudio.DeviceInfo, sampleRate int, channels int, bitDepth int, duration time.Duration) (*Out, error) {
	framesPerBuffer := int(float64(sampleRate) * duration.Seconds())
	bytesPerSample := bitDepth / 8
	bytesPerBuffer := framesPerBuffer * channels * bytesPerSample

	out := &Out{
		chanBuffer:      make(chan []byte, 128),
		buffer:          bytes.NewBuffer(nil),
		bytesPerBuffer:  bytesPerBuffer,
		framesPerBuffer: framesPerBuffer,
	}

	stream, err := portaudio.OpenStream(portaudio.StreamParameters{
		Output:          portaudio.StreamDeviceParameters{Device: device, Channels: channels},
		SampleRate:      float64(sampleRate),
		FramesPerBuffer: framesPerBuffer,
	}, out.processAudio)
	// stream, err := portaudio.OpenDefaultStream(0, channels, float64(sampleRate), framesPerBuffer, out.processAudio)
	if err != nil {
		return nil, err
	}
	out.stream = stream

	if err := out.stream.Start(); err != nil {
		return nil, err
	}

	go out.onWrite()

	return out, nil
}
