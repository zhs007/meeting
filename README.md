# meeting

本仓库当前包含两条实现线：

- Python + Gemini Live Translation 单向实时会议翻译原型。
- legacy/reference Go + 火山/豆包 AST 音频链路。

Python 原型是当前主要方向。Go 代码保留为历史参考，不在本任务中删除或重写。

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
- 默认目标语言：`en`

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
MEETING_TARGET_LANGUAGE=en
MEETING_ECHO_TARGET_LANGUAGE=false
```

配置优先级：

```text
命令行参数 > 环境变量 > .env > 默认值
```

设备名没有隐式默认值。未通过命令行、环境变量或 `.env` 指定设备时，`check` 和 `run` 会失败并提示先列设备。

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
  --target-language en
```

`check` 会验证：

- `GEMINI_API_KEY` 存在，但不会打印 key 值。
- 输入设备可按 16kHz mono int16 打开。
- 输出设备可按 24kHz mono int16 打开。
- Gemini 配置可构造为 Live Translation + 目标语言。
- 100ms 输入 chunk 为 3200 bytes。

### 运行

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

运行时会打印 input transcript 和 output transcript，并把本次摘要写入 `logs/`。日志目录默认不入库，日志不得包含 API key。

Ctrl+C 会关闭输入流、输出流和 Gemini session，并输出本次运行摘要。

### 验证

```bash
python -m pytest
python -m ruff check .
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
