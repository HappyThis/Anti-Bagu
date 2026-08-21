# Anti-Bagu 项目结构

状态：V1 已实现
日期：2026-08-21

## 总体结构

项目采用 monorepo、本地优先、三端分层架构：

```text
Swift macOS 采集器
  → localhost WebSocket
Python 异步实时核心
  → localhost WebSocket
React 本地 H5
```

Python 后端采用模块化单体，不拆微服务。V1 只为已经存在的职责建目录，避免提前创建 RAG、视觉、数据库等空模块。

## 当前目录

```text
Anti-Bagu/
├── apps/
│   ├── capture-macos/
│   │   ├── Package.swift
│   │   ├── Sources/AntiBaguCapture/
│   │   │   ├── AntiBaguCaptureApp.swift
│   │   │   ├── AudioMetadata.swift
│   │   │   ├── AudioWebSocket.swift
│   │   │   ├── CaptureConfiguration.swift
│   │   │   └── CapturePermissions.swift
│   │   └── Tests/AntiBaguCaptureTests/
│   │
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── app/
│           ├── features/
│           │   ├── answer/
│           │   ├── diagnostics/
│           │   ├── session/
│           │   └── transcript/
│           └── shared/
│
├── backend/
│   ├── pyproject.toml
│   ├── src/anti_bagu/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   ├── audio/
│   │   ├── asr/
│   │   ├── interview/
│   │   └── llm/
│   └── tests/
│       ├── fakes/
│       └── unit/
│
├── protocol/
│   ├── schemas/
│   └── examples/
│
├── tests/                         # 已有模型与 ASR 评测
│   └── fixtures/
├── scripts/                       # 已有实时模型测试脚本
├── docs/
│   ├── assets/
│   ├── PROJECT_STRUCTURE.md
│   ├── TECHNICAL_DESIGN_V1.md
│   └── TEST_REPORT.md
├── Makefile
├── .env.example
└── README.md
```

## 模块边界

### `apps/capture-macos`

负责 macOS 权限、系统音频、麦克风和 PCM 传输。它只知道本地音频协议，不知道 ASR、DeepSeek 和面试状态机。

当前已实现：

- macOS 13+ Swift Package。
- 屏幕录制和麦克风权限状态检查。
- `interviewer` 与 `candidate` 独立 WebSocket 地址。
- 16kHz、单声道、`pcm_s16le` 元数据。
- 二进制音频 WebSocket 客户端。
- ScreenCaptureKit 系统音频采集。
- AVAudioEngine 麦克风采集。
- AVAudioConverter 16kHz 单声道 PCM 转换。
- 100ms 音频帧时间戳和自动重连队列。
- 协议和端点单元测试。

### `apps/web`

负责显示，不直接访问云端 API。

当前已实现：

- React + TypeScript + Vite。
- 单一后端 WebSocket 连接和自动重连。
- 面试官与候选人双栏 partial/final 转写。
- 当前问题、FAST/THINK 状态与回答。
- 增量 THINK 答案。
- 两路 Canvas 实时声波，音频采样不触发整页 React 重渲染。
- 采集、ASR、模型和端到端真实延迟。
- 本地清空交互。
- 延迟诊断栏和响应式布局。

### `backend/api`

FastAPI 传输边界：

- `GET /health`
- `POST /api/transcripts`
- `WS /ws/ui`
- `WS /ws/audio/interviewer`
- `WS /ws/audio/candidate`

路由只负责协议转换，不包含候选人触发规则。

### `backend/audio`

定义和校验 V1 PCM 元数据。每个 100ms 音频包由 8 字节采集时间戳和 3200 字节 PCM 组成，总长度 3208 字节。

### `backend/asr`

包含 ASR Session 接口和双路 Qwen Streaming 生产实现。云端连接失败时后端最多自动重连三次，本地音频 WebSocket 不随单次云端故障关闭。

### `backend/interview`

V1 的业务核心：

- `conversation.py`：完整 final 日志和 committed Focus/Answer 历史。
- `context.py`：8K Token 估算、历史 Focus 与最近对话 Markdown 构建。
- `coordinator.py`：300ms 合并窗口、generation 抢占和 FAST/THINK 生命周期。
- `events.py`：内部 Pydantic 协议。
- `state.py`：实时会话状态。

已固定的行为：

- `interviewer.final` 进入 300ms 合并窗口，窗口结束后调用 Focus。
- 新的 `interviewer.partial` 只重置窗口，不取消运行中的 Focus。
- `candidate.final` 只追加上下文，不推进 revision，不调用模型。
- `candidate.partial` 不取消模型。
- 新 Focus generation 抢占旧请求，迟到结果不能提交。
- 新 committed Focus 才取消旧 THINK 答案，并保留已显示内容。

### `backend/llm`

只负责执行一次模型请求，不决定调用时机：

- `DeepSeekFocusResponder`：关闭思考、解析结构化输出。
- `DeepSeekThinkingAnswerer`：Thinking High、增量输出。
- 独立、版本化的 Prompt 文件。
- 未配置 Key 时的可启动降级实现。

### `protocol`

Swift、Python 和 TypeScript 的协议事实来源。目前保存 JSON Schema 和示例。类型自动生成在协议稳定后再引入。

## 依赖规则

```text
API/音频/ASR
      ↓
Interview Coordinator
      ↓
Conversation + LLM ports
      ↓
DeepSeek/Qwen implementations
```

- Swift 不读取云端 API Key。
- React 不直接调用 ASR 或 LLM。
- FastAPI 路由不直接调用 OpenAI SDK。
- LLM 模块不知道音频和 WebSocket。
- 候选人触发规则只存在于 `InterviewCoordinator`。
- 环境变量只由 `backend/config.py` 读取。

## 测试分层

`backend/tests` 是默认不访问网络的产品测试，目前覆盖：

- candidate final 零模型调用。
- 快速连续 interviewer final 合并为单次 Focus。
- candidate final 不取消正在运行的请求。
- interviewer partial 不取消旧请求。
- 新 generation 抢占旧 Focus，但保留全部 final。
- THINK 增量事件。
- 中断 THINK 后保存已显示推荐内容。
- 8K Prompt 尽量使用可用空间且不超过预算。
- Focus 输出协议校验。
- PCM 元数据校验。
- 时间戳音频包、PCM 声级和 Qwen 结果映射。
- 新 UI 连接的音频状态与延迟快照重放。

根目录现有 `tests` 和 `scripts` 是真实模型评测，不随普通 `make test` 运行，避免自动产生 API 费用。

## 开发命令

```bash
make bootstrap
make dev-backend
make dev-web
make dev-capture
make test
make build-web
make check
```

## 后续扩展

只有功能开始实现时再创建对应模块：

```text
backend/src/anti_bagu/knowledge/    # RAG verified_facts
backend/src/anti_bagu/vision/       # 手动截图理解
apps/mobile-web/                    # 手机端
```

这些扩展通过已有事件和 LLM 接口接入，不修改候选人不触发规则。
