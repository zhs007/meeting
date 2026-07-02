# 任务 1 执行报告：Gemini Live Translation Python 单向实时翻译初始化

## 1. 实际变更文件清单

新增：

- `.env.example`
- `.gitignore`
- `AGENTS.md`
- `pyproject.toml`
- `requirements.txt`
- `src/meeting_translator/__init__.py`
- `src/meeting_translator/__main__.py`
- `src/meeting_translator/audio_devices.py`
- `src/meeting_translator/audio_io.py`
- `src/meeting_translator/cli.py`
- `src/meeting_translator/config.py`
- `src/meeting_translator/gemini_live_translate.py`
- `src/meeting_translator/pcm.py`
- `src/meeting_translator/transcript_log.py`
- `tests/test_config.py`
- `tests/test_device_selection.py`
- `tests/test_gemini_message_shapes.py`
- `tests/test_pcm.py`
- `tasks/1-gemini-live-translation-python-init-260702-060808.md`

更新：

- `README.md`
- `AGENT_GUIDE.md`

未删除或重写现有 Go/豆包代码。

## 2. 最终音频链路说明

本任务落地的 Python 原型链路为：

```text
AirPods 4 麦克风中文语音
  -> meeting Python app
  -> Gemini Live Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本 app 不读取会议 app 扬声器输出，不把会议 app 输出 pass-through 到 AirPods，不接管会议 app 的 AirPods 输出。

## 3. Gemini 模型和音频参数

- 模型：`gemini-3.5-live-translate-preview`
- 输入：raw PCM16 little-endian、16kHz、mono
- 输入 chunk：100ms，1600 samples，3200 bytes
- 输出：raw PCM16 little-endian、24kHz、mono
- 默认目标语言：`en`
- 默认 `echoTargetLanguage=false`

实现说明：当前安装到的 `google-genai 1.75.0` 没有公开 `types.TranslationConfig`，因此代码使用 `LiveConnectConfig` 并把官方 wire shape `generationConfig.translationConfig.targetLanguageCode` / `echoTargetLanguage` 写入 config。已有测试覆盖该 shape，避免字段被 SDK 类型变化静默丢失。

## 4. 运行过的命令和结果摘要

```bash
git checkout -b codex/gemini-live-translation-python-init
```

结果：成功创建并切换分支。首次普通执行因 `.git` 写入受限失败，随后按权限流程提升后成功。

```bash
python3 -m venv .venv
```

结果：成功。

```bash
.venv/bin/python -m pip install -U pip
```

结果：当前 pip 已满足版本要求；普通网络访问被沙箱代理限制拦截，但命令最终退出 0。

```bash
.venv/bin/python -m pip install -r requirements.txt
```

结果：普通网络访问失败，错误为沙箱内无法连接代理。

```bash
env http_proxy=http://127.0.0.1:1087 https_proxy=http://127.0.0.1:1087 .venv/bin/python -m pip install -r requirements.txt
```

结果：成功。安装了 `google-genai 1.75.0`、`sounddevice 0.5.5`、`pytest 8.4.2`、`ruff 0.15.20` 等依赖。

```bash
.venv/bin/python -m pip install -e .
```

结果：普通网络访问在隔离构建依赖 `setuptools` 阶段失败。

```bash
env http_proxy=http://127.0.0.1:1087 https_proxy=http://127.0.0.1:1087 .venv/bin/python -m pip install -e .
```

结果：成功安装 editable 包 `meeting-translator 0.1.0`。

```bash
.venv/bin/python -m pytest
```

结果：`16 passed in 0.29s`。

```bash
.venv/bin/python -m ruff check .
```

结果：`All checks passed!`

```bash
.venv/bin/python -m meeting_translator devices
```

结果：命令成功执行，但当前运行环境没有暴露任何音频设备：

```text
index | input | output | default_rate | can_input | can_output | name
----- | ----- | ------ | ------------ | --------- | ---------- | ----
```

```bash
.venv/bin/python -m meeting_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

结果：无 `GEMINI_API_KEY` 时显式失败，且未打印 key 值：

```text
error: GEMINI_API_KEY is required; set it in the environment or .env. The key value is never printed.
```

```bash
env GEMINI_API_KEY=placeholder .venv/bin/python -m meeting_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en
```

结果：当前环境无音频设备，因此按精确设备名显式失败，没有兜底到默认设备：

```text
error: input device 'AirPods 4' was not found. Run `python -m meeting_translator devices` and pass the exact device name.
```

```bash
.venv/bin/python -c "from meeting_translator.gemini_live_translate import build_live_config, live_translation_config_dict, MODEL_NAME; cfg=build_live_config('en', echo_target_language=False); print(MODEL_NAME); print(type(cfg).__name__); print(live_translation_config_dict(cfg))"
```

结果：成功构造 Gemini Live Translation config：

```text
gemini-3.5-live-translate-preview
LiveConnectConfig
{'targetLanguageCode': 'en', 'echoTargetLanguage': False}
```

```bash
git diff --check
```

结果：通过，无空白错误。

## 5. 依赖安装是否使用代理

使用了代理。普通网络访问因沙箱限制失败后，按任务计划使用：

```bash
http_proxy=http://127.0.0.1:1087
https_proxy=http://127.0.0.1:1087
```

代理只用于安装命令，没有写入源码、配置文件或测试。

## 6. 单元测试结果

`pytest` 结果：`16 passed`。

覆盖项：

- 配置优先级：命令行参数 > 环境变量 > `.env` > 默认值
- 缺 `GEMINI_API_KEY` 显式失败且不泄露 key 值
- 设备精确名称匹配
- 找不到输入/输出设备显式失败
- 不允许隐式选择默认设备
- 16kHz/100ms/mono/PCM16 chunk 为 3200 bytes
- PCM base64 roundtrip
- 非 100ms chunk 发送前失败
- Gemini input/output transcript 解析
- Gemini output audio 入输出队列
- 未知 Gemini 消息结构记录为 unsupported event
- Gemini Live Translation config 保留官方 `translationConfig` wire shape

## 7. ruff 结果

`ruff check .` 结果：`All checks passed!`

## 8. devices 输出中实际使用的输入/输出设备名

当前执行环境没有暴露任何音频设备，因此没有实际可使用的输入/输出设备名。

需要在真实 macOS 桌面音频环境中重跑：

```bash
python -m meeting_translator devices
```

然后用输出中的精确设备名重跑 `check`。

## 9. check 子命令结果

已验证两类显式失败：

- 缺少 `GEMINI_API_KEY`：失败且不打印 key 值。
- 使用占位 key 时缺少 `AirPods 4` 输入设备：失败且不静默选择默认设备。

由于当前环境没有暴露音频设备，本次无法验证真实 AirPods 4 / BlackHole 2ch 的采样率、声道、dtype 打开结果。

## 10. run 人工验收结果

未执行真实 `run` 人工会议链路验收。

缺少条件：

- 当前环境没有暴露 `AirPods 4` 或 `BlackHole 2ch` 音频设备。
- 当前环境没有真实 `GEMINI_API_KEY`。
- 未接入实际会议 app 麦克风测试或对端会议环境。

代码已实现 `run` 命令、Gemini session、输入/输出音频流、字幕日志和 Ctrl+C 关闭摘要。需要在具备上述条件的 macOS 桌面环境中人工验收。

## 11. AGENTS.md 和 AGENT_GUIDE.md

- 已新增 `AGENTS.md`，同步 Python 原型边界、验证命令、失败策略和安全规则。
- 已更新 `AGENT_GUIDE.md`，把项目方向从单一 Go 更新为 Python 原型 + legacy Go，并修正 Python 任务的验证命令。

## 12. 安全扫描结果

执行原计划安全扫描：

```bash
rg -n --hidden -g '!.git' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：命中 `tasks/1-gemini-live-translation-python-init.md` 中记录的扫描命令本身，为假阳性，不是真实 API key。

排除该任务说明文件后重跑：

```bash
rg -n --hidden -g '!.git' -g '!tasks/1-gemini-live-translation-python-init.md' -e 'GEMINI_API_KEY=AIza|AIza[0-9A-Za-z_-]{35}|OPENAI_API_KEY=sk-|sk-[A-Za-z0-9_-]{20,}|APP_KEY=.*[A-Za-z0-9]{8,}|ACCESS_KEY=.*[A-Za-z0-9]{8,}'
```

结果：无命中。

结论：未发现真实 Gemini API key、OpenAI API key、APP_KEY 或 ACCESS_KEY。

## 13. 未完成事项和下一步建议

未完成：

- 真实 AirPods 4 / BlackHole 2ch 设备打开验收。
- 真实 Gemini Live API 连接验收。
- 会议 app 麦克风端到端人工验收。

建议下一步：

1. 在真实 macOS 桌面环境确认 `python -m meeting_translator devices` 能看到 AirPods 4 和 BlackHole 2ch。
2. 配置真实 `.env`，不要提交 `.env`。
3. 运行 `python -m meeting_translator check --input-device "<实际输入设备名>" --output-device "<实际输出设备名>" --target-language en`。
4. 会议 app 麦克风选择 BlackHole 2ch，扬声器选择 AirPods 4 后执行 `run` 人工验收。

## 14. 二次遗漏检查

- 当前 Go/豆包代码未被误删：已确认。
- 新 Python 代码没有硬编码个人设备名：已确认，设备名仅在 `.env.example`、README 示例和任务文档中出现。
- 输入设备和输出设备没有设计成 pass-through 混音：已确认，输入流只进入 Gemini，输出流只播放 Gemini 输出音频。
- 停止 app 只停止翻译链路，不接管会议 app 的 AirPods 输出：已确认。
- Gemini 输入/输出采样率符合任务约束：已确认，输入 16kHz，输出 24kHz。
- 100ms chunk 大小和发送前校验有测试覆盖：已确认。
- 缺 key、缺设备、设备不支持格式都会显式失败：已确认。
- 没有引入 OpenAI provider 或通用 provider 抽象：已确认。
- 没有为了测试通过加入隐藏 fallback：已确认。
- 文档和 agent 规则没有互相冲突：已同步 README、AGENTS.md、AGENT_GUIDE.md。
- 任务报告文件名使用 UTC 时间：已确认，`260702-060808` 来自 `date -u +%y%m%d-%H%M%S`。
