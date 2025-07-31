package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"

	"github.com/golang/glog"
	"github.com/gorilla/websocket"
	"google.golang.org/protobuf/proto"
)

func buildHTTPHeader(conf Config, connID string) http.Header {
	h := http.Header{
		"X-Api-App-Key":     []string{conf.AppKey},
		"X-Api-Access-Key":  []string{conf.AccessKey},
		"X-Api-Resource-Id": []string{conf.ResourceID},
		"X-Api-Connect-Id":  []string{connID},
	}
	if conf.AppID != "" {
		h["X-Api-App-Id"] = []string{conf.AppID}
	}
	return h
}

func dial(conf Config, connID string) (*websocket.Conn, error) {
	addr := fmt.Sprintf("%s/api/%s", conf.Host, conf.Endpoint)
	glog.Infof("Dial server: %s", addr)
	header := buildHTTPHeader(conf, connID)
	conn, r, connErr := websocket.DefaultDialer.DialContext(context.Background(), addr, header)
	if r != nil {
		logID := r.Header.Get("X-Tt-Logid")
		glog.Infof("Dial server with LogID: %s", logID)
	}
	if connErr != nil {
		if r != nil {
			body, err := io.ReadAll(r.Body)
			if err != nil {
				body = []byte(fmt.Sprintf("parse response body failed: %v", err))
			}
			connErr = fmt.Errorf("[code=%s] [body=%s] %w", r.Status, body, connErr)
		}
		return nil, connErr
	}
	return conn, nil
}

func normalClose(conn *websocket.Conn) {
	defer conn.Close()
	normalClosure := websocket.FormatCloseMessage(websocket.CloseNormalClosure, "")
	if err := conn.WriteControl(websocket.CloseMessage, normalClosure, time.Now().Add(time.Second)); err != nil {
		glog.Errorf("Write websocket NormalClosure: %v", err)
	}
}

func readAudioChunks(path string, chunkSize int) ([][]byte, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	max := len(content)

	var chunks [][]byte
	for i := 0; i < max; i += chunkSize {
		if i+chunkSize < max {
			chunks = append(chunks, content[i:i+chunkSize])
		} else {
			chunks = append(chunks, content[i:])
		}
	}
	return chunks, nil
}

func sendV4Request(conn *websocket.Conn, req proto.Message) error {
	frame, err := proto.Marshal(req)
	if err != nil {
		return fmt.Errorf("proto marshal failed:%w", err)
	}

	if err := conn.WriteMessage(websocket.BinaryMessage, frame); err != nil {
		return fmt.Errorf("send V4 request: %w", err)
	}

	glog.Info("V4 request is sent.")
	return nil
}

func receiveV4Message(conn *websocket.Conn, resp proto.Message) error {
	mt, frame, err := conn.ReadMessage()
	if err != nil {
		return fmt.Errorf("read message: %w", err)
	}
	if mt != websocket.BinaryMessage && mt != websocket.TextMessage {
		return fmt.Errorf("unexpected Websocket message type: %d", mt)
	}

	if err := proto.Unmarshal(frame, resp); err != nil {
		glog.Warningf("Unable to unmarshal response message: %v", frame)
		return fmt.Errorf("unmarshal response message: %w", err)
	}
	return nil
}

func shakeHands(conn *websocket.Conn, req, resp proto.Message) error {
	if err := sendV4Request(conn, req); err != nil {
		return fmt.Errorf("start connection: %w", err)
	}

	if err := receiveV4Message(conn, resp); err != nil {
		return fmt.Errorf("receive ConnectionStarted response: %w", err)
	}

	//if event.Type(msg.Event) != event.Type_ConnectionStarted {
	//	return fmt.Errorf("unexpected response event (%s) for StartConnection request", event.Type(msg.Event))
	//}
	glog.Infof("Shake-hands done: %s", resp)
	return nil
}
