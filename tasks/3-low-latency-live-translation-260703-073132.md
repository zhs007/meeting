# 任务 3 执行报告：Low Latency Live Translation 稳定化

UTC 时间：260703-073132

## 1. 实际变更文件

- `.env.example`
- `AGENTS.md`
- `AGENT_GUIDE.md`
- `README.md`
- `src/meeting_translator/config.py`
- `src/meeting_translator/audio_io.py`
- `src/meeting_translator/gemini_live_translate.py`
- `src/meeting_translator/cli.py`
- `src/meeting_translator/transcript_log.py`
- `tests/test_audio_io.py`
- `tests/test_config.py`
- `tests/test_gemini_message_shapes.py`
- `tests/test_reconnect.py`
- `tasks/3-low-latency-live-translation-260703-073132.md`

未修改 `src/meeting_openai_translator/`、legacy Go、豆包目录。

## 2. 最终低延迟配置默认值

Gemini 原型新增配置：

```text
MEETING_INPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_QUEUE_CHUNKS=8
MEETING_OUTPUT_THREAD_QUEUE_CHUNKS=8
MEETING_MAX_PLAYBACK_BUFFER_MS=800
MEETING_METRICS_INTERVAL_SEC=10
MEETING_AUTO_RECONNECT=true
MEETING_MAX_RECONNECTS=0
MEETING_DEBUG_EVENTS=false
```

默认输入队列最多约 800ms。输出侧默认 asyncio queue 约 800ms、thread queue 约 800ms、playback buffer 800ms，合计本地输出缓冲预算约 2.4s，且任何单层输出队列都不再允许 50 个 100ms chunk 的约 5s 积压。

配置优先级仍为：

```text
命令行参数 > 环境变量 > .env > 默认值
```

## 3. 策略说明

### 3.1 低延迟队列策略

- `run` 默认使用 `asyncio.Queue(maxsize=config.input_queue_chunks)` 和 `asyncio.Queue(maxsize=config.output_queue_chunks)`。
- CLI 会先建立 Gemini session，等 session ready 后再启动麦克风输入流，避免启动期连接耗时把 8 个 100ms input chunk 填满并误判 overflow。
- GoAway 重连期间会临时让输入 callback 不入队；断开窗口里的输入 chunk 计入 `input_dropped_while_disconnected`，不是静默吞掉。
- Gemini receiver 写输出 asyncio queue 时不再无限等待；队列满则丢弃旧音频块，保留最新块。
- `RawAudioOutput` 的 thread queue 大小改为配置传入，默认 8。
- thread queue 满时丢弃最旧音频块，再放入最新音频块。
- `_playback_buffer` 超过 `MEETING_MAX_PLAYBACK_BUFFER_MS` 时丢弃最旧音频字节。
- 所有输出丢弃都会累计 `output_dropped_chunks` / `output_dropped_bytes`，旧 session 清理会额外累计 `output_stale_cleared_chunks` / `output_stale_cleared_bytes`。

### 3.2 输入溢出策略

- `RawAudioInput` 捕获到 input queue full 时记录 `input_overflows` 和 `input_overflow_error`。
- CLI 主 loop 监听 `input_overflow_event`，默认显式停止本次运行并抛出 `GeminiLiveError`。
- 没有实现隐藏的“静默丢输入继续跑”fallback。
- input queue overflow 只表示 Gemini sender 在 session 已 ready 时仍追不上采集侧；启动期和重连期另走 `capture_active_event`，避免把 session 尚未 ready 误判为发送背压。

### 3.3 GoAway / 自动重连策略

- `run_single_live_translation_session(...)` 只负责单个 Gemini session。
- 外层 `run_live_translation(...)` 负责 GoAway 后清理旧输入/输出队列、关闭当前 session、按配置自动重连。
- `MEETING_AUTO_RECONNECT=true` 时，GoAway 后打印 `reconnecting before timeout` 并创建新 session。
- `MEETING_AUTO_RECONNECT=false` 时，GoAway 作为正常关闭原因 `closed_after_goaway` 记录。
- `MEETING_MAX_RECONNECTS=0` 表示无限制；大于 0 时达到上限会记录 `reconnect_limit_reached_after_goaway` 并结束。

### 3.4 Gemini 事件收敛

- `usageMetadata`、`setupComplete`、`goAway`、`sessionResumptionUpdate`、`voiceActivity`、`voiceActivityDetectionSignal`、`turnComplete`、`generationComplete`、`waitingForInput`、transcription finished 等控制事件默认不刷 `Unsupported Gemini event`。
- 真正未知事件默认只计数并保存首个样例到 summary；只有 `--debug-events` / `MEETING_DEBUG_EVENTS=true` 时才打印。

## 4. Summary / metrics

`TranscriptLogger.close(...)` 新增 `metrics` 字段。关闭摘要包含：

- low latency config
- current queue depths
- `input_chunks_captured`
- `input_chunks_queued`
- `input_dropped_while_disconnected`
- `input_stale_cleared_chunks`
- `input_stale_cleared_bytes`
- `input_overflows`
- `output_dropped_chunks`
- `output_dropped_bytes`
- `output_max_async_queue_depth`
- `output_max_thread_queue_depth`
- `output_max_playback_buffer_ms`
- `input_chunks_sent`
- `output_audio_chunks_received`
- `output_audio_bytes_received`
- `goaway_count`
- `reconnect_count`
- `session_count`
- `unsupported_event_count`

周期 metrics 示例由 CLI 打印，默认每 10 秒一次；`MEETING_METRICS_INTERVAL_SEC=0` 可关闭。

## 5. 文档同步

已同步：

- `.env.example`：新增 Gemini 低延迟、重连、debug events 默认值。
- `README.md`：新增低延迟队列说明、运行参数、metrics、GoAway 自动重连说明、Teams/BlackHole 设置仍保留。
- `AGENTS.md`：新增 Gemini 低延迟 check 参数和失败策略。
- `AGENT_GUIDE.md`：同步 Gemini check 参数和低延迟失败策略。

## 6. 自动化测试结果

### 6.1 依赖安装

```bash
.venv/bin/python -m pip install -r requirements.txt
```

结果：通过，依赖均已满足。pip cache 目录不可写，因此 cache disabled；不影响安装结果。

```bash
.venv/bin/python -m pip install -e .
```

第一次在沙箱内失败，原因是构建隔离阶段访问 `setuptools>=69` 被网络限制阻止。按沙箱规则提权重跑同一条命令后通过。

未使用代理。

### 6.2 单元测试

```bash
.venv/bin/python -m pytest
```

结果：通过。

```text
55 passed
```

新增覆盖：

- 低延迟配置优先级和非法值。
- 输出 thread queue 满时丢弃旧音频并计数。
- playback buffer 超过上限时丢弃旧音频并计数。
- 默认输出缓冲预算低于 5s。
- input queue full 触发 overflow signal。
- session 未 ready 时输入 callback 不入队、不触发 overflow，并计入 disconnected drop。
- GoAway 后自动重连、禁用重连、达到重连上限。
- 重连时清理旧输入/输出队列。
- 正常 Gemini 控制事件不刷 unsupported。
- 未知事件默认计数不刷屏。

### 6.3 ruff

```bash
.venv/bin/python -m ruff check .
```

结果：

```text
All checks passed!
```

### 6.4 devices / check

```bash
.venv/bin/python -m meeting_translator devices
```

结果：命令可执行，但当前环境没有列出可用音频设备，只输出表头：

```text
index | input | output | default_rate | can_input | can_output | name
----- | ----- | ------ | ------------ | --------- | ---------- | ----
```

```bash
GEMINI_API_KEY=placeholder-key .venv/bin/python -m meeting_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en \
  --input-queue-chunks 8 \
  --output-queue-chunks 8 \
  --output-thread-queue-chunks 8 \
  --max-playback-buffer-ms 800 \
  --metrics-interval-sec 10 \
  --auto-reconnect
```

结果：显式失败，当前环境找不到输入设备：

```text
error: input device 'AirPods 4' was not found. Run `python -m meeting_translator devices` and pass the exact device name.
```

按任务原计划设备名 `Zerro的AirPods` 重跑同样显式失败，原因相同。未在源码中硬编码任何个人设备名。

### 6.5 OpenAI 并存保护性验收

本任务未修改 OpenAI 实现。作为并存保护，执行：

```bash
.venv/bin/python -m meeting_openai_translator devices
OPENAI_API_KEY=placeholder-key .venv/bin/python -m meeting_openai_translator check \
  --input-device "AirPods 4" \
  --output-device "BlackHole 2ch" \
  --target-language en
```

结果：OpenAI devices 入口可执行但当前环境无设备；check 显式失败于输入设备找不到。

### 6.6 git diff check

```bash
git diff --check
```

结果：通过，无 trailing whitespace 或 diff 格式问题。

## 7. 安全扫描

执行原计划扫描：

```bash
rg -n --hidden -g '!.git' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：命中均为 `tasks/*.md` 中记录的扫描命令本身，属于假阳性。

排除任务文档后重扫：

```bash
rg -n --hidden -g '!.git' -g '!tasks/*.md' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：无命中，未发现真实 Gemini/OpenAI/API key。

额外检查：

```bash
find . -path './.git' -prune -o -path './.venv' -prune -o \( -name '.env' -o -name '*.pcm' -o -name '*.wav' \) -print
git status --short -- test_audio.wav .env
git ls-files .env test_audio.wav logs
```

结果：

- 工作区存在 `.env`，但未被 git 跟踪，也未出现在本次 diff。
- 工作区存在 `test_audio.wav`，且该文件已由历史提交 `79a4cce` 跟踪；本任务未新增或修改它。若严格执行“仓库中不得存在 WAV”，需要单独清理这个既有历史文件。
- 未发现 `.pcm`。
- `logs/` 未出现在本次改动中。

## 8. 手工验收结果

当前环境缺少可用音频设备，`meeting_translator devices` 没列出 AirPods / BlackHole，因此未执行真实 Gemini Live API、Teams / BlackHole、端到端延迟和 12 分钟长会话人工验收。

未完成的人工验收条件：

- macOS 音频设备可见。
- 输入设备为实际 AirPods / 本机麦克风。
- 输出设备为 BlackHole 2ch。
- 会议 app 麦克风选择 BlackHole 2ch。
- 会议 app 扬声器选择 AirPods。
- 真实 `GEMINI_API_KEY` 仅在本地 shell 或 `.env` 中提供，不能写入源码或报告。
- 运行至少 12 分钟观察 GoAway 自动重连或正常关闭。

端到端延迟估计：

- 修改前：用户观察约 5 秒。
- 本任务自动验收环境：无法测量真实端到端延迟。
- 本地队列理论上已从单队列 50 chunk 约 5 秒降低为单队列 8 chunk 约 800ms；输出侧三层预算约 2.4 秒，并带有丢弃计数。

metrics 摘要：

- 未进行真实 `run`，因此没有真实会议 metrics。
- 单元测试已覆盖 queue full、playback buffer 超限、GoAway 清理旧输出队列和重连计数。

进程残留检查：

- 本任务未执行真实 `python -m meeting_translator run` 长会话。
- `pgrep -fl "python -m meeting_translator run"` 失败：`sysmond service not found`。
- `ps -axo pid,command` 在当前环境失败：`operation not permitted`。
- 因未启动真实 run 进程，未发现由本任务产生的残留运行进程。

## 9. 二次遗漏检查

- Go/豆包代码未改动。
- OpenAI 源码未改动；OpenAI pytest 仍通过。
- 没有在源码中硬编码 `Zerro的AirPods` 或任何个人设备名。
- `.env` 未入库，本任务未新增真实 API key。
- `test_audio.wav` 是既有 tracked 文件，本任务未新增或修改；建议单独清理。
- 输入设备和输出设备仍不是 pass-through 混音：Gemini 输入只送 Gemini，输出只送 BlackHole。
- README 仍写明 macOS 系统输出不要选择 BlackHole。
- Gemini 输入 16kHz / mono / int16 / 100ms / 3200 bytes 未改变。
- Gemini 输出 24kHz / mono / int16 未改变。
- `validate_input_chunk` 的 100ms chunk 校验仍存在。
- Gemini output queue、thread queue、playback buffer 默认都不再单层积压到约 5 秒。
- 输入溢出会显式错误，不再静默隐藏。
- 输出丢弃是明确低延迟策略，并在 stats / summary 中计数。
- GoAway 不再被当成普通忽略事件；会进入重连或正常关闭分支。
- 自动重连使用外层 loop，不递归创建无限后台任务。
- README、AGENTS.md、AGENT_GUIDE.md、`.env.example` 与实际 CLI 参数一致。
- 任务报告文件名使用 UTC 时间。

## 10. 未完成事项和下一步建议

1. 在真实 macOS 桌面环境运行 Gemini `run`，记录短句延迟、metrics 最大队列深度和 drop 计数。
2. 运行至少 12 分钟，确认 GoAway 后自动重连，且不出现 `1008 policy violation`。
3. 如真实延迟仍超过 2 秒，根据 metrics 判断瓶颈是本地队列、Gemini VAD/模型、网络，还是 Teams 麦克风测试链路。
4. 单独处理既有 tracked `test_audio.wav` 是否应从仓库移除及历史清理。
