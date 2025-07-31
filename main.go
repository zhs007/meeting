package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/joho/godotenv"
)

var (
	// Common flags.
	target    = flag.String("target", "ast", "Target service: ast, etc.")
	outdir    = flag.String("outdir", "./", "Result output directory")
	repeat    = flag.Int("repeat", 1, "Number of repeat times")
	audiofile = flag.String("audio", "test_audio.wav", "Test audio file path")
	mic       = flag.Bool("mic", false, "Use microphone for audio input")
)

type Config struct {
	Host     string
	Endpoint string

	AppID      string
	AppKey     string
	AccessKey  string
	ResourceID string
}

var (
	conf Config
)

func init() {
	// 自动加载 .env 文件
	_ = godotenv.Load()

	flag.StringVar(&conf.Host, "host", "wss://openspeech.bytedance.com", "Host name")
	flag.StringVar(&conf.Endpoint, "endpoint", "v4/ast/v2/translate", "Endpoint path")

	// 优先从环境变量读取
	envAppID := os.Getenv("APP_ID")
	envAppKey := os.Getenv("APP_KEY")
	envAccessKey := os.Getenv("ACCESS_KEY")

	if envAppID != "" {
		conf.AppID = envAppID
	}
	if envAppKey != "" {
		conf.AppKey = envAppKey
	}
	if envAccessKey != "" {
		conf.AccessKey = envAccessKey
	}

	flag.StringVar(&conf.AppID, "app_id", conf.AppID, "Volcano AppID")
	flag.StringVar(&conf.AppKey, "app_key", conf.AppKey, "SAIL App key")
	flag.StringVar(&conf.AccessKey, "access_key", conf.AccessKey, "Access key for authorization")
	flag.StringVar(&conf.ResourceID, "resource_id", "volc.service_type.10053", "Commodity resource ID")
}

func main() {
	flag.Set("logtostderr", "true")
	flag.Parse()

	isV4 := strings.HasPrefix(conf.Endpoint, "v4/")
	for i := 0; i < *repeat; i++ {
		fmt.Printf("\n====================== Running count: %d ======================\n", i+1)
		if isV4 {
			switch *target {
			case "ast":
				translateV4(conf, *audiofile, i)
			default:
				panic("Target not supported for v4: " + *target)
			}
		} else {
			panic("Target not v4: ")
		}
	}
}
