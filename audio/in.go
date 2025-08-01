package audio

import (
	"github.com/gordonklaus/portaudio"
)

type In struct {
	stream *portaudio.Stream
	chanIn chan []int16
}

func (in *In) processAudio(inBuf []float32) {
	// 创建一个 int16 的缓冲区来存放转换后的 PCM 数据
	pcmData := make([]int16, len(inBuf))

	// 将 float32 转换为 int16
	for i, sample := range inBuf {
		// 将 -1.0 到 1.0 的 float32 映射到 -32767 到 32767 的 int16
		pcmData[i] = int16(sample * 32767.0)
	}

	in.chanIn <- pcmData
}

func NewIn(sampleRate int, channels int, chanIn chan []int16) (*In, error) {
	in := &In{
		chanIn: chanIn,
	}

	stream, err := portaudio.OpenDefaultStream(channels, 0, float64(sampleRate), 0, in.processAudio)
	if err != nil {
		return nil, err
	}
	in.stream = stream

	if err := in.stream.Start(); err != nil {
		return nil, err
	}

	return in, nil
}
