package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"time"

	"github.com/gordonklaus/portaudio"
)

// WavHeader 定义了标准的 44 字节 WAV 文件头
type WavHeader struct {
	RiffMark      [4]byte // "RIFF"
	FileSize      uint32  // 文件大小 - 8
	WaveMark      [4]byte // "WAVE"
	FmtMark       [4]byte // "fmt "
	FmtSize       uint32  // 16 for PCM
	AudioFormat   uint16  // 1 for PCM
	NumChannels   uint16  // 声道数
	SampleRate    uint32  // 采样率
	ByteRate      uint32  // SampleRate * NumChannels * BitsPerSample/8
	BlockAlign    uint16  // NumChannels * BitsPerSample/8
	BitsPerSample uint16  // 每个样本的位数
	DataMark      [4]byte // "data"
	DataSize      uint32  // 数据大小
}

func main() {
	const (
		sampleRate     = 16000
		channels       = 1
		bitsPerSample  = 16
		recordDuration = 5 * time.Second
		outputFileName = "recording.wav"
	)

	fmt.Printf("准备录音，时长: %v\n", recordDuration)

	if err := recordWav(outputFileName, sampleRate, channels, bitsPerSample, recordDuration); err != nil {
		fmt.Fprintf(os.Stderr, "错误: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("录音完成！文件已保存为 '%s'\n", outputFileName)
	fmt.Println("你可以使用 ffplay 或其他播放器来播放它:")
	fmt.Printf("ffplay %s\n", outputFileName)
}

func recordWav(fileName string, sampleRate, channels, bitsPerSample int, duration time.Duration) error {
	// 1. 创建 WAV 文件
	file, err := os.Create(fileName)
	if err != nil {
		return fmt.Errorf("无法创建文件: %w", err)
	}
	defer file.Close()

	// 2. 准备并写入一个占位的 WAV 头部
	header := WavHeader{
		RiffMark:      [4]byte{'R', 'I', 'F', 'F'},
		FileSize:      0, // 占位
		WaveMark:      [4]byte{'W', 'A', 'V', 'E'},
		FmtMark:       [4]byte{'f', 'm', 't', ' '},
		FmtSize:       16, // For PCM
		AudioFormat:   1,  // PCM
		NumChannels:   uint16(channels),
		SampleRate:    uint32(sampleRate),
		ByteRate:      uint32(sampleRate * channels * bitsPerSample / 8),
		BlockAlign:    uint16(channels * bitsPerSample / 8),
		BitsPerSample: uint16(bitsPerSample),
		DataMark:      [4]byte{'d', 'a', 't', 'a'},
		DataSize:      0, // 占位
	}
	if err := binary.Write(file, binary.LittleEndian, &header); err != nil {
		return fmt.Errorf("写入 WAV 占位头部失败: %w", err)
	}

	// 用于记录总共写入了多少音频数据字节
	var totalBytesWritten uint32 = 0

	// 3. 初始化 PortAudio
	if err := portaudio.Initialize(); err != nil {
		return fmt.Errorf("PortAudio 初始化失败: %w", err)
	}
	defer portaudio.Terminate()

	// 4. 定义音频回调函数 (核心逻辑)
	// PortAudio 会从麦克风获取数据，并填充到 in 缓冲区
	processAudio := func(in []float32) {
		// 创建一个 int16 的缓冲区来存放转换后的 PCM 数据
		pcmData := make([]int16, len(in))

		// 将 float32 转换为 int16
		for i, sample := range in {
			// 将 -1.0 到 1.0 的 float32 映射到 -32767 到 32767 的 int16
			pcmData[i] = int16(sample * 32767.0)
		}

		// 将转换后的 PCM 数据以二进制形式写入文件
		if err := binary.Write(file, binary.LittleEndian, pcmData); err != nil {
			fmt.Fprintf(os.Stderr, "写入音频数据失败: %v\n", err)
			return // 在回调中最好不要 panic
		}

		// 更新写入的总字节数
		totalBytesWritten += uint32(len(pcmData) * 2) // 每个 int16 是 2 字节
	}

	// 5. 打开音频输入流
	stream, err := portaudio.OpenDefaultStream(channels, 0, float64(sampleRate), 0, processAudio)
	if err != nil {
		return fmt.Errorf("打开 PortAudio 输入流失败: %w", err)
	}
	defer stream.Close()

	// 6. 开始录音
	if err := stream.Start(); err != nil {
		return fmt.Errorf("启动 PortAudio 流失败: %w", err)
	}

	fmt.Println("正在录音...")

	// 阻塞，直到录音时长结束
	time.Sleep(duration)

	// 7. 停止录音
	if err := stream.Stop(); err != nil {
		return fmt.Errorf("停止 PortAudio 流失败: %w", err)
	}

	fmt.Println("录音结束，正在更新 WAV 头部...")

	// 8. 更新 WAV 头部信息
	// FileSize 是文件总大小减去 "RIFF" 标记和 FileSize 字段本身的大小 (8字节)
	// 但更简单的计算是：头部大小(除了前8字节) + 数据大小 = 36 + DataSize
	header.DataSize = totalBytesWritten
	header.FileSize = header.DataSize + 36

	// Seek 到文件开头相应位置并写入正确的值
	// 更新 FileSize (在文件偏移量 4 的位置)
	if _, err := file.Seek(4, 0); err != nil {
		return fmt.Errorf("Seek 到 FileSize 位置失败: %w", err)
	}
	if err := binary.Write(file, binary.LittleEndian, header.FileSize); err != nil {
		return fmt.Errorf("更新 FileSize 失败: %w", err)
	}

	// 更新 DataSize (在文件偏移量 40 的位置)
	if _, err := file.Seek(40, 0); err != nil {
		return fmt.Errorf("Seek 到 DataSize 位置失败: %w", err)
	}
	if err := binary.Write(file, binary.LittleEndian, header.DataSize); err != nil {
		return fmt.Errorf("更新 DataSize 失败: %w", err)
	}

	return nil
}
