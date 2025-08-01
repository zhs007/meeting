package main

import (
	"fmt"
	"log"
	"strings"

	"github.com/gordonklaus/portaudio"
)

// selectDevice 辅助函数，用于让用户选择设备
func selectDevice(devices []*portaudio.DeviceInfo, deviceType string, requiredChannels int) *portaudio.DeviceInfo {
	fmt.Printf("\n可用的%s设备:\n", deviceType)
	var availableDevices []*portaudio.DeviceInfo
	for _, device := range devices {
		isInput := deviceType == "输入" && device.MaxInputChannels >= requiredChannels
		isOutput := deviceType == "输出" && device.MaxOutputChannels >= requiredChannels

		if isInput || isOutput {
			availableDevices = append(availableDevices, device)
			fmt.Printf("[%d] %s\n", len(availableDevices)-1, device.Name)
		}
	}

	if len(availableDevices) == 0 {
		log.Fatalf("未找到可用的%s设备。", deviceType)
	}

	var choice int
	fmt.Printf("请选择一个%s设备的编号: ", deviceType)
	if _, err := fmt.Scanf("%d", &choice); err != nil || choice < 0 || choice >= len(availableDevices) {
		log.Fatalf("无效的选择: %v", err)
	}
	return availableDevices[choice]
}

func main() {
	// --- 1. 初始化 PortAudio (V2 标准步骤) ---
	if err := portaudio.Initialize(); err != nil {
		log.Fatalf("初始化 PortAudio 失败: %v", err)
	}
	defer portaudio.Terminate()

	devices, err := portaudio.Devices()
	if err != nil {
		log.Fatalf("获取设备列表失败: %v", err)
	}

	// --- 2. 选择设备 ---
	inputDevice := selectDevice(devices, "输入", 1)
	outputDevice := selectDevice(devices, "输出", 1) // 请求单声道，让驱动适配

	if !strings.Contains(outputDevice.Name, "BlackHole") {
		fmt.Println("警告：您选择的输出设备似乎不是 BlackHole。")
	}

	// --- 3. 定义流参数 ---
	const sampleRate = 16000
	const channels = 1 // 我们的整个处理流程都使用单声道
	const framesPerBuffer = 256

	fmt.Printf("\n--- 配置 ---\n")
	fmt.Printf("输入: %s\n", inputDevice.Name)
	fmt.Printf("输出: %s\n", outputDevice.Name)
	fmt.Printf("采样率: %d Hz, 声道数: %d\n", sampleRate, channels)
	fmt.Println("------------")

	// 使用 Go Channel 连接输入和输出
	// audioChan := make(chan []int16, 100)
	// var wg sync.WaitGroup

	// --- 4. 打开输入输出流 (V2核心API) ---
	// 使用 portaudio.OpenStream 创建 stream 对象
	inputStream, err := portaudio.OpenStream(portaudio.StreamParameters{
		Input:           portaudio.StreamDeviceParameters{Device: inputDevice, Channels: channels},
		SampleRate:      sampleRate,
		FramesPerBuffer: framesPerBuffer,
	}, nil)
	if err != nil {
		log.Fatalf("打开输入流失败: %v", err)
	}
	defer inputStream.Close()

	outputStream, err := portaudio.OpenStream(portaudio.StreamParameters{
		Output:          portaudio.StreamDeviceParameters{Device: outputDevice, Channels: channels},
		SampleRate:      sampleRate,
		FramesPerBuffer: framesPerBuffer,
	}, nil)
	if err != nil {
		log.Fatalf("打开输出流失败: %v", err)
	}
	defer outputStream.Close()

	// --- 5. 创建并发的读写 Goroutine ---

	// // 读取 Goroutine
	// wg.Add(1)
	// go func() {
	// 	defer wg.Done()
	// 	defer close(audioChan)
	// 	buffer := make([]int16, framesPerBuffer)
	// 	for {
	// 		// V2 API: 在流对象上调用 .Read()
	// 		if err := inputStream.Read(); err != nil {
	// 			// 当流被 Stop/Close 时，Read会返回错误，这是正常的退出方式
	// 			return
	// 		}

	// 		// 复制数据到新切片以安全地发送到 channel
	// 		dataToSend := make([]int16, framesPerBuffer)
	// 		copy(dataToSend, buffer)
	// 		audioChan <- dataToSend
	// 	}
	// }()

	// // 写入 Goroutine
	// wg.Add(1)
	// go func() {
	// 	defer wg.Done()
	// 	for data := range audioChan {
	// 		// 在这里进行你的音频处理
	// 		// 例如：简单的音量增益
	// 		for i, sample := range data {
	// 			// 将样本值乘以 1.5 来增大音量
	// 			newSample := float32(sample) * 1.5
	// 			// 防止数据溢出 int16 范围
	// 			if newSample > 32767 {
	// 				newSample = 32767
	// 			}
	// 			if newSample < -32768 {
	// 				newSample = -32768
	// 			}
	// 			data[i] = int16(newSample)
	// 		}

	// 		// V2 API: 在流对象上调用 .Write()
	// 		if err := outputStream.Write(data); err != nil {
	// 			log.Printf("写入输出流错误: %v", err)
	// 		}
	// 	}
	// }()

	// --- 6. 启动流并等待 (V2 API) ---
	if err := inputStream.Start(); err != nil {
		log.Fatalf("启动输入流失败: %v", err)
	}
	if err := outputStream.Start(); err != nil {
		log.Fatalf("启动输出流失败: %v", err)
	}

	fmt.Println("\n音频正在转发 (PortAudio V2 风格)...")
	fmt.Println("按回车键停止。")
	fmt.Scanln()

	// --- 7. 停止并清理 ---
	fmt.Println("正在停止...")
	// V2 API: 在流对象上调用 .Stop()
	inputStream.Stop()
	outputStream.Stop() // 写入流会在 channel 关闭后自动停止，但显式调用更安全

	// wg.Wait() // 等待所有 goroutine 优雅地退出
	fmt.Println("已停止。")
}
