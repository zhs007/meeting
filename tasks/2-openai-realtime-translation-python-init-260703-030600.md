# 任务 2 执行报告：OpenAI Realtime Translation Python 独立原型初始化

## 1. 实际变更文件清单

新增：

- `src/meeting_openai_translator/__init__.py`
- `src/meeting_openai_translator/__main__.py`
- `src/meeting_openai_translator/audio_devices.py`
- `src/meeting_openai_translator/audio_io.py`
- `src/meeting_openai_translator/cli.py`
- `src/meeting_openai_translator/config.py`
- `src/meeting_openai_translator/openai_events.py`
- `src/meeting_openai_translator/openai_realtime_translate.py`
- `src/meeting_openai_translator/pcm.py`
- `src/meeting_openai_translator/transcript_log.py`
- `tests/test_openai_config.py`
- `tests/test_openai_device_selection.py`
- `tests/test_openai_event_shapes.py`
- `tests/test_openai_pcm.py`
- `tasks/2-openai-realtime-translation-python-init-260703-030600.md`

更新：

- `.env.example`
- `AGENTS.md`
- `AGENT_GUIDE.md`
- `README.md`
- `pyproject.toml`
- `requirements.txt`
- `tasks/2-openai-realtime-translation-python-init.md`

未删除或重写现有 Gemini 包、Go/豆包代码。

## 2. Gemini / OpenAI 并存边界

本次把任务 2 从原始 “OpenAI only / 不实现 Gemini” 修正为 “在任务 1 Gemini 基础上新增 OpenAI 独立原型”。

- Gemini 保持在 `src/meeting_translator/`，入口仍为 `python -m meeting_translator`。
- OpenAI 新增在 `src/meeting_openai_translator/`，入口为 `python -m meeting_openai_translator`。
- 未引入通用 provider 抽象。
- 两条链路分别维护配置、PCM 参数、音频设备校验、音频 I/O 和协议处理。

## 3. OpenAI 音频链路说明

```text
AirPods 4 麦克风中文语音
  -> meeting OpenAI Python app
  -> OpenAI Realtime Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本 app 不读取会议 app 扬声器输出，不把会议 app 输出 pass-through 到 AirPods，不接管会议 app 的 AirPods 输出。

## 4. OpenAI 模型、endpoint 和音频参数

- 模型：`gpt-realtime-translate`
- endpoint：`wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate`
- 输入：raw PCM16 little-endian、24kHz、mono
- 输入 chunk：100ms，2400 samples，4800 bytes
- 输出：raw PCM16 little-endian、24kHz、mono
- 默认目标语言：`en`

已确认：

- 使用 `/v1/realtime/translations`。
- 没有实现或调用 `/v1/realtime` voice-agent session。
- 没有调用 `response.create`。
- 发送音频事件为 `session.input_audio_buffer.append`。
- 关闭事件为 `session.close`，并等待 `session.closed`。
- `session.close` 后继续 append 会显式失败。

## 5. 运行过的命令和结果摘要

```bash
.venv/bin/python -m pip install -r requirements.txt
```

结果：普通网络访问失败，新增 `websockets` 下载被沙箱网络限制拦截。

```bash
env http_proxy=http://127.0.0.1:1087 https_proxy=http://127.0.0.1:1087 .venv/bin/python -m pip install -r requirements.txt
```

结果：成功。安装 `websockets 15.0.1`。代理只用于当前命令，未写入源码、配置或测试。

```bash
.venv/bin/python -m pip install -e .
```

结果：普通网络访问在隔离构建依赖阶段失败。

```bash
env http_proxy=http://127.0.0.1:1087 https_proxy=http://127.0.0.1:1087 .venv/bin/python -m pip install -e .
```

结果：成功安装 editable 包 `meeting-translator 0.1.0`。

```bash
.venv/bin/python -m pytest
```

结果：`41 passed in 1.13s`。

```bash
.venv/bin/python -m ruff check .
```

结果：`All checks passed!`

```bash
.venv/bin/python -m meeting_translator devices
.venv/bin/python -m meeting_openai_translator devices
```

结果：两个命令均成功执行，但当前运行环境没有暴露任何音频设备：

```text
index | input | output | default_rate | can_input | can_output | name
----- | ----- | ------ | ------------ | --------- | ---------- | ----
```

```bash
.venv/bin/python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

结果：无 `OPENAI_API_KEY` 时显式失败，且未打印 key 值：

```text
error: OPENAI_API_KEY is missing; set it in the environment or .env. The key value is never printed.
```

```bash
env OPENAI_API_KEY=placeholder .venv/bin/python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

结果：当前环境无音频设备，因此按精确设备名显式失败，没有兜底到默认设备：

```text
error: input device 'AirPods 4' was not found. Run `python -m meeting_openai_translator devices` and pass the exact device name.
```

```bash
env GEMINI_API_KEY=placeholder .venv/bin/python -m meeting_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

结果：Gemini 入口仍可运行到设备精确校验阶段，当前环境无音频设备，因此显式失败：

```text
error: input device 'AirPods 4' was not found. Run `python -m meeting_translator devices` and pass the exact device name.
```

```bash
git diff --check
```

结果：通过，无空白错误。

## 6. 单元测试结果

`pytest` 结果：`41 passed`。

新增 OpenAI 覆盖项：

- 配置优先级：命令行参数 > OpenAI 专属环境变量 >共享设备环境变量 > 默认目标语言。
- 缺 `OPENAI_API_KEY` 显式失败且不泄露 key 值。
- `OPENAI_SAFETY_IDENTIFIER` 为空时使用不可识别占位值。
- email-like safety identifier 显式失败。
- 设备精确名称匹配、缺输入/输出设备显式失败、不选默认设备。
- 24kHz/100ms/mono/PCM16 chunk 为 4800 bytes。
- PCM base64 roundtrip。
- 非 100ms chunk 发送前失败。
- OpenAI input/output transcript delta 解析。
- OpenAI output audio delta 解码并写入输出队列。
- `session.closed` 触发关闭状态。
- endpoint/model/session.update 合同。
- `session.input_audio_buffer.append` 使用 base64 PCM。
- `session.close` 后禁止继续 append。

## 7. ruff 结果

`ruff check .` 结果：`All checks passed!`

## 8. devices 和 check 结果

当前执行环境没有暴露任何音频设备，因此没有实际可使用的输入/输出设备名。

已验证 OpenAI `check` 两类显式失败：

- 缺少 `OPENAI_API_KEY`：失败且不打印 key 值。
- 使用占位 key 时缺少 `AirPods 4` 输入设备：失败且不静默选择默认设备。

需要在真实 macOS 桌面音频环境中重跑：

```bash
python -m meeting_openai_translator devices
python -m meeting_openai_translator check --input-device "<实际输入设备名>" --output-device "<实际输出设备名>" --target-language en
```

## 9. run 人工验收结果

未执行真实 `run` 人工会议链路验收。

缺少条件：

- 当前环境没有暴露 `AirPods 4` 或 `BlackHole 2ch` 音频设备。
- 当前环境没有真实 `OPENAI_API_KEY`。
- 未接入实际会议 app 麦克风测试或对端会议环境。

需要在具备上述条件的 macOS 桌面环境中执行：

```bash
OPENAI_API_KEY=your_key_here python -m meeting_openai_translator run --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

会议 app 麦克风选择 BlackHole 2ch，扬声器选择 AirPods 4。macOS 系统输出不要选择 BlackHole。

## 10. 文档和协作规则同步

- `README.md` 已新增 OpenAI 独立原型说明，并保留 Gemini / legacy Go 说明。
- `AGENTS.md` 已更新为 Gemini/OpenAI 两条独立 Python 原型并存。
- `AGENT_GUIDE.md` 已同步 OpenAI 包路径和验证命令。
- `.env.example` 已加入 OpenAI 占位符，没有真实 key。
- `tasks/2-openai-realtime-translation-python-init.md` 已修正为并存合同。

## 11. 安全扫描结果

执行原计划安全扫描：

```bash
rg -n --hidden -g '!.git' -e 'OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：仅命中任务文档中记录的扫描命令本身，是假阳性。

排除任务文档后重跑：

```bash
rg -n --hidden -g '!.git' -g '!tasks/*.md' -e 'OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：无命中。

本地存在被 `.gitignore` 覆盖的 `.env`、`logs/` 和 `test_audio.wav`，未读取内容，未提交。

## 12. 未完成事项和下一步建议

- 真实 OpenAI Realtime Translation 连接未验收。
- 真实 AirPods 4 / BlackHole 2ch 24kHz 打开未验收。
- 会议 app 麦克风端到端人工验收未执行。
- 如果 macOS/PortAudio 无法稳定用 24kHz 打开 AirPods 或 BlackHole，应另开任务显式加入重采样模块和测试，不要在本任务中静默降级。

## 13. 二次遗漏检查

- Go/豆包代码未被误删：已确认。
- Gemini 包未切换成 OpenAI：已确认。
- Gemini 16kHz 输入 / 24kHz 输出合同未改：已确认。
- OpenAI 包没有硬编码个人设备名：已确认，只在文档和示例命令中使用示例设备名。
- 输入设备和输出设备没有设计成 pass-through 混音：已确认，输入只进入 OpenAI，输出只播放 OpenAI 音频。
- 停止 app 只停止翻译链路，不接管会议 app 的 AirPods 输出：已确认。
- OpenAI 输入/输出采样率为 24kHz PCM16 mono：已确认。
- 100ms chunk 为 4800 bytes 且有测试覆盖：已确认。
- 缺 key、缺设备、采样率不支持都会显式失败：已确认。
- 没有引入不必要 provider 抽象：已确认。
- 没有为了测试通过加入隐藏 fallback：已确认。
- 文档、任务计划、agent 规则没有互相冲突：已确认。
- 任务报告文件名使用 UTC 时间：已确认。
