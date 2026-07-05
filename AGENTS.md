# AGENTS.md

本仓库包含 legacy Go 实现和 Python 实时翻译原型。当前主要任务方向是 macOS 单向实时会议翻译，Gemini 和 OpenAI 作为两条独立 Python 原型并存：

```text
AirPods 4 麦克风 -> Python app -> Gemini Live Translation -> BlackHole 2ch -> 会议 app 麦克风
AirPods 4 麦克风 -> Python app -> OpenAI Realtime Translation -> BlackHole 2ch -> 会议 app 麦克风
```

## 技术栈边界

- Gemini Python 原型位于 `src/meeting_translator/`，使用 `google-genai` 和 `sounddevice`。
- OpenAI Python 原型位于 `src/meeting_openai_translator/`，使用 `websockets` 和 `sounddevice`。
- legacy Go/豆包代码保留为参考，不要为了 Python 任务删除或重写 Go 文件。
- Gemini 和 OpenAI 保持独立入口和独立音频参数；不要引入不必要的通用 provider 抽象。
- 不接管会议 app 的扬声器输出；会议 app 扬声器应由用户设置为 AirPods 4。

## Python 验证命令

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest
python -m ruff check .
python -m meeting_translator devices
python -m meeting_translator check \
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
python -m meeting_openai_translator devices
python -m meeting_openai_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
git diff --check
```

如果本机设备名不同，先运行 `python -m meeting_translator devices`，再用实际设备名重跑 `check`。不要在代码里硬编码个人设备名。

## 失败策略

- 缺少 `GEMINI_API_KEY` 或 `OPENAI_API_KEY` 必须显式失败，不能打印 key 值。
- 缺少设备名、设备找不到、采样率/声道/dtype 不支持必须显式失败。
- 不允许静默选择默认音频设备。
- 不允许静默降级采样率或声道。
- Gemini 低延迟输出丢弃必须有明确策略和计数，不能伪装为正常播放成功。
- Gemini 输入队列溢出必须显式停止或报错，不能静默吞掉并继续运行。
- 不要为了测试通过加入生产代码不需要的隐藏 fallback。

## 安全规则

不得提交以下内容：

- `.env`
- 真实 Gemini API key、OpenAI API key 或其他 API key
- 会议音频、PCM、WAV
- `logs/` 下的会议字幕日志或运行摘要

依赖下载失败时，可临时使用用户指定代理：

```bash
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
```

代理只能用于当前 shell，不得写入源码、配置文件或测试。
