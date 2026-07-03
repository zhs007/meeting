# 任务 3：Low Latency Live Translation 稳定化

## 1. 任务目标

在本仓库 `/Users/zerro/github.com/meeting` 中，基于当前 Python + Gemini Live Translation 单向会议翻译原型，降低端到端延迟并稳定长会议运行。

当前目标链路保持不变：

```text
AirPods / 本机麦克风中文或日文语音
  -> meeting Python app
  -> Gemini Live Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> Teams / 会议 app 的麦克风输入
```

本任务必须解决或明确诊断以下已观察问题：

1. Teams 已经能听到 Gemini 翻译语音，但体感延迟约 5 秒。
2. 当前实现中 `output_queue=maxsize=50`、`RawAudioOutput.thread_queue_size=50`，按 100ms 音频 chunk 估算，单个队列理论上可积压约 5 秒音频。
3. Gemini Live session 约 10 分钟会收到 `GoAway`；客户端必须主动关闭或重连，不能等服务端用 `1008 policy violation` 强断。
4. 仍然可能出现 `Unsupported Gemini event: unrecognized Gemini response shape`；必须区分正常控制事件、可忽略空事件、真正未知协议事件。
5. Ctrl+C / SIGTERM 必须能在合理时间内退出，不允许需要连续多次 Ctrl+C 或手动 kill。

本任务不是重新初始化 Python 项目，不切换 OpenAI 路线，不删除 legacy Go/豆包代码。

## 2. 当前仓库事实

仓库根目录：

```text
/Users/zerro/github.com/meeting
```

当前核心文件：

- `src/meeting_translator/cli.py`
  - `run_command` 创建：
    - `input_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)`
    - `output_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)`
  - 启动 `RawAudioInput`、`RawAudioOutput`、`run_live_translation`。
  - 负责 Ctrl+C / SIGTERM 的 `shutdown_event`。
- `src/meeting_translator/audio_io.py`
  - `RawAudioInput` 使用 `sounddevice.RawInputStream`。
  - 输入参数：16kHz、mono、int16、100ms chunk。
  - `RawAudioOutput` 使用 `sounddevice.RawOutputStream`。
  - 输出参数：24kHz、mono、int16。
  - 当前输出 stream `blocksize=1200`，对应 24kHz 下约 50ms。
  - 当前 `RawAudioOutput.thread_queue_size=50`。
  - 当前已有 `_playback_buffer`，用于跨 sounddevice callback 保留剩余音频，避免截断。
- `src/meeting_translator/gemini_live_translate.py`
  - 模型：`gemini-3.5-live-translate-preview`。
  - 使用 `send_realtime_input(audio=types.Blob(..., mime_type="audio/pcm;rate=16000"))`。
  - 已解析 input transcript、output transcript、inline audio。
  - 已有 `go_away_time_left(response)`。
  - 收到 GoAway 时当前行为是设置 `shutdown_event` 并结束当前 session；尚未自动重连。
- `src/meeting_translator/transcript_log.py`
  - 记录运行摘要和字幕片段数，默认写入 `logs/`。
- `tests/test_audio_io.py`
  - 已覆盖输出 callback 不能截断跨 callback 的 chunk。
- `tests/test_gemini_message_shapes.py`
  - 已覆盖 transcript、output audio、GoAway timeLeft、部分控制消息解析。
- `README.md`
  - 已描述 Python + Gemini 单向翻译启动方式。
- `AGENTS.md`
  - 已写明 Python 原型、legacy Go 边界、验证命令和安全规则。

当前已知真实运行结果：

- Teams / 会议 app 已能听到翻译语音。
- `received_audio_bytes` 可持续增长。
- `input_transcript_segments` / `output_transcript_segments` 可持续增长。
- 约 10 分钟后 Gemini 连接会触发 session 生命周期相关事件。

## 3. 硬约束

### 3.1 音频参数

Gemini Live Translation 仍使用当前任务 1 约定参数：

```text
input_sample_rate = 16000
input_channels = 1
input_dtype = int16
input_chunk_ms = 100
input_bytes_per_chunk = 3200

output_sample_rate = 24000
output_channels = 1
output_dtype = int16
```

本任务不得悄悄改采样率、声道或 dtype。

### 3.2 失败策略

必须保留显式失败，不允许隐藏逻辑 bug：

- 缺 `GEMINI_API_KEY` 必须失败，不能打印 key 值。
- 输入/输出设备找不到必须失败。
- 设备不能按指定采样率、声道、dtype 打开必须失败。
- Gemini 认证、网络、协议错误必须分类记录。
- 如果输入音频队列持续溢出，不能静默吞掉；必须显式计数并在默认策略下失败或给出清晰错误状态。
- 输出音频为降低延迟而丢弃旧块时，必须是明确的低延迟策略，并在 summary 中记录丢弃数量；不得伪装为“正常播放成功”。

### 3.3 测试边界

如果测试导致生产代码出现奇怪写法，优先修改测试，不改不该改的生产行为。

不允许为了测试方便加入生产环境不会使用的隐藏 fallback。

### 3.4 安全边界

不得提交：

- `.env`
- 真实 Gemini API key
- 会议音频
- `.pcm` / `.wav`
- `logs/` 下的真实会议字幕日志或运行摘要

## 4. 本任务不做什么

- 不删除当前 Go/豆包代码。
- 不实现 OpenAI provider。
- 不切换到 `tasks/2-openai-realtime-translation-python-init.md`。
- 不实现双向翻译。
- 不接管会议 app 的扬声器输出。
- 不把 macOS 系统输出改成 BlackHole。
- 不为了降低延迟引入 UI、数据库、后台服务或常驻 daemon。
- 不把代理写入源码、`.env.example` 或测试。

## 5. 目标结果

完成后应达到：

1. 默认运行模式的本地音频积压上限明显低于当前 5 秒。
2. 如果 Gemini / 网络 / Teams 导致真实端到端延迟仍高，程序能打印足够的队列和时间指标用于定位，而不是只凭体感猜测。
3. 收到 Gemini `GoAway` 后不会再触发 `1008 policy violation`。
4. 长会议可选择自动重连 Gemini Live session，且不会把旧输出音频继续慢慢播给 Teams。
5. Ctrl+C 一次即可触发有序关闭；正常情况下 3 秒内完成退出摘要。
6. `python -m pytest`、`python -m ruff check .`、`git diff --check` 通过。
7. README / AGENTS.md 如有新配置或新验收命令，必须同步更新。
8. 写中文任务报告到 `tasks/3-low-latency-live-translation-[utctime].md`。

## 6. 建议实现方案

### 阶段 A：低延迟配置与运行参数

新增或更新以下配置：

```text
MEETING_INPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_THREAD_QUEUE_CHUNKS=8
MEETING_MAX_PLAYBACK_BUFFER_MS=800
MEETING_METRICS_INTERVAL_SEC=10
MEETING_AUTO_RECONNECT=true
MEETING_MAX_RECONNECTS=0
```

说明：

- `MEETING_INPUT_QUEUE_CHUNKS`
  - 输入侧 100ms chunk 队列上限。
  - 默认建议 8，即最多约 800ms。
  - 输入队列满说明发送侧追不上采集侧；默认应显式失败或停止本次 session，不应静默积压到数秒。
- `MEETING_OUTPUT_QUEUE_CHUNKS`
  - Gemini receiver 到 audio output pump 之间的 asyncio 队列上限。
  - 默认建议 8。
- `MEETING_OUTPUT_THREAD_QUEUE_CHUNKS`
  - audio output pump 到 sounddevice callback 之间的线程队列上限。
  - 默认建议 8。
- `MEETING_MAX_PLAYBACK_BUFFER_MS`
  - `_playback_buffer` 最大保留时长。
  - 超过时说明播放落后，应按明确低延迟策略丢弃旧音频并计数。
- `MEETING_METRICS_INTERVAL_SEC`
  - 周期性打印队列深度和延迟诊断。
  - 设为 `0` 可关闭周期指标。
- `MEETING_AUTO_RECONNECT`
  - 收到 GoAway 或正常 session 到期时是否自动重连。
  - 默认建议 `true`。
- `MEETING_MAX_RECONNECTS`
  - `0` 表示不限制重连次数。
  - 大于 0 时达到上限必须显式结束并写 summary。

需要更新：

- `src/meeting_translator/config.py`
  - 增加上述配置字段和解析。
  - 布尔和整数解析必须显式校验；非法值失败。
- `src/meeting_translator/cli.py`
  - 增加对应 CLI 参数：
    - `--input-queue-chunks`
    - `--output-queue-chunks`
    - `--output-thread-queue-chunks`
    - `--max-playback-buffer-ms`
    - `--metrics-interval-sec`
    - `--auto-reconnect / --no-auto-reconnect`
    - `--max-reconnects`
  - 优先级仍是：

```text
命令行参数 > 环境变量 > .env > 默认值
```

`.env.example` 应增加占位默认值，但不得写真实 key。

### 阶段 B：输出播放队列低延迟化

更新 `src/meeting_translator/audio_io.py`：

1. 把 `RawAudioOutput.thread_queue_size` 从固定默认 50 改为由配置传入。
2. 给 `RawAudioOutput` 增加可测试的低延迟队列策略：
   - 当 output asyncio queue 满时，不无限等待。
   - 当 thread queue 满时，按明确策略丢弃旧音频块，优先播放最新块。
   - `_playback_buffer` 超过 `MEETING_MAX_PLAYBACK_BUFFER_MS` 时，丢弃最旧音频并记录字节数/毫秒数。
3. 新增 stats 字段：
   - `output_dropped_chunks`
   - `output_dropped_bytes`
   - `output_max_async_queue_depth`
   - `output_max_thread_queue_depth`
   - `output_max_playback_buffer_ms`
4. 停止时 summary 必须输出这些统计。
5. 输出 callback 中不得做阻塞网络 I/O，不得 await，不得打印高频日志。

验收要点：

- 任何单个输出队列默认都不能再允许约 5 秒积压。
- 降低延迟的丢弃行为必须可见、可计数。
- 不能重新引入音频截断 bug；跨 callback 的剩余音频仍必须保留。

### 阶段 C：输入队列显式背压

更新 `src/meeting_translator/audio_io.py` 和 `src/meeting_translator/cli.py`：

1. `input_queue` 默认从 50 降到 8。
2. `RawAudioInput` 在 queue full 时：
   - 默认记录 `input_overflows`。
   - 设置一个可被主 loop 读取的错误状态，触发显式停止；不要继续沉默运行。
3. 如果后续确实需要“丢旧输入保实时”，必须作为单独显式模式实现，例如 `--drop-old-input-on-overflow`，默认不启用。

验收要点：

- 网络或 Gemini 发送卡住时不会把本地麦克风音频积压成多秒延迟。
- 输入溢出不是隐藏 fallback。

### 阶段 D：GoAway 自动重连

更新 `src/meeting_translator/gemini_live_translate.py`：

1. 把当前单 session 函数拆清楚：
   - `run_single_live_translation_session(...)`
   - `run_live_translation(...)` 作为外层重连循环。
2. 收到 GoAway 时：
   - 打印 `Gemini sent GoAway; reconnecting before timeout. time_left=...`。
   - 停止当前 sender/receiver。
   - 关闭当前 websocket session。
   - 清理旧输出队列中的陈旧音频。
   - 如果 `MEETING_AUTO_RECONNECT=true`，启动新 session。
   - 如果 `MEETING_AUTO_RECONNECT=false`，正常结束，summary 的 `error_status` 应为 `None` 或明确的 `closed_after_goaway`，不能作为 unexpected error。
3. 如果 SDK 提供 `session_resumption_update` handle：
   - 可以记录 handle 和 resumable 状态。
   - 是否使用 handle 重连必须谨慎验证；如果未实现，不要假装已支持 session resumption。
   - 翻译链路本身不依赖跨 session 长上下文，优先保证低延迟和稳定关闭。
4. 连续重连失败必须显式失败，并区分：
   - DNS/代理/网络失败
   - 认证失败
   - Gemini policy / quota / rate limit
   - SDK websocket 关闭

验收要点：

- 运行超过 10 分钟时，不再出现 `1008 policy violation`。
- 12 分钟人工运行时，如果收到 GoAway，应自动重连或正常结束，不能崩成 unexpected error。

### 阶段 E：协议事件解析收敛

更新 `src/meeting_translator/gemini_live_translate.py`：

1. 已知控制事件必须静默或低频 debug 记录：
   - `setupComplete`
   - `usageMetadata`
   - `goAway`
   - `sessionResumptionUpdate`
   - `voiceActivity`
   - `voiceActivityDetectionSignal`
   - `serverContent.turnComplete`
   - `serverContent.generationComplete`
   - `serverContent.waitingForInput`
   - `inputTranscription.finished`
   - `outputTranscription.finished`
2. 真正未知事件默认不要高频刷屏。
   - 建议增加 `MEETING_DEBUG_EVENTS=false` / `--debug-events`。
   - 默认只汇总未知事件计数和首个样例。
   - 开启 debug 时才打印完整未知结构，但不得打印 API key。
3. 如果未知结构包含音频或字幕字段但解析失败，应显式失败或至少在 summary 中标记 `unsupported_event_count`，不能吞掉。

验收要点：

- 正常会议过程中不刷 `Unsupported Gemini event`。
- 真正未知协议事件仍有诊断证据。

### 阶段 F：延迟指标与手工验收辅助

新增或更新：

- `src/meeting_translator/audio_io.py`
- `src/meeting_translator/gemini_live_translate.py`
- `src/meeting_translator/transcript_log.py`

建议统计：

```text
input_chunks_captured
input_chunks_sent
output_audio_chunks_received
output_audio_bytes_received
output_audio_chunks_played
input_queue_depth_current/max
output_queue_depth_current/max
thread_queue_depth_current/max
playback_buffer_ms_current/max
output_dropped_chunks/bytes
goaway_count
reconnect_count
session_count
```

周期输出示例：

```text
metrics: input_q=0/8 output_q=1/8 thread_q=2/8 playback_buffer_ms=120 dropped_output=0 reconnects=0
```

关闭 summary 必须包含上述关键字段。

手工验收方式：

1. Teams 麦克风选择 BlackHole 2ch。
2. Teams 扬声器选择 AirPods。
3. macOS 系统输出不要选择 BlackHole。
4. 说短句：
   - `你好，今天我们测试低延迟。`
   - `请确认英文声音什么时候出来。`
5. 用秒表或屏幕录制估计从说完短句到 Teams 麦克风测试听到英文的时间。
6. 记录：
   - 原始版本延迟估计
   - 本任务完成后延迟估计
   - metrics 中最大队列深度
   - 是否发生 output drop

目标：

- 短句端到端体感延迟优先目标：小于 2 秒。
- 如果模型/VAD 导致无法小于 2 秒，必须证明本地队列没有积压到多秒，并在报告中记录真实瓶颈。

## 7. 测试要求

必须新增或更新单元测试。

### 7.1 `tests/test_config.py`

覆盖：

- 新增整数配置的命令行 > 环境变量 > `.env` > 默认值优先级。
- 非正整数失败，例如 `MEETING_OUTPUT_QUEUE_CHUNKS=0`。
- 非法布尔值失败，例如 `MEETING_AUTO_RECONNECT=maybe`。
- 缺 key 仍不泄露 key 值。

### 7.2 `tests/test_audio_io.py`

覆盖：

- 输出 callback 继续保留跨 callback 剩余音频，不能截断。
- thread queue 满时按低延迟策略丢弃旧音频并计数。
- `_playback_buffer` 超过 `max_playback_buffer_ms` 时丢弃旧音频并计数。
- 默认配置下理论最大输出队列积压不得达到 5 秒。
- 输入 queue full 时必须记录 overflow，并能触发显式失败信号。

### 7.3 `tests/test_gemini_message_shapes.py`

覆盖：

- GoAway 事件解析 `timeLeft`。
- GoAway 触发 session 正常关闭或重连控制流。
- `usageMetadata`、`setupComplete`、`sessionResumptionUpdate`、`voiceActivity`、transcription finished 空事件不刷 unsupported。
- 真正未知结构计数，不高频刷屏。

### 7.4 新增 `tests/test_reconnect.py` 或等价测试

使用 fake session / fake client，不连真实 Gemini。

覆盖：

- 第一轮 fake session 发 GoAway 后，外层 run loop 创建第二轮 session。
- `MEETING_AUTO_RECONNECT=false` 时 GoAway 后正常结束。
- 达到 `MEETING_MAX_RECONNECTS` 后显式结束并写明原因。
- 重连时清理旧输出队列，避免把上一 session 的陈旧音频继续播给 Teams。

### 7.5 测试设计要求

如果为了测试 fake session 导致生产代码出现奇怪入口或测试专用分支，应改测试，不要污染生产逻辑。

生产代码可以通过依赖注入接收 session factory，但该抽象必须服务于真实重连逻辑，不只是为了测试。

## 8. 文档和协作规则同步

如果新增低延迟配置、重连配置、metrics 输出或 debug event 开关，必须更新：

- `README.md`
  - 增加低延迟运行说明。
  - 解释 5 秒延迟不一定是网络，先看队列和 metrics。
  - 写明 Gemini session 约 10 分钟连接生命周期，以及 GoAway 自动重连行为。
  - 写明 Teams / BlackHole 设置。
- `AGENTS.md`
  - 增加本任务相关验证命令。
  - 增加低延迟策略约束：输出丢弃必须可计数，输入溢出不得静默兜底。
  - 保留不删除 legacy Go/豆包代码的边界。
- `.env.example`
  - 增加低延迟和重连配置的占位默认值。

如果没有修改这些文件，任务报告必须解释为什么不需要同步。

## 9. 验证命令

基础验证：

```bash
source .venv/bin/activate
python -m pytest
python -m ruff check .
python -m meeting_translator devices
python -m meeting_translator check \
  --input-device "Zerro的AirPods" \
  --output-device "BlackHole 2ch" \
  --target-language en
git diff --check
git status --short
```

如果本机设备名不同，先运行：

```bash
python -m meeting_translator devices
```

再使用实际设备名重跑 `check`。不得在代码里硬编码 `Zerro的AirPods` 或任何个人设备名。

依赖安装如失败，使用用户指定代理后重试同一条安装命令：

```bash
export http_proxy=http://127.0.0.1:1087;export https_proxy=http://127.0.0.1:1087;
python -m pip install -r requirements.txt
python -m pip install -e .
```

低延迟人工验收建议命令：

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "Zerro的AirPods" \
  --output-device "BlackHole 2ch" \
  --target-language en \
  --input-queue-chunks 8 \
  --output-queue-chunks 8 \
  --output-thread-queue-chunks 8 \
  --max-playback-buffer-ms 800 \
  --metrics-interval-sec 10 \
  --auto-reconnect
```

如果 CLI 参数名最终不同，必须在 README、AGENTS.md 和任务报告里写清最终命令。

长会话验收：

```bash
GEMINI_API_KEY=your_key_here python -m meeting_translator run \
  --input-device "Zerro的AirPods" \
  --output-device "BlackHole 2ch" \
  --target-language en \
  --metrics-interval-sec 10 \
  --auto-reconnect
```

运行至少 12 分钟，观察：

- Teams 是否持续能听到英文翻译语音。
- 收到 GoAway 后是否自动重连或正常关闭。
- 不得出现 `1008 policy violation`。
- Ctrl+C 是否一次即可退出。

## 10. 安全扫描

任务完成前必须运行：

```bash
rg -n --hidden -g '!.git' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

要求：

- `.env` 不得入库。
- 真实 API key 不得出现在源码、README、AGENTS.md、任务报告、测试 fixture、日志中。
- 如果任务计划或任务报告记录了扫描命令本身导致假阳性，必须排除对应任务文档后重跑并说明结果。

## 11. 任务报告要求

任务完成后必须写中文报告，路径格式：

```text
tasks/3-low-latency-live-translation-[utctime].md
```

其中 `[utctime]` 使用 UTC 时间，格式为：

```bash
date -u +%y%m%d-%H%M%S
```

报告至少包含：

- 实际变更文件清单。
- 最终低延迟配置默认值。
- 是否修改 `.env.example`、README、AGENTS.md。
- 低延迟队列策略说明。
- 输入溢出处理策略说明。
- 输出丢弃策略说明。
- GoAway / 自动重连策略说明。
- 运行过的命令和结果摘要。
- 依赖安装是否使用代理。
- 单元测试结果。
- ruff 结果。
- `devices` 输出中实际使用的输入/输出设备名。
- `check` 子命令结果。
- Teams / BlackHole 人工验收结果。
- 端到端延迟估计：修改前、修改后。
- metrics 摘要：最大 input/output/thread queue 深度、最大 playback buffer ms、drop 计数。
- 12 分钟长会话验收结果；如果无法人工验收，说明缺少的设备/API key/会议 app 条件。
- 安全扫描结果，明确是否发现真实 API key。
- 未完成事项和下一步建议。

## 12. 完成标准

本任务完成必须同时满足：

- 默认输出队列积压上限不再是 50 个 100ms chunk。
- 输出播放不截断 chunk，且跨 callback buffer 有测试覆盖。
- 低延迟丢弃策略有测试覆盖，并在 summary 中可见。
- 输入队列溢出不再静默兜底。
- 收到 Gemini GoAway 后不再触发 `1008 policy violation`。
- 长会话可自动重连或正常关闭，行为由配置明确控制。
- 正常控制事件不刷 `Unsupported Gemini event`。
- 真正未知事件仍保留诊断能力。
- Ctrl+C / SIGTERM 可有序退出。
- `python -m pytest` 通过。
- `python -m ruff check .` 通过。
- `git diff --check` 通过。
- README / AGENTS.md / `.env.example` 与新增配置同步，或报告解释不需要同步的理由。
- 任务报告 `tasks/3-low-latency-live-translation-[utctime].md` 已写入。

## 13. 二次遗漏检查

交付前必须做一次专门遗漏检查：

- 当前 Go/豆包代码未被误删。
- 没有把个人设备名硬编码进源码。
- `.env`、真实 API key、会议日志、音频文件没有入库。
- 输入设备和输出设备仍不是 pass-through 混音。
- macOS 系统输出仍不要求选择 BlackHole。
- Gemini 输入 16kHz / 输出 24kHz 参数没有被悄悄改掉。
- 100ms chunk 校验仍存在。
- output queue、thread queue、playback buffer 三层都不会默认积压到约 5 秒。
- 输入溢出不会静默隐藏。
- 输出丢弃只作为明确低延迟策略存在，并且计数可见。
- GoAway 不再被当成普通可忽略事件。
- 自动重连不会递归创建无限后台任务或泄漏旧 websocket。
- Ctrl+C 后不会留下 `python -m meeting_translator run` 进程。
- README、AGENTS.md、`.env.example` 和实际 CLI 参数一致。
- 任务报告文件名使用 UTC 时间。
