# meeting

本仓库当前包含三条实现线：

- Python + Gemini Live Translation 单向实时会议翻译原型。
- Python + OpenAI Realtime Translation 单向实时会议翻译原型。
- legacy/reference Go + 火山/豆包 AST 音频链路。

Python 原型是当前主要方向。Gemini 和 OpenAI 保持独立入口和独立音频参数，不做通用 provider 抽象。Go 代码保留为历史参考，不在本任务中删除或重写。

## Python + Gemini 单向实时翻译

目标链路：

```text
AirPods 4 麦克风中文语音
  -> meeting Python app
  -> Gemini Live Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本 app 只处理本地说话者的麦克风到会议虚拟麦克风的单向翻译，不接管会议 app 的扬声器输出。

会议 app 设置应为：

- 麦克风：`BlackHole 2ch`
- 扬声器：`AirPods 4`

macOS 系统输出不要选择 BlackHole，避免把系统声音送进会议麦克风链路。

### 音频和 Gemini 参数

- Gemini 模型：`gemini-3.5-live-translate-preview`
- 输入：raw PCM16 little-endian、16kHz、mono
- 输入 chunk：100ms，固定 3200 bytes
- 输出：raw PCM16 little-endian、24kHz、mono
- 默认源语言 hint：`zh-CN`
- 默认目标语言：`en`
- 默认固定输出声线：`Kore`

设备名、采样率、声道、dtype 不支持时会显式失败，不会静默降级到默认设备或其他采样率。

### 初始化

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

如果依赖下载失败，可临时使用用户指定代理重试安装命令：

```bash
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
python -m pip install -r requirements.txt
python -m pip install -e .
```

不要把代理写入源码、配置文件或测试。

### 配置

复制 `.env.example` 为 `.env` 后填写：

```env
GEMINI_API_KEY=your_gemini_api_key_here
MEETING_INPUT_DEVICE=AirPods 4
MEETING_OUTPUT_DEVICE=BlackHole 2ch
MEETING_SOURCE_LANGUAGE=zh-CN
MEETING_TARGET_LANGUAGE=en
MEETING_VOICE_NAME=Kore
MEETING_ECHO_TARGET_LANGUAGE=false
MEETING_INPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_THREAD_QUEUE_CHUNKS=8
MEETING_MAX_PLAYBACK_BUFFER_MS=800
MEETING_METRICS_INTERVAL_SEC=10
MEETING_AUTO_RECONNECT=true
MEETING_MAX_RECONNECTS=0
MEETING_DEBUG_EVENTS=false
```

配置优先级：

```text
命令行参数 > 环境变量 > .env > 默认值
```

设备名没有隐式默认值。未通过命令行、环境变量或 `.env` 指定设备时，`check` 和 `run` 会失败并提示先列设备。

Gemini 原型默认使用 `MEETING_SOURCE_LANGUAGE=zh-CN` 作为输入音频转写语言 hint，并固定 `MEETING_VOICE_NAME=Kore` 作为输出声线，适合单人会议里保持译员声音稳定。如果源输入不是中文，可用 `--source-language ja` 等 BCP-47 语言码覆盖；如果想换固定声线，可用 `--voice-name Charon` 等 Gemini 预置 voice 名覆盖。Gemini 原型默认使用低延迟本地队列：输入队列 8 个 100ms chunk，Gemini 输出 asyncio 队列 8 个 chunk，输出线程队列 8 个 chunk，播放缓冲最多 800ms。旧音频只会按明确低延迟策略丢弃，并在运行摘要中计数；输入队列溢出会显式停止本次运行，不会静默堆积多秒延迟。启动和 GoAway 重连期间会等 Gemini session ready 后再把麦克风音频放入输入队列，断开窗口里的输入 chunk 会作为 `input_dropped_while_disconnected` 计数。

### 列设备

```bash
python -m meeting_translator devices
```

输出包含设备 index、name、输入/输出通道数、默认采样率，以及是否可作为输入/输出设备。

### 检查链路

```bash
python -m meeting_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --source-language zh-CN \
  --target-language en \
  --voice-name Kore
```

`check` 会验证：

- `GEMINI_API_KEY` 存在，但不会打印 key 值。
- 输入设备可按 16kHz mono int16 打开。
- 输出设备可按 24kHz mono int16 打开。
- Gemini 配置可构造为 Live Translation + 源语言 hint + 目标语言 + 固定输出声线。
- 100ms 输入 chunk 为 3200 bytes。
- Gemini 低延迟队列、metrics、自动重连参数可解析。

### 运行

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --source-language zh-CN \
  --target-language en \
  --voice-name Kore \
  --input-queue-chunks 8 \
  --output-queue-chunks 8 \
  --output-thread-queue-chunks 8 \
  --max-playback-buffer-ms 800 \
  --metrics-interval-sec 10 \
  --auto-reconnect
```

运行时会打印 input transcript、output transcript 和周期 metrics，例如本地输入/输出队列深度、播放缓冲时长、输出丢弃数、重连数、未知事件数。5 秒体感延迟不一定是网络问题，先看 metrics 中本地队列是否积压到多秒。

Gemini Live session 约 10 分钟可能收到 GoAway。默认 `MEETING_AUTO_RECONNECT=true` 会在 GoAway 前主动关闭当前 session、清理旧输入/输出音频并创建新 session；如果关闭自动重连，GoAway 会作为正常会话结束记录到 summary。Ctrl+C 会关闭输入流、输出流和 Gemini session，并输出本次运行摘要。

## Python + OpenAI 单向实时翻译

目标链路：

```text
AirPods 4 麦克风中文语音
  -> meeting OpenAI Python app
  -> OpenAI Realtime Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本 app 只处理本地说话者的麦克风到会议虚拟麦克风的单向翻译，不接管会议 app 的扬声器输出。会议 app 设置同样应为：

- 麦克风：`BlackHole 2ch`
- 扬声器：`AirPods 4`

### OpenAI 参数

- OpenAI 模型：`gpt-realtime-translate`
- WebSocket endpoint：`wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate`
- 输入：raw PCM16 little-endian、24kHz、mono
- 输入 chunk：100ms，固定 4800 bytes，base64 后发送
- 输出：raw PCM16 little-endian、24kHz、mono
- 默认目标语言：`en`

OpenAI 原型不使用 `/v1/realtime` voice-agent session，不调用 `response.create`。关闭时先发送 `session.close`，停止继续 append 音频，并等待 `session.closed`。

### OpenAI 配置

`.env` 可填写：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_SAFETY_IDENTIFIER=local-user-hash-placeholder
MEETING_OPENAI_INPUT_DEVICE=AirPods 4
MEETING_OPENAI_OUTPUT_DEVICE=BlackHole 2ch
MEETING_OPENAI_TARGET_LANGUAGE=en
```

`OPENAI_API_KEY` 缺失时 `check` 和 `run` 会显式失败，且不会打印 key 值。`OPENAI_SAFETY_IDENTIFIER` 为空时使用不可识别的本地占位值。

### OpenAI 列设备

```bash
python -m meeting_openai_translator devices
```

### OpenAI 检查链路

```bash
python -m meeting_openai_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

`check` 会验证：

- `OPENAI_API_KEY` 存在，但不会打印 key 值。
- 输入设备可按 24kHz mono int16 打开。
- 输出设备可按 24kHz mono int16 打开。
- OpenAI 配置为 `gpt-realtime-translate` + `/v1/realtime/translations`。
- 100ms 输入 chunk 为 4800 bytes。
- 关闭流程入口为 `session.close` -> 等待 `session.closed`。

### OpenAI 运行

```bash
OPENAI_API_KEY=your_key_here python -m meeting_openai_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

运行时会打印 input transcript 和 output transcript，并把本次摘要写入 `logs/`。日志目录默认不入库，日志不得包含 API key。

### 验证

```bash
python -m pytest
python -m ruff check .
python -m meeting_translator devices
python -m meeting_openai_translator devices
git diff --check
```

## Legacy/reference Go + 火山/豆包 AST

旧 Go 链路保留为音频链路参考：

```bash
go run . --target=ast \
  --host=wss://openspeech.bytedance.com \
  --endpoint=v4/ast/v2/translate \
  --resource_id=volc.service_type.10053 \
  --app_id=<app_id> \
  --access_key=<access_key>
```

Go 命令不属于 Python 原型验收路径。修改 legacy Go 代码前请单独确认验收边界。
