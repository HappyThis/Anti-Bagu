# Anti-Bagu

**关键词：** 线上面试、计算机面试、八股文、AI 面试助手、语音识别、屏幕理解、算法题

## 背景

计算机面试充斥着脱离实际工作的“八股文”和套路化算法题。求职者不得不花费大量时间反复背诵，却因工作中很少使用而不断遗忘。

在 AI 时代，这类问题已经可以通过工具快速解决，继续依靠背诵考察候选人，难以反映其真实工作能力。

## 目标

Anti-Bagu 是一个面向线上面试的 AI 助手。它通过理解面试现场的信息，帮助候选人解决八股文和算法题，并以此展示传统八股考察方式在 AI 时代的不合理性。

## 工作方式

系统需要同时感知两类信息：

1. **面试对话：** 理解面试官的提问以及双方的对话上下文。
2. **屏幕信息：** 识别屏幕上展示的题目、代码和相关资料。

系统将融合语音与屏幕信息，识别当前问题并提供相应辅助。

## 定位

> 一个用 AI 对抗八股的线上面试助手。

## V1 技术方案

V1 采用本地优先的三端架构：

```text
Swift macOS 双路音频采集
  → Python 异步实时核心
  → React 本地 H5
```

- [V1 技术方案](docs/TECHNICAL_DESIGN_V1.md)
- [项目结构](docs/PROJECT_STRUCTURE.md)
- [模型与链路测试报告](docs/TEST_REPORT.md)
- [Focus Token 预算实验](docs/FOCUS_TOKEN_BUDGET_REPORT.md)

## 本地开发

```bash
make bootstrap
make dev-backend
make dev-web
make dev-capture
```

不访问外部模型的测试：

```bash
make test
```

## 真实监听

首次运行前，在 macOS“隐私与安全性”中允许 Codex/终端访问：

- 屏幕与系统音频录制。
- 麦克风。

权限修改后需要完整重启 Codex。随后分别运行：

```bash
make dev-backend
make dev-web
make dev-capture
```

页面会显示两路真实声波，以及采集传输、ASR、模型和端到端延迟。系统音频映射为 `interviewer`，麦克风映射为 `candidate`。
