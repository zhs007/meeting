package audio

import (
	"encoding/binary"
	"fmt"
	"io"
	"log/slog"
	"os"
	"time"

	"github.com/gordonklaus/portaudio"
)

func Init() (*Out, error) {
	if err := portaudio.Initialize(); err != nil {
		slog.Error("PortAudio initialize failed", "error", err)

		return nil, err
	}

	out, err := NewOut(16000, 1, 16, 80*time.Millisecond)
	if err != nil {
		slog.Error("NewOut failed", "error", err)

		return nil, err
	}

	return out, nil
}

func Terminate() {
	if err := portaudio.Terminate(); err != nil {
		slog.Error("PortAudio terminate failed", "error", err)
	}
}

// WavHeader 结构体用于存储 WAV 文件的头部信息
type WavHeader struct {
	RiffMark      [4]byte
	FileSize      uint32
	WaveMark      [4]byte
	FmtMark       [4]byte
	FmtSize       uint32
	AudioFormat   uint16
	NumChannels   uint16
	SampleRate    uint32
	ByteRate      uint32
	BlockAlign    uint16
	BitsPerSample uint16
}

func main() {
	// --- 配置参数 ---
	const (
		// 将这里的文件名改为你的 16k 音频文件
		wavFile          = "test_audio.wav"
		targetSampleRate = 16000 // <<-- 主要修改点
		targetChannels   = 1
		targetBitDepth   = 16
		chunkDuration    = 80 * time.Millisecond
	)

	if err := playWav(wavFile, targetSampleRate, targetChannels, targetBitDepth, chunkDuration); err != nil {
		fmt.Fprintf(os.Stderr, "错误: %v\n", err)
		os.Exit(1)
	}
}

func playWav(fileName string, sampleRate, channels, bitDepth int, duration time.Duration) error {
	fmt.Printf("准备播放 '%s'\n", fileName)
	fmt.Printf("要求格式: %d Hz, %d-bit, %d 声道, %v 的数据块\n", sampleRate, bitDepth, channels, duration)

	// 计算缓冲区大小 (根据新的采样率自动计算)
	framesPerBuffer := int(float64(sampleRate) * duration.Seconds())
	bytesPerSample := bitDepth / 8
	bytesPerBuffer := framesPerBuffer * channels * bytesPerSample
	fmt.Printf("计算得出: 每缓冲区 %d 帧, 每次读取 %d 字节\n", framesPerBuffer, bytesPerBuffer)

	// --- 文件和头部处理 ---
	file, err := os.Open(fileName)
	if err != nil {
		return fmt.Errorf("无法打开文件: %w", err)
	}
	defer file.Close()

	var header WavHeader
	if err := binary.Read(file, binary.LittleEndian, &header); err != nil {
		return fmt.Errorf("读取 WAV 头部失败: %w", err)
	}

	// 验证音频格式
	if string(header.RiffMark[:]) != "RIFF" || string(header.WaveMark[:]) != "WAVE" {
		return fmt.Errorf("文件不是有效的 WAV 格式")
	}
	if header.AudioFormat != 1 {
		return fmt.Errorf("不支持的音频格式 (需要 PCM, 文件格式为 %d)", header.AudioFormat)
	}
	if header.SampleRate != uint32(sampleRate) {
		return fmt.Errorf("采样率不匹配 (需要 %d, 文件为 %d)", sampleRate, header.SampleRate)
	}
	if header.NumChannels != uint16(channels) {
		return fmt.Errorf("声道数不匹配 (需要 %d, 文件为 %d)", channels, header.NumChannels)
	}
	if header.BitsPerSample != uint16(bitDepth) {
		return fmt.Errorf("位深度不匹配 (需要 %d, 文件为 %d)", bitDepth, header.BitsPerSample)
	}

	for {
		var chunkID [4]byte
		var chunkSize uint32
		if err := binary.Read(file, binary.LittleEndian, &chunkID); err != nil {
			return err
		}
		if err := binary.Read(file, binary.LittleEndian, &chunkSize); err != nil {
			return err
		}
		if string(chunkID[:]) == "data" {
			fmt.Printf("'data' chunk 找到, 大小: %d 字节\n", chunkSize)
			break
		}
		if _, err := file.Seek(int64(chunkSize), io.SeekCurrent); err != nil {
			return err
		}
	}

	// --- PortAudio 初始化和流处理 ---
	if err := portaudio.Initialize(); err != nil {
		return fmt.Errorf("PortAudio 初始化失败: %w", err)
	}
	defer portaudio.Terminate()

	done := make(chan struct{})

	// 音频回调函数 (逻辑完全通用，无需修改)
	processAudio := func(out []float32) {
		readBuffer := make([]byte, bytesPerBuffer)
		bytesRead, err := io.ReadFull(file, readBuffer)

		samplesRead := bytesRead / bytesPerSample

		for i := 0; i < samplesRead; i++ {
			sample := int16(binary.LittleEndian.Uint16(readBuffer[i*2 : (i+1)*2]))
			out[i] = float32(sample) / 32768.0
		}

		if samplesRead < len(out) {
			for i := samplesRead; i < len(out); i++ {
				out[i] = 0.0
			}
		}

		if err != nil {
			if err == io.EOF || err == io.ErrUnexpectedEOF {
				fmt.Println("\n播放结束。")
				close(done)
			} else {
				fmt.Fprintf(os.Stderr, "从文件读取时发生错误: %v\n", err)
				close(done)
			}
		} else {
			fmt.Print(".")
		}
	}

	stream, err := portaudio.OpenDefaultStream(0, channels, float64(sampleRate), framesPerBuffer, processAudio)
	if err != nil {
		return fmt.Errorf("打开 PortAudio 流失败: %w", err)
	}
	defer stream.Close()

	if err := stream.Start(); err != nil {
		return fmt.Errorf("启动 PortAudio 流失败: %w", err)
	}
	defer stream.Stop()

	fmt.Println("开始播放 (每处理一个 80ms 的数据块打印一个'.')...")
	<-done

	return nil
}
