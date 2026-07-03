# 任务 2：OpenAI Realtime Translation Python 单向实时翻译初始化

## 1. 任务目标

在本仓库 `/Users/zerro/github.com/meeting` 中，基于新分支初始化一个 Python 原型项目，用 OpenAI Realtime Translation 实现单向实时同声传译：

```text
AirPods 4 麦克风中文语音
  -> meeting Python app
  -> OpenAI Realtime Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本任务只做单向链路，不做双向翻译，不接管会议 app 的扬声器输出。会议 app 的输出设备应由会议 app 自己设置为 AirPods 4。

本任务是 OpenAI 方案的独立任务文档。若后续选择 OpenAI 路线，应以本任务为执行依据；`tasks/1-gemini-live-translation-python-init.md` 仅作为 Gemini 备选方案，不要求同时实现。

## 2. 当前仓库事实

当前仓库是 Go 项目，主要文件如下：

- `main.go`：当前入口，读取豆包/火山相关 `APP_ID`、`APP_KEY`、`ACCESS_KEY`，默认 endpoint 是 `v4/ast/v2/translate`。
- `business_v4.go`：当前翻译主流程，硬编码 `audio.Init("MacBook Air麦克风", "BlackHole 2ch", 16000, 1, 16, 80*time.Millisecond, chanIn)`。
- `audio/`：基于 PortAudio 的输入/输出封装。
- `doubao/`：豆包/火山 websocket 翻译封装。
- `README.md`：当前只描述 Go + 火山 AST 的运行方式。
- `AGENT_GUIDE.md`：当前写着主要语言是 Go，并提示不要自动执行 Go 命令。
- `tasks/1-gemini-live-translation-python-init.md`：Gemini 备选方案计划，不是本任务的实现目标。
- 当前没有 `AGENTS.md` 或 `agents.md`；只有 `AGENT_GUIDE.md` 和空的 `AGENT_RULES.md`。

当前 Go 实现仅作为音频链路参考，不作为新实现的架构约束。新实现应优先保持 Python 原型独立、清晰、可删除。

## 3. OpenAI Realtime Translation 硬接口约束

以 OpenAI 官方 Realtime Translation 文档为准：

- 官方文档：https://developers.openai.com/api/docs/guides/realtime-translation
- 模型页：https://developers.openai.com/api/docs/models/gpt-realtime-translate
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
- 源流结束时必须先发 `session.close`，停止继续 append 音频，并继续读取事件直到收到 `session.closed`，再关闭 socket。

因此本任务的默认音频参数必须是：

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

本任务不实现自动重采样。若执行者确认 macOS/PortAudio 无法稳定以 24kHz 打开 AirPods 或 BlackHole，需要另开任务显式加入重采样模块，并配套测试；不得在本任务中悄悄把 48kHz 当成 24kHz 发送。

## 4. 分支和边界

推荐从当前 `main` 新建分支：

```bash
git checkout -b codex/openai-realtime-translation-python-init
```

本任务边界：

- 只初始化 Python 单向原型。
- 只实现 OpenAI Realtime Translation。
- 不实现 Gemini provider。
- 不实现豆包/火山 provider。
- 不实现 OpenAI voice-agent session。
- 不删除当前 Go/豆包代码。
- 不重写 git 历史。
- 不提交真实 API key。
- 不隐藏逻辑错误；设备找不到、采样率不支持、API key 缺失、OpenAI 连接失败、session event 不符合预期，都必须显式失败。
- 不为了测试通过而污染生产逻辑；如果测试导致奇怪写法，修改测试，不改不该改的生产行为。

## 5. 目标文件结构

建议新增或更新以下文件：

```text
.
├── .env.example
├── .gitignore
├── AGENT_GUIDE.md
├── AGENTS.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── src/
│   └── meeting_translator/
│       ├── __init__.py
│       ├── __main__.py
│       ├── audio_devices.py
│       ├── audio_io.py
│       ├── cli.py
│       ├── config.py
│       ├── openai_realtime_translate.py
│       ├── openai_events.py
│       ├── pcm.py
│       └── transcript_log.py
└── tests/
    ├── test_config.py
    ├── test_device_selection.py
    ├── test_openai_event_shapes.py
    └── test_pcm.py
```

说明：

- `src/meeting_translator/cli.py`：命令行入口，包含 `devices`、`check`、`run` 三个子命令。
- `audio_devices.py`：列出设备、按名称选择输入/输出设备、检查采样率/声道/dtype。
- `audio_io.py`：使用 `sounddevice.RawInputStream` 和 `sounddevice.RawOutputStream`；音频 callback 只负责把 bytes 放入队列，不做网络请求。
- `openai_realtime_translate.py`：连接 OpenAI Realtime Translation，发送 100ms PCM16 chunk，接收翻译音频与转写文本，负责 `session.close` 流程。
- `openai_events.py`：集中定义/解析 OpenAI translation session 事件。
- `pcm.py`：PCM16 little-endian 编解码、chunk 校验、base64 编码/解码。
- `transcript_log.py`：输出源语言和目标语言字幕日志，默认写到 `logs/`，日志文件不得包含 API key。
- `AGENTS.md`：如果新增 Python 技术栈，必须新增该文件或与现有 agent 规则保持同步；当前仓库没有该文件，因此本任务需要创建。
- `AGENT_GUIDE.md`：必须同步更新“主要语言”和验证命令，避免仍写成只有 Go。

## 6. Python 依赖

优先使用最小依赖，不引入 UI 框架：

```text
websockets
sounddevice
numpy
python-dotenv
pytest
ruff
```

说明：

- OpenAI 官方 Python 片段使用 `websocket-client` 展示协议形态；本任务建议用 `websockets`，因为本项目需要 asyncio queue 管理音频输入/输出。
- 若执行者选择 `websocket-client`，必须保证音频 callback 不直接做阻塞网络 I/O，并在任务报告中说明原因。

依赖文件：

- `requirements.txt`：锁定可运行的最小依赖范围。
- `pyproject.toml`：配置包名、Python 版本、pytest、ruff。

建议 Python 版本：

```text
Python >= 3.11
```

初始化命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

如果依赖下载失败，使用用户指定代理后重试同一条安装命令：

```bash
export http_proxy=http://127.0.0.1:1087;export https_proxy=http://127.0.0.1:1087;
python -m pip install -r requirements.txt
python -m pip install -e .
```

不要把代理写死进源码、配置文件或测试。

## 7. 配置约定

`.env.example` 必须只包含占位符：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_SAFETY_IDENTIFIER=local-user-hash-placeholder
MEETING_INPUT_DEVICE=AirPods 4
MEETING_OUTPUT_DEVICE=BlackHole 2ch
MEETING_TARGET_LANGUAGE=en
```

`.gitignore` 至少需要确保以下内容不入库：

```text
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
logs/
*.wav
*.pcm
```

CLI 参数优先级：

```text
命令行参数 > 环境变量 > .env > 默认值
```

但设备名不能有隐式兜底：

- 如果用户传了 `--input-device`，必须只匹配该设备；找不到就失败。
- 如果用户传了 `--output-device`，必须只匹配该设备；找不到就失败。
- 如果没有传且环境变量为空，`run` 必须失败并提示先执行 `devices` 或配置 `.env`。

OpenAI key 规则：

- `OPENAI_API_KEY` 缺失时，`check` 和 `run` 必须失败。
- 错误信息只允许写“OPENAI_API_KEY is missing”或等价信息，不能打印 key 值。
- `OPENAI_SAFETY_IDENTIFIER` 为空时可以使用本地固定占位值，但不得包含邮箱、姓名、会议号等可识别信息。

## 8. CLI 行为

### 8.1 列设备

命令：

```bash
python -m meeting_translator devices
```

输出必须包含：

- 设备 index
- 设备 name
- input channel count
- output channel count
- default sample rate
- 是否可作为输入/输出

### 8.2 检查单向链路

命令示例：

```bash
python -m meeting_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

检查内容：

- `OPENAI_API_KEY` 是否存在，但不能打印 key 值。
- 输入设备能否按 24kHz、mono、int16 打开。
- 输出设备能否按 24kHz、mono、int16 打开。
- 100ms chunk 大小是否为 4800 bytes。
- OpenAI 配置是否能构造为 `gpt-realtime-translate` + `/v1/realtime/translations`。
- `session.close` 关闭流程是否有实现入口。
- 不真正加入会议 app，不要求会议 app 正在运行。

### 8.3 运行单向翻译

命令示例：

```bash
OPENAI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

运行行为：

- 从 AirPods 4 读取 24kHz PCM16 mono。
- 每 100ms 发送一个 base64 PCM16 chunk 到 OpenAI Realtime Translation。
- 使用 `session.input_audio_buffer.append` 持续发送音频。
- 不调用 `response.create`。
- 接收 `session.output_audio.delta`，base64 解码后写入 BlackHole 2ch。
- 接收 `session.input_transcript.delta` 和 `session.output_transcript.delta` 并打印、写日志。
- Ctrl+C 或输入流结束时，先发送 `session.close`。
- 发送 `session.close` 后停止 append 音频，继续读取事件直到 `session.closed`。
- 收到 `session.closed` 后关闭 websocket、输入流、输出流。
- 关闭时写出本次日志摘要：开始时间、结束时间、输入设备、输出设备、目标语言、收到音频字节数、源字幕片段数、目标字幕片段数、错误状态。

## 9. 实现阶段

### 阶段 A：项目骨架

1. 创建 `src/meeting_translator/` 和 `tests/`。
2. 添加 `pyproject.toml`、`requirements.txt`。
3. 添加 `python -m meeting_translator` 入口。
4. 添加 `devices` 子命令，先只列设备。
5. 更新 `.env.example` 和 `.gitignore`。

验收：

```bash
source .venv/bin/activate
python -m meeting_translator devices
python -m pytest
python -m ruff check .
```

### 阶段 B：设备选择和音频 I/O

1. 实现输入设备按名称选择，输出设备按名称选择。
2. 实现 `check` 子命令。
3. 实现 RawInputStream -> asyncio queue。
4. 实现 asyncio queue -> RawOutputStream。
5. 明确禁止输入流和输出流混成同一个 pass-through；本 app 不应把会议 app 输出转发到 AirPods。

验收：

```bash
python -m meeting_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
python -m pytest
python -m ruff check .
```

如果本机设备名不是精确的 `AirPods 4`，先执行 `python -m meeting_translator devices`，用实际设备名重跑 `check`。不得在代码里硬编码开发者个人设备名。

### 阶段 C：OpenAI Realtime Translation

1. 使用 `websockets` 连接 `wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate`。
2. 设置 header：
   - `Authorization: Bearer ${OPENAI_API_KEY}`
   - `OpenAI-Safety-Identifier: ${OPENAI_SAFETY_IDENTIFIER}`
3. socket 打开后发送 `session.update`：
   - `session.audio.output.language="en"`
4. 将 100ms PCM16 chunk base64 后发送：
   - `type="session.input_audio_buffer.append"`
   - `audio=<base64_pcm16>`
5. 接收并处理：
   - `session.output_audio.delta`
   - `session.output_transcript.delta`
   - `session.input_transcript.delta`
   - `session.closed`
6. Ctrl+C 或输入流结束时发送：
   - `type="session.close"`
7. `session.close` 后不得继续 append 音频。
8. 等到 `session.closed` 后再关闭 socket。
9. 连接错误、认证错误、消息结构未知时显式失败。

验收：

```bash
OPENAI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

人工验收：

1. macOS 系统输出不要选择 BlackHole。
2. 会议 app 麦克风选择 BlackHole 2ch。
3. 会议 app 扬声器选择 AirPods 4。
4. 对 AirPods 4 麦克风说中文。
5. 会议 app 麦克风测试或对端应收到英文翻译语音。
6. 停掉本 app 后，BlackHole 不再收到翻译语音；但会议 app 的 AirPods 4 输出不应受本 app 接管。

### 阶段 D：文档和协作规则同步

1. 更新 `README.md`：
   - 新增 Python + OpenAI Realtime Translation 单向原型运行说明。
   - 保留旧 Go/豆包说明，标注为 legacy/reference。
   - 明确 `tasks/1-gemini-live-translation-python-init.md` 是备选方案，不是当前实现目标。
   - 写清会议 app 的麦克风/扬声器设置。
2. 创建 `AGENTS.md`：
   - 写明本仓库现在包含 legacy Go 和 Python prototype。
   - 写明当前优先 provider 是 OpenAI Realtime Translation。
   - 写明 Python 验证命令。
   - 写明不得提交 `.env`、真实 API key、会议日志音频。
   - 写明依赖下载失败时使用用户指定代理。
3. 更新 `AGENT_GUIDE.md`：
   - 项目主要方向改为 macOS 单向实时会议翻译。
   - 记录 Python 原型和 legacy Go 的边界。
   - 记录 OpenAI 方案为当前优先任务。
   - 删除或修正“不要自动执行任何 go 相关命令”对 Python 任务的误导；Go 命令限制可保留为 legacy Go 注意事项。

验收：

```bash
python -m pytest
python -m ruff check .
git diff --check
```

## 10. 测试要求

必须有单元测试：

- `test_config.py`
  - 环境变量和命令行参数优先级。
  - 缺少 `OPENAI_API_KEY` 时 `run`/`check` 的错误信息不泄露 key。
  - `OPENAI_SAFETY_IDENTIFIER` 为空时使用不可识别占位值。
- `test_device_selection.py`
  - 精确设备名匹配。
  - 找不到输入设备时显式错误。
  - 找不到输出设备时显式错误。
  - 不允许静默选择默认设备。
- `test_pcm.py`
  - 24kHz、100ms、mono、int16 的 chunk 必须是 4800 bytes。
  - base64 编码/解码后 bytes 不变。
  - 非 100ms chunk 在发送前失败。
- `test_openai_event_shapes.py`
  - `session.input_transcript.delta` 能解析。
  - `session.output_transcript.delta` 能解析。
  - `session.output_audio.delta` 能 base64 解码并写入输出队列。
  - `session.closed` 能触发 socket 关闭状态。
  - `session.close` 后不得继续发送 `session.input_audio_buffer.append`。
  - 未知关键消息结构显式错误或记录为 unsupported event，不得吞掉。

如果测试迫使生产代码出现不自然的测试专用分支，应优先修改测试设计。不要为了测试写不该存在的生产兜底逻辑。

## 11. 验证命令清单

实现者完成后必须至少运行：

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
  --target-language en
git diff --check
git status --short
```

如果依赖下载失败，使用代理后重试：

```bash
export http_proxy=http://127.0.0.1:1087;export https_proxy=http://127.0.0.1:1087;
python -m pip install -r requirements.txt
python -m pip install -e .
```

如果 OpenAI 联网运行失败，报告必须区分：

- 依赖安装失败
- DNS/代理/网络失败
- API key 缺失
- API key 无权限
- OpenAI Realtime Translation 返回错误
- 音频设备打不开
- 24kHz 采样率不支持
- 人工会议链路未验收

不要把这些失败统一写成“运行失败”。

## 12. 安全和提交前检查

提交前必须检查：

```bash
rg -n --hidden -g '!.git' -e 'OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
git status --short
```

要求：

- `.env` 不得入库。
- 真实 OpenAI API key 不得出现在源码、README、任务报告、测试 fixture、日志中。
- `OPENAI_SAFETY_IDENTIFIER` 不得包含邮箱、姓名、会议号等可识别信息。
- 会议音频、PCM、WAV、字幕日志默认不入库。
- `.env.example` 只能写占位符。

## 13. 任务报告要求

任务完成后必须写中文报告，路径格式：

```text
tasks/2-openai-realtime-translation-python-init-[utctime].md
```

其中 `[utctime]` 使用 UTC 时间，格式为 `yymmdd-HHMMSS`，例如：

```bash
date -u +%y%m%d-%H%M%S
```

报告至少包含：

- 实际变更文件清单。
- 最终音频链路说明。
- OpenAI 模型、endpoint 和音频参数。
- 是否使用 `/v1/realtime/translations`，确认没有使用 `/v1/realtime`。
- 是否实现 `session.close` -> 等待 `session.closed` 的关闭流程。
- 运行过的命令和结果摘要。
- 依赖安装是否使用代理。
- 单元测试结果。
- ruff 结果。
- `devices` 输出中实际使用的输入/输出设备名。
- `check` 子命令结果。
- `run` 人工验收结果；如果无法人工验收，说明缺少的设备/API key/会议 app 条件。
- 是否创建/更新 `AGENTS.md` 和 `AGENT_GUIDE.md`。
- 安全扫描结果，明确是否发现真实 API key。
- 未完成事项和下一步建议。

## 14. 完成标准

本任务完成必须同时满足：

- `tasks/2-openai-realtime-translation-python-init.md` 中定义的 Python 原型文件已落地。
- `python -m pytest` 通过。
- `python -m ruff check .` 通过。
- `python -m meeting_translator devices` 可列出设备。
- `python -m meeting_translator check --input-device ... --output-device ... --target-language en` 对实际设备给出明确通过或明确失败原因。
- OpenAI 连接代码存在，并能在有 `OPENAI_API_KEY` 时按 `gpt-realtime-translate` 配置运行。
- 连接 endpoint 是 `/v1/realtime/translations`。
- 不调用 `response.create`。
- 发送音频事件使用 `session.input_audio_buffer.append`。
- 关闭流程使用 `session.close` 并等待 `session.closed`。
- 没有把真实 API key、`.env`、音频日志提交进仓库。
- `README.md`、`AGENTS.md`、`AGENT_GUIDE.md` 已与 Python + OpenAI 单向原型同步。
- 已写任务报告 `tasks/2-openai-realtime-translation-python-init-[utctime].md`。

## 15. 二次遗漏检查

交付前执行一次专门的遗漏检查，逐项确认：

- 当前 Go/豆包代码未被误删。
- `tasks/1-gemini-live-translation-python-init.md` 没有被误当成当前实现目标。
- 新 Python 代码没有硬编码个人设备名。
- 输入设备和输出设备没有被设计成 pass-through 混音。
- 停止 app 只停止翻译链路，不接管会议 app 的 AirPods 输出。
- OpenAI 输入/输出采样率符合 WebSocket 24kHz PCM16 约束。
- 100ms chunk 的大小和发送节奏有测试覆盖。
- 缺 key、缺设备、采样率不支持都会显式失败。
- 没有引入不必要 provider 抽象；本任务只实现 OpenAI。
- 没有为了测试通过加入隐藏 fallback。
- 文档和 agent 规则没有互相冲突。
- 任务报告文件名使用 UTC 时间。
