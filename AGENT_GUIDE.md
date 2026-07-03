# AGENT_GUIDE.md

本文件用于描述 agent 在本项目中的基础信息、参数默认值和行为规范，供自动化处理和团队成员参考。

## 1. 基础信息
- 项目名称：meeting
- 主要语言：Python 原型 + legacy Go
- 业务领域：macOS 在线会议单向实时同声传译

## 2. 项目描述

当前主要方向是 Python 单向实时会议翻译原型。Gemini 和 OpenAI 两条原型独立并存：

```text
AirPods 4 麦克风中文语音
  -> meeting Python app
  -> Gemini Live Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入

AirPods 4 麦克风中文语音
  -> meeting OpenAI Python app
  -> OpenAI Realtime Translation
  -> 英文语音 PCM
  -> BlackHole 2ch 输出设备
  -> 会议 app 的麦克风输入
```

本项目不接管会议 app 的扬声器输出。会议 app 的麦克风应选择 BlackHole 2ch，扬声器应由用户自行选择 AirPods 4。

仓库中 legacy Go/豆包 AST 代码保留为历史参考和音频链路参考，不作为 Python 原型的架构约束。

## 3. 注意事项
- Gemini Python 原型位于 `src/meeting_translator/`。
- OpenAI Python 原型位于 `src/meeting_openai_translator/`。
- Python 验证命令：
  - `python -m pip install -r requirements.txt`
  - `python -m pip install -e .`
  - `python -m pytest`
  - `python -m ruff check .`
  - `python -m meeting_translator devices`
  - `python -m meeting_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en`
  - `python -m meeting_openai_translator devices`
  - `python -m meeting_openai_translator check --input-device "AirPods 4" --output-device "BlackHole 2ch" --target-language en`
- 设备名不能隐式兜底到系统默认设备；缺设备、设备找不到、采样率/声道/dtype 不支持都必须显式失败。
- 不得提交 `.env`、真实 API key、会议音频、PCM/WAV 文件或 `logs/` 下的会议日志。
- 依赖下载失败时，可以临时使用用户指定代理 `http://127.0.0.1:1087` / `https://127.0.0.1:1087` 重试安装命令；不得把代理写入源码、配置文件或测试。
- legacy Go 任务仍需谨慎执行 Go 命令；如仅处理 Python 原型，可按上述 Python 验证命令执行。

## 4. 参考规范
- 详细编码规范见 rule.md。
- Python/Python 原型协作规则见 AGENTS.md。
- 其他协作和提交要求见 CONTRIBUTING.md（如有）。

---
如需补充或修改 agent 相关规则，请在本文件中更新并通知相关成员。
