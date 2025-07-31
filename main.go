package main

import (
	"flag"
	"fmt"
	"strings"
)

var (
	// Common flags.
	target = flag.String("target", "ast", "Target service: ast, etc.")
	outdir = flag.String("outdir", "/tmp", "Result output directory")
	repeat = flag.Int("repeat", 1, "Number of repeat times")
	audio  = flag.String("audio", "test_audio.wav", "Test audio file path")
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
	flag.StringVar(&conf.Host, "host", "wss://openspeech.bytedance.com", "Host name")
	flag.StringVar(&conf.Endpoint, "endpoint", "v4/ast/v2/translate", "Endpoint path")
	flag.StringVar(&conf.AppID, "app_id", "", "Volcano AppID")
	flag.StringVar(&conf.AppKey, "app_key", "HouOOHkeCTvN7ez5", "SAIL App key")
	flag.StringVar(&conf.AccessKey, "access_key", "123", "Access key for authorization")
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
				translateV4(conf, *audio, i)
			default:
				panic("Target not supported for v4: " + *target)
			}
		} else {
			panic("Target not v4: ")
		}
	}
}
