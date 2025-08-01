package main

import (
	"fmt"
	"log"

	"github.com/gordonklaus/portaudio"
)

func main() {
	// 1. 初始化 PortAudio
	if err := portaudio.Initialize(); err != nil {
		log.Fatalf("初始化 PortAudio 失败: %v", err)
	}
	defer portaudio.Terminate() // 确保在程序退出前终止 PortAudio

	// 2. 获取可用设备列表
	devices, err := portaudio.Devices()
	if err != nil {
		log.Fatalf("获取设备列表失败: %v", err)
	}

	// 3. 筛选并显示麦克风设备
	var micDevices []*portaudio.DeviceInfo
	fmt.Println("可用的麦克风设备:")
	for _, device := range devices {
		// 麦克风设备应至少有一个输入通道
		if device.MaxInputChannels > 0 {
			micDevices = append(micDevices, device)
			fmt.Printf("[%d] %s\n", len(micDevices)-1, device.Name)
		}
	}

	if len(micDevices) == 0 {
		log.Fatal("未找到可用的麦克风设备")
	}

	// 4. 让用户选择一个麦克风
	var choice int
	fmt.Print("请选择一个麦克风设备的编号: ")
	if _, err := fmt.Scanf("%d", &choice); err != nil || choice < 0 || choice >= len(micDevices) {
		log.Fatalf("无效的选择: %v", err)
	}

	selectedDevice := micDevices[choice]
	fmt.Printf("已选择: %s\n", selectedDevice.Name)

	// 5. 配置并打开音频流
	// 定义一个缓冲区用于存放音频数据
	buffer := make([]int32, 64)
	streamParameters := portaudio.StreamParameters{
		Input: portaudio.StreamDeviceParameters{
			Device:   selectedDevice,
			Channels: 1, // 使用单声道
			Latency:  selectedDevice.DefaultLowInputLatency,
		},
		Output:          portaudio.StreamDeviceParameters{}, // 我们只关心输入
		SampleRate:      16000,
		FramesPerBuffer: len(buffer),
	}

	stream, err := portaudio.OpenStream(streamParameters, &buffer)
	if err != nil {
		log.Fatalf("打开音频流失败: %v", err)
	}
	defer stream.Close()

	// 6. 开始并读取音频流
	if err := stream.Start(); err != nil {
		log.Fatalf("启动音频流失败: %v", err)
	}
	defer stream.Stop()

	fmt.Println("正在录音... 按 Ctrl+C 停止。")

	// 持续读取音频数据
	for {
		if err := stream.Read(); err != nil {
			log.Fatalf("读取音频流失败: %v", err)
		}
		// 在这里处理 `buffer` 中的音频数据
		// 例如: fmt.Println(buffer)
	}
}
