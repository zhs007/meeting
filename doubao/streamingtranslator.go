package doubao

import (
	"bytes"
	"strings"

	"github.com/golang/glog"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"

	"code.byted.org/data-speech/wsclientsdk/protogen/common/event"
	"code.byted.org/data-speech/wsclientsdk/protogen/common/rpcmeta"
	"code.byted.org/data-speech/wsclientsdk/protogen/products/understanding/ast"
	"code.byted.org/data-speech/wsclientsdk/protogen/products/understanding/base"
)

type StreamingTranslator struct {
	cfg       Config
	conn      *websocket.Conn
	sessionID string
}

func (st *StreamingTranslator) Start() error {
	conn, err := dial(st.cfg, uuid.New().String())
	if err != nil {
		glog.Exitf("Dial server: %v", err)
	}
	defer normalClose(conn)

	st.sessionID = uuid.New().String()

	translateRequest := &ast.TranslateRequest{
		RequestMeta: &rpcmeta.RequestMeta{
			SessionID: st.sessionID,
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
			Rate:   48000,
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
	glog.Infof("Session (ID=%s) started.", st.sessionID)

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
		recvAudio.Write(resp.GetData())
		recvText.WriteString(resp.GetText())
	}

	return nil
}

func NewStreamingTranslator(cfg Config) *StreamingTranslator {
	return &StreamingTranslator{
		cfg:  cfg,
		conn: nil, // Connection will be established in Start method
	}
}
