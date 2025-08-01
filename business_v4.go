package main

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/golang/glog"
	"github.com/google/uuid"

	"code.byted.org/data-speech/wsclientsdk/audio"

	"code.byted.org/data-speech/wsclientsdk/protogen/common/event"
	"code.byted.org/data-speech/wsclientsdk/protogen/common/rpcmeta"
	"code.byted.org/data-speech/wsclientsdk/protogen/products/understanding/ast"
	"code.byted.org/data-speech/wsclientsdk/protogen/products/understanding/base"
)

// translateV4 sends audio chunks to server and receives translated text.
func translateV4(conf Config, audiofile string, n int) {
	// audioChunks, err := readAudioChunks(audiofile, 3200) // chunk size: 100ms
	// if err != nil {
	// 	glog.Exitf("Read audio chunks from file: %v", err)
	// }

	conn, err := dial(conf, uuid.New().String())
	if err != nil {
		glog.Exitf("Dial server: %v", err)
	}
	defer normalClose(conn)

	sessionId := uuid.New().String()
	translateRequest := &ast.TranslateRequest{
		RequestMeta: &rpcmeta.RequestMeta{
			SessionID: sessionId,
		},
		Event: event.Type_StartSession,
		User: &base.User{
			Uid: "ast_go_client",
			Did: "ast_go_client",
		},
		SourceAudio: &base.Audio{
			Format:  "wav",
			Rate:    16000,
			Bits:    16,
			Channel: 1,
		},
		TargetAudio: &base.Audio{
			Format: "pcm",
			Rate:   16000,
		},
		Request: &ast.ReqParams{
			Mode:           "s2s",
			SourceLanguage: "zh",
			TargetLanguage: "en",
		},
		Denoise: nil,
	}
	if err := shakeHands(conn, translateRequest, new(ast.TranslateResponse)); err != nil {
		glog.Exitf("Start session: %v", err)
	}
	glog.Infof("Session (ID=%s) started.", sessionId)

	// go func() {
	// 	t := time.NewTicker(100 * time.Millisecond)
	// 	defer t.Stop()

	// 	for _, chunk := range audioChunks {
	// 		glog.Infof("Sending chunk: %d", len(chunk))
	// 		if err := sendV4Request(conn, &ast.TranslateRequest{
	// 			RequestMeta: &rpcmeta.RequestMeta{
	// 				SessionID: sessionId,
	// 			},
	// 			Event: event.Type_TaskRequest,
	// 			SourceAudio: &base.Audio{
	// 				BinaryData: chunk,
	// 			},
	// 		}); err != nil {
	// 			glog.Exitf("Send audio chunk: %v", err)
	// 		}
	// 		<-t.C
	// 	}

	// 	if err := sendV4Request(conn, &ast.TranslateRequest{
	// 		RequestMeta: &rpcmeta.RequestMeta{
	// 			SessionID: sessionId,
	// 		},
	// 		Event: event.Type_FinishSession,
	// 	}); err != nil {
	// 		glog.Exitf("Finish session: %v", err)
	// 	}
	// 	glog.Info("FinishSession request is sent.")
	// }()

	chanIn := make(chan []int16, 128)
	_, out, err := audio.Init("MacBook Air麦克风", "BlackHole 2ch", 16000, 1, 16, 80*time.Millisecond, chanIn)
	if err != nil {
		glog.Exitf("Initialize audio: %v", err)
	}
	defer audio.Terminate()

	go func() {
		for {
			pcmData := <-chanIn

			glog.Infof("Sending chunk: %d", len(pcmData))
			if err := sendV4Request(conn, &ast.TranslateRequest{
				RequestMeta: &rpcmeta.RequestMeta{
					SessionID: sessionId,
				},
				Event: event.Type_TaskRequest,
				SourceAudio: &base.Audio{
					BinaryData: audio.Int16ToBytes(pcmData),
				},
			}); err != nil {
				glog.Exitf("Send audio chunk: %v", err)
			}
			// <-t.C
		}
	}()

	// portaudio.Initialize()
	// defer portaudio.Terminate()

	// outData := make([]byte, 3200)
	// stream, err := portaudio.OpenDefaultStream(0, 1, 48000, 3200, outData)
	// if err != nil {
	// 	glog.Errorf("PortAudio open stream error: %v", err)
	// 	return
	// }
	// defer stream.Close()
	// if err := stream.Start(); err != nil {
	// 	glog.Errorf("PortAudio start error: %v", err)
	// 	return
	// }
	// defer stream.Stop()

	var recvAudio bytes.Buffer
	var recvText strings.Builder
	for {
		glog.Infof("Waiting for message...")
		resp := new(ast.TranslateResponse)
		if err := receiveV4Message(conn, resp); err != nil {
			glog.Errorf("Receive message error: %v", err)
			break
		}

		if resp.GetEvent() == event.Type_SessionFailed {
			glog.Infof("(session_id=%s) failed, status code:%d, error message:%s", resp.GetResponseMeta().GetSessionID(), resp.GetResponseMeta().GetStatusCode(), resp.GetResponseMeta().GetMessage())
			break
		} else if resp.GetEvent() == event.Type_SessionCanceled {
			glog.Infof("(session_id=%s) canceled", resp.GetResponseMeta().GetSessionID())
			break
		} else if resp.GetEvent() == event.Type_SessionFinished {
			glog.Infof("(session_id=%s) finished", resp.GetResponseMeta().GetSessionID())
			break
		}
		glog.Infof("Receive message (session_id=%s, event=%s), seq:%d, text:%s, audio data length:%d",
			resp.GetResponseMeta().GetSessionID(), resp.GetEvent(), resp.GetResponseMeta().GetSequence(), resp.GetText(), len(resp.GetData()))
		glog.V(3).Infof("Receive message: %+v", resp)
		// 流式播放音频数据
		if len(resp.GetData()) > 0 {
			out.Write(resp.GetData())
			recvAudio.Write(resp.GetData())
			// if recvAudio.Len() >= 3200 {
			// 	_, err := recvAudio.Read(outData)
			// 	if err != nil {
			// 		glog.Errorf("Read audio data error: %v", err)

			// 		continue
			// 	}

			// 	if err := stream.Write(); err != nil {
			// 		glog.Errorf("PortAudio write error: %v", err)
			// 		return
			// 	}
			// }
			// // playPCMStream(resp.GetData(), 48000)
			// // 将 []byte 转为 []int16
			// pcm16 := make([]int16, len(pcm)/2)
			// for i := 0; i < len(pcm)/2; i++ {
			// 	pcm16[i] = int16(pcm[2*i]) | int16(pcm[2*i+1])<<8
			// }
			// if err := stream.Write(pcm16); err != nil {
			// 	glog.Errorf("PortAudio write error: %v", err)

			// }

		}

		recvText.WriteString(resp.GetText())

	}

	if recvAudio.Len() > 0 {
		path := filepath.Join(*outdir, fmt.Sprintf("v4_translate_audio_%05d.wav", n))
		if err := SavePCMAsWav(path, recvAudio.Bytes(), 16000); err != nil {
			glog.Exitf("Save audio file: %v", err)
		}
		glog.Infof("Session finished, audio is saved as: %s", path)
		glog.Infof("Session finished, text is: %s", recvText.String())
	} else {
		glog.Exit("Session finished, no audio data is received.")
	}
}

func SavePCMAsWav(filename string, pcm []byte, sampleRate int) error {
	f, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer f.Close()

	// WAV header
	numChannels := 1
	bitsPerSample := 16
	byteRate := sampleRate * numChannels * bitsPerSample / 8
	blockAlign := numChannels * bitsPerSample / 8
	dataLen := len(pcm)
	fileLen := 36 + dataLen

	// RIFF header
	f.Write([]byte("RIFF"))
	binary.Write(f, binary.LittleEndian, uint32(fileLen))
	f.Write([]byte("WAVE"))
	// fmt chunk
	f.Write([]byte("fmt "))
	binary.Write(f, binary.LittleEndian, uint32(16)) // fmt chunk size
	binary.Write(f, binary.LittleEndian, uint16(1))  // PCM format
	binary.Write(f, binary.LittleEndian, uint16(numChannels))
	binary.Write(f, binary.LittleEndian, uint32(sampleRate))
	binary.Write(f, binary.LittleEndian, uint32(byteRate))
	binary.Write(f, binary.LittleEndian, uint16(blockAlign))
	binary.Write(f, binary.LittleEndian, uint16(bitsPerSample))
	// data chunk
	f.Write([]byte("data"))
	binary.Write(f, binary.LittleEndian, uint32(dataLen))
	// PCM data
	f.Write(pcm)
	return nil
}
