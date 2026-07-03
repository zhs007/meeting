# 任务 2：OpenAI Realtime Translation Python 独立原型初始化

## 1. 任务目标

在已经完成任务 1 Gemini 原型的基础上，为本仓库 `/Users/zerro/github.com/meeting` 新增一条 OpenAI Realtime Translation 单向实时会议翻译原型。

目标链路：

```text
AirPods 4 麦克风中文语音
  -> meeting OpenAI Python app
  -> OpenAI Realtime Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本任务不替换 Gemini，不删除 legacy Go/豆包代码。Gemini 和 OpenAI 作为两条独立 Python 原型并存，避免为了并存而引入不必要的通用 provider 抽象。

## 2. 当前仓库事实

- Gemini 原型已位于 `src/meeting_translator/`。
- Gemini CLI 为 `python -m meeting_translator ...`。
- Gemini 使用 `GEMINI_API_KEY`、`google-genai`、16kHz 输入、24kHz 输出。
- legacy Go/豆包代码仍保留为历史参考。
- `AGENTS.md`、`AGENT_GUIDE.md`、`README.md` 已描述 Gemini 主线，需要同步更新为 Gemini/OpenAI 并存。

## 3. OpenAI 硬接口约束

- 模型：`gpt-realtime-translate`
- WebSocket endpoint：`wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate`
- 认证 header：`Authorization: Bearer ${OPENAI_API_KEY}`
- 建议 header：`OpenAI-Safety-Identifier: <stable-privacy-preserving-user-id>`
- 这是 translation session，不是普通 voice-agent session。
- 不连接 `/v1/realtime`。
- 不调用 `response.create`。
- 输入音频持续 append，包含短暂停顿和静音。
- WebSocket 原始音频路径发送 base64 编码的 24kHz PCM16。
- 输出事件包含翻译音频 delta、源字幕 delta、目标字幕 delta。
- 源流结束或 Ctrl+C 时必须先发 `session.close`，停止继续 append 音频，并继续读取事件直到收到 `session.closed`，再关闭 socket。

默认音频参数：

```text
input_sample_rate = 24000
input_channels = 1
input_dtype = int16
input_chunk_ms = 100
input_samples_per_chunk = 2400
input_bytes_per_chunk = 4800

output_sample_rate = 24000
output_channels = 1
output_dtype = int16
```

如果 AirPods 4 或 BlackHole 2ch 不能按上述参数打开，应显式失败并打印设备、采样率、声道、dtype，不允许静默降级到别的采样率或别的设备。

本任务不实现自动重采样。

## 4. 边界

- 新增 OpenAI 独立 Python 包，例如 `src/meeting_openai_translator/`。
- 保留 Gemini 包 `src/meeting_translator/` 的现有行为。
- 不实现双向翻译。
- 不接管会议 app 的扬声器输出。
- 不把会议 app 输出 pass-through 到 AirPods。
- 不删除 Go/豆包代码。
- 不提交 `.env`、真实 API key、会议音频、PCM/WAV、`logs/` 下真实日志。
- 不隐藏设备、采样率、API key、网络、协议错误。
- 不为了测试通过加入生产代码不需要的 fallback。

## 5. 目标文件结构

新增或更新：

```text
src/meeting_openai_translator/
  __init__.py
  __main__.py
  audio_devices.py
  audio_io.py
  cli.py
  config.py
  openai_events.py
  openai_realtime_translate.py
  pcm.py
  transcript_log.py

tests/
  test_openai_config.py
  test_openai_device_selection.py
  test_openai_event_shapes.py
  test_openai_pcm.py

requirements.txt
pyproject.toml
.env.example
README.md
AGENTS.md
AGENT_GUIDE.md
```

OpenAI CLI 入口：

```bash
python -m meeting_openai_translator devices
python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
OPENAI_API_KEY=your_key_here python -m meeting_openai_translator run --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

## 6. 配置约定

OpenAI 专属环境变量：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_SAFETY_IDENTIFIER=local-user-hash-placeholder
MEETING_OPENAI_INPUT_DEVICE=AirPods 4
MEETING_OPENAI_OUTPUT_DEVICE=BlackHole 2ch
MEETING_OPENAI_TARGET_LANGUAGE=en
```

设备名优先级：

```text
命令行参数 > MEETING_OPENAI_* > MEETING_* > 无默认值
```

API key 规则：

- `OPENAI_API_KEY` 缺失时，`check` 和 `run` 必须失败。
- 错误信息不能打印 key 值。
- `OPENAI_SAFETY_IDENTIFIER` 为空时可以使用本地固定占位值，但不得包含邮箱、姓名、会议号等可识别信息。

## 7. 实现阶段

### 阶段 A：OpenAI 独立骨架

- 新增 `src/meeting_openai_translator/`。
- 新增 `python -m meeting_openai_translator` 入口。
- 新增 `devices` 子命令。
- 更新依赖，加入 `websockets`。

验收：

```bash
python -m pytest
python -m ruff check .
python -m meeting_openai_translator devices
```

### 阶段 B：OpenAI 设备选择和 24k 音频 I/O

- 输入设备按精确名称选择。
- 输出设备按精确名称选择。
- 输入/输出均按 24kHz mono int16 打开。
- 100ms chunk 固定 4800 bytes。
- 不允许默认设备和隐式降级。

验收：

```bash
python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
python -m pytest
python -m ruff check .
```

如果本机设备名不同，先运行 `devices`，再用实际设备名重跑 `check`。不得在代码里硬编码个人设备名。

### 阶段 C：OpenAI Realtime Translation

- 连接 `/v1/realtime/translations?model=gpt-realtime-translate`。
- 发送 `session.update`，设置 `session.audio.output.language`。
- 发送 `session.input_audio_buffer.append`，音频为 base64 PCM16。
- 接收 `session.output_audio.delta`、`session.input_transcript.delta`、`session.output_transcript.delta`、`session.closed`。
- Ctrl+C 或输入结束时发送 `session.close`。
- `session.close` 后不得继续 append 音频。
- 等到 `session.closed` 后再关闭 socket。

人工验收：

```bash
OPENAI_API_KEY=your_key_here python -m meeting_openai_translator run --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

会议 app 麦克风选择 BlackHole 2ch，扬声器选择 AirPods 4。macOS 系统输出不要选择 BlackHole。

### 阶段 D：文档和协作规则同步

- README 同步 Gemini/OpenAI 两条原型。
- AGENTS.md 同步独立入口、验证命令、失败策略和安全规则。
- AGENT_GUIDE.md 同步项目方向和验证命令。
- `.env.example` 只包含占位符。

## 8. 单元测试要求

必须覆盖：

- OpenAI 配置优先级。
- 缺少 `OPENAI_API_KEY` 显式失败且不泄露 key 值。
- `OPENAI_SAFETY_IDENTIFIER` 为空时使用不可识别占位值。
- 精确设备名匹配和缺设备显式失败。
- 不允许静默选择默认设备。
- 24kHz、100ms、mono、PCM16 chunk 为 4800 bytes。
- PCM base64 roundtrip。
- 非 100ms chunk 在发送前失败。
- `session.input_transcript.delta`、`session.output_transcript.delta`、`session.output_audio.delta`、`session.closed`。
- `session.close` 后不得继续发送 `session.input_audio_buffer.append`。
- 未知事件显式记录为 unsupported。

## 9. 验证命令清单

完成后至少运行：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest
python -m ruff check .
python -m meeting_translator devices
python -m meeting_openai_translator devices
python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
git diff --check
git status --short
```

如依赖下载失败，可在当前 shell 临时使用用户指定代理重试，不得写入源码、配置或测试：

```bash
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
```

## 10. 安全检查

提交前必须检查：

```bash
rg -n --hidden -g '!.git' -e 'OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
git status --short
```

要求：

- `.env` 不得入库。
- `.env.example` 只能写占位符。
- 真实 API key 不得出现在源码、README、任务报告、测试 fixture、日志中。
- 会议音频、PCM、WAV、字幕日志默认不入库。

## 11. 任务报告要求

任务完成后写中文报告：

```text
tasks/2-openai-realtime-translation-python-init-[utctime].md
```

报告至少包含：

- 实际变更文件清单。
- Gemini/OpenAI 并存边界说明。
- OpenAI 音频链路、模型、endpoint、音频参数。
- 确认没有使用 `/v1/realtime` 和 `response.create`。
- `session.close` -> `session.closed` 关闭流程。
- 运行过的命令和结果摘要。
- 依赖安装是否使用代理。
- 单元测试和 ruff 结果。
- devices/check 结果。
- run 人工验收结果；无法人工验收时说明缺少条件。
- 安全扫描结果。
- 未完成事项和下一步建议。

## 12. 完成标准

- OpenAI 独立 Python 原型已落地。
- Gemini 现有入口和测试未被破坏。
- `python -m pytest` 通过。
- `python -m ruff check .` 通过。
- `python -m meeting_openai_translator devices` 可列设备。
- `check` 对实际设备给出明确通过或明确失败原因。
- OpenAI endpoint 是 `/v1/realtime/translations`。
- 不调用 `response.create`。
- 音频事件使用 `session.input_audio_buffer.append`。
- 关闭流程使用 `session.close` 并等待 `session.closed`。
- 文档和 agent 规则已同步。
- 已写 UTC 中文任务报告。

## 13. 二次遗漏检查

交付前逐项确认：

- Go/豆包代码未被误删。
- Gemini 包未被切换成 OpenAI，也未被改坏采样率合同。
- OpenAI 包没有硬编码个人设备名。
- 输入设备和输出设备没有被设计成 pass-through 混音。
- 停止 app 只停止翻译链路，不接管会议 app 的 AirPods 输出。
- OpenAI 输入/输出采样率为 24kHz PCM16 mono。
- 100ms chunk 为 4800 bytes 且有测试覆盖。
- 缺 key、缺设备、采样率不支持都会显式失败。
- 没有引入不必要 provider 抽象。
- 没有为了测试通过加入隐藏 fallback。
- 文档、任务计划、agent 规则没有互相冲突。
- 任务报告文件名使用 UTC 时间。
