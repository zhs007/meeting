# 任务 1：Gemini Live Translation Python 单向实时翻译初始化

## 1. 任务目标

在本仓库 `/Users/zerro/github.com/meeting` 中，基于新分支初始化一个 Python 原型项目，用 Gemini Live Translation 实现单向实时同声传译：

```text
AirPods 4 麦克风中文语音
  -> meeting Python app
  -> Gemini Live Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本任务只做单向链路，不做双向翻译，不接管会议 app 的扬声器输出。会议 app 的输出设备应由会议 app 自己设置为 AirPods 4。

## 2. 当前仓库事实

当前仓库是 Go 项目，主要文件如下：

- `main.go`：当前入口，读取豆包/火山相关 `APP_ID`、`APP_KEY`、`ACCESS_KEY`，默认 endpoint 是 `v4/ast/v2/translate`。
- `business_v4.go`：当前翻译主流程，硬编码 `audio.Init("MacBook Air麦克风", "BlackHole 2ch", 16000, 1, 16, 80*time.Millisecond, chanIn)`。
- `audio/`：基于 PortAudio 的输入/输出封装。
- `doubao/`：豆包/火山 websocket 翻译封装。
- `README.md`：当前只描述 Go + 火山 AST 的运行方式。
- `AGENT_GUIDE.md`：当前写着主要语言是 Go，并提示不要自动执行 Go 命令。
- 当前没有 `tasks/` 历史任务文件；本文件是 `tasks/` 下第一个任务。
- 当前没有 `AGENTS.md` 或 `agents.md`；只有 `AGENT_GUIDE.md` 和空的 `AGENT_RULES.md`。

当前 Go 实现仅作为音频链路参考，不作为新实现的架构约束。新实现应优先保持 Python 原型独立、清晰、可删除。

## 3. Gemini Live Translation 硬接口约束

以 Google 官方 Gemini Live Translation 文档为准：

- 官方文档：https://ai.google.dev/gemini-api/docs/live-api/live-translate
- 模型：`gemini-3.5-live-translate-preview`
- 输入：raw 16-bit PCM、16kHz、mono、little-endian。
- 输出：raw 16-bit PCM、24kHz、mono、little-endian。
- chunk：按 100ms 音频块发送。
- 翻译配置：使用 `translationConfig.targetLanguageCode`，本任务默认目标语言为 `en`。
- 限制：Live Translation 只支持音频输入，不支持文本输入；voice replication 不稳定，不作为验收标准。

因此本任务的默认音频参数必须是：

```text
input_sample_rate = 16000
input_channels = 1
input_dtype = int16
input_chunk_ms = 100
input_samples_per_chunk = 1600

output_sample_rate = 24000
output_channels = 1
output_dtype = int16
```

如果 AirPods 4 或 BlackHole 2ch 不能按上述参数打开，应显式失败并打印设备、采样率、声道、dtype，不允许静默降级到别的采样率或别的设备。

## 4. 分支和边界

推荐从当前 `main` 新建分支：

```bash
git checkout -b codex/gemini-live-translation-python-init
```

本任务边界：

- 只初始化 Python 单向原型。
- 只实现 Gemini Live Translation provider。
- 不实现 OpenAI provider。
- 不删除当前 Go/豆包代码。
- 不重写 git 历史。
- 不提交真实 API key。
- 不隐藏逻辑错误；设备找不到、采样率不支持、API key 缺失、Gemini 连接失败，都必须显式失败。
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
│       ├── gemini_live_translate.py
│       ├── pcm.py
│       └── transcript_log.py
└── tests/
    ├── test_config.py
    ├── test_device_selection.py
    ├── test_gemini_message_shapes.py
    └── test_pcm.py
```

说明：

- `src/meeting_translator/cli.py`：命令行入口，包含 `devices`、`check`、`run` 三个子命令。
- `audio_devices.py`：列出设备、按名称选择输入/输出设备、检查采样率/声道/dtype。
- `audio_io.py`：使用 `sounddevice.RawInputStream` 和 `sounddevice.RawOutputStream`；音频 callback 只负责把 bytes 放入队列，不做网络请求。
- `gemini_live_translate.py`：连接 Gemini Live Translation，发送 100ms PCM16 chunk，接收翻译音频与转写文本。
- `pcm.py`：PCM16 little-endian 编解码、chunk 校验、base64 编码/解码。
- `transcript_log.py`：输出源语言和目标语言字幕日志，默认写到 `logs/`，日志文件不得包含 API key。
- `AGENTS.md`：如果新增 Python 技术栈，必须新增该文件或与现有 agent 规则保持同步；当前仓库没有该文件，因此本任务需要创建。
- `AGENT_GUIDE.md`：必须同步更新“主要语言”和验证命令，避免仍写成只有 Go。

## 6. Python 依赖

优先使用最小依赖，不引入 UI 框架：

```text
google-genai
sounddevice
numpy
python-dotenv
pytest
ruff
```

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
GEMINI_API_KEY=your_gemini_api_key_here
MEETING_INPUT_DEVICE=AirPods 4
MEETING_OUTPUT_DEVICE=BlackHole 2ch
MEETING_TARGET_LANGUAGE=en
MEETING_ECHO_TARGET_LANGUAGE=false
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

- `GEMINI_API_KEY` 是否存在，但不能打印 key 值。
- 输入设备能否按 16kHz、mono、int16 打开。
- 输出设备能否按 24kHz、mono、int16 打开。
- 100ms chunk 大小是否为 3200 bytes。
- Gemini 配置是否能构造为 `gemini-3.5-live-translate-preview` + `target_language_code=en`。
- 不真正加入会议 app，不要求会议 app 正在运行。

### 8.3 运行单向翻译

命令示例：

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

运行行为：

- 从 AirPods 4 读取 16kHz PCM16 mono。
- 每 100ms 发送一个音频 chunk 到 Gemini Live Translation。
- 接收 Gemini 输出的 24kHz PCM16 mono 音频。
- 将输出音频写入 BlackHole 2ch。
- 同时打印 input transcript 和 output transcript。
- Ctrl+C 时有序关闭输入流、输出流和 Gemini session。
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

### 阶段 C：Gemini Live Translation

1. 使用 `google-genai` 连接 `gemini-3.5-live-translate-preview`。
2. 配置：
   - `response_modalities=["AUDIO"]`
   - `input_audio_transcription`
   - `output_audio_transcription`
   - `translation_config.target_language_code="en"`
   - `translation_config.echo_target_language=false`
3. 将 100ms PCM16 chunk 发送为 `audio/pcm;rate=16000`。
4. 接收 output audio chunk 并写入 BlackHole。
5. 接收 input/output transcript 并打印、写日志。
6. 连接错误、认证错误、消息结构未知时显式失败。

验收：

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
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
   - 新增 Python + Gemini 单向原型运行说明。
   - 保留旧 Go/豆包说明，标注为 legacy/reference。
   - 写清会议 app 的麦克风/扬声器设置。
2. 创建 `AGENTS.md`：
   - 写明本仓库现在包含 legacy Go 和 Python prototype。
   - 写明 Python 验证命令。
   - 写明不得提交 `.env`、真实 API key、会议日志音频。
   - 写明依赖下载失败时使用用户指定代理。
3. 更新 `AGENT_GUIDE.md`：
   - 项目主要方向改为 macOS 单向实时会议翻译。
   - 记录 Python 原型和 legacy Go 的边界。
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
  - 缺少 `GEMINI_API_KEY` 时 `run`/`check` 的错误信息不泄露 key。
- `test_device_selection.py`
  - 精确设备名匹配。
  - 找不到输入设备时显式错误。
  - 找不到输出设备时显式错误。
  - 不允许静默选择默认设备。
- `test_pcm.py`
  - 16kHz、100ms、mono、int16 的 chunk 必须是 3200 bytes。
  - base64 编码/解码后 bytes 不变。
  - 非 100ms chunk 在发送前失败。
- `test_gemini_message_shapes.py`
  - fake input transcript event 能解析。
  - fake output transcript event 能解析。
  - fake output audio event 能写入输出队列。
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

如果 Gemini 联网运行失败，报告必须区分：

- 依赖安装失败
- DNS/代理/网络失败
- API key 缺失
- API key 无权限
- Gemini Live API 返回错误
- 音频设备打不开
- 人工会议链路未验收

不要把这些失败统一写成“运行失败”。

## 12. 安全和提交前检查

提交前必须检查：

```bash
rg -n --hidden -g '!.git' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
git status --short
```

要求：

- `.env` 不得入库。
- 真实 Gemini API key 不得出现在源码、README、任务报告、测试 fixture、日志中。
- 会议音频、PCM、WAV、字幕日志默认不入库。
- `.env.example` 只能写占位符。

## 13. 任务报告要求

任务完成后必须写中文报告，路径格式：

```text
tasks/1-gemini-live-translation-python-init-[utctime].md
```

其中 `[utctime]` 使用 UTC 时间，格式为 `yymmdd-HHMMSS`，例如：

```bash
date -u +%y%m%d-%H%M%S
```

报告至少包含：

- 实际变更文件清单。
- 最终音频链路说明。
- Gemini 模型和音频参数。
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

- `tasks/1-gemini-live-translation-python-init.md` 中定义的 Python 原型文件已落地。
- `python -m pytest` 通过。
- `python -m ruff check .` 通过。
- `python -m meeting_translator devices` 可列出设备。
- `python -m meeting_translator check --input-device ... --output-device ... --target-language en` 对实际设备给出明确通过或明确失败原因。
- Gemini 连接代码存在，并能在有 `GEMINI_API_KEY` 时按 `gemini-3.5-live-translate-preview` 配置运行。
- 没有把真实 API key、`.env`、音频日志提交进仓库。
- `README.md`、`AGENTS.md`、`AGENT_GUIDE.md` 已与 Python + Gemini 单向原型同步。
- 已写任务报告 `tasks/1-gemini-live-translation-python-init-[utctime].md`。

## 15. 二次遗漏检查

交付前执行一次专门的遗漏检查，逐项确认：

- 当前 Go/豆包代码未被误删。
- 新 Python 代码没有硬编码个人设备名。
- 输入设备和输出设备没有被设计成 pass-through 混音。
- 停止 app 只停止翻译链路，不接管会议 app 的 AirPods 输出。
- Gemini 输入/输出采样率符合官方约束。
- 100ms chunk 的大小和发送节奏有测试覆盖。
- 缺 key、缺设备、采样率不支持都会显式失败。
- 没有引入不必要 provider 抽象；本任务只实现 Gemini。
- 没有为了测试通过加入隐藏 fallback。
- 文档和 agent 规则没有互相冲突。
- 任务报告文件名使用 UTC 时间。
