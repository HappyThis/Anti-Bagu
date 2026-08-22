# Anti-Bagu 项目结构

状态：Cloud Beta 已实现
日期：2026-08-22

## 架构原则

当前阶段采用模块化单体，而不是微服务。实时链路、控制面和持久化边界清晰分离，但部署为一个 Python 进程，避免在 2 核 4G 服务器上引入 Redis、消息队列和服务间网络开销。

```text
macOS Agent ── WSS 控制通道 ───────────────┐
             ├── WSS interviewer PCM ─────┤
             └── WSS candidate PCM ───────┤
                                           ▼
React Web / Mobile H5 ── HTTPS/WSS ── FastAPI modular monolith
                                           ├── PostgreSQL
                                           └── local task storage
```

## 目录

```text
Anti-Bagu/
├── apps/
│   ├── capture-macos/                 # anti-bagu-agent
│   │   ├── Sources/AntiBaguCapture/
│   │   │   ├── AntiBaguCaptureApp.swift
│   │   │   ├── AgentAPI.swift
│   │   │   ├── AgentControlClient.swift
│   │   │   ├── AgentCredentials.swift
│   │   │   ├── CaptureSession.swift
│   │   │   └── ... audio capture/transport
│   │   └── Tests/
│   └── web/
│       └── src/
│           ├── app/                   # routing and access guards
│           ├── features/              # high-frequency realtime UI
│           ├── product/               # user/admin/mobile product pages
│           └── shared/                # API and wire protocol
├── backend/
│   ├── migrations/                    # Alembic schema history
│   └── src/anti_bagu/
│       ├── agent/                     # desktop control connections
│       ├── api/
│       │   ├── routers/               # HTTP/WebSocket transport only
│       │   ├── dependencies.py
│       │   └── schemas.py
│       ├── asr/                       # Qwen streaming adapter
│       ├── audio/                     # PCM protocol validation
│       ├── auth/                      # activation/login/session service
│       ├── core/                      # security primitives
│       ├── interview/                 # Focus/context/state machine
│       ├── llm/                       # DeepSeek adapters and prompts
│       ├── mobile/                    # ephemeral QR pairing
│       ├── persistence/               # SQLAlchemy and task artifacts
│       ├── realtime/                  # per-task runtime registry
│       ├── tasks/                     # lifecycle and preflight service
│       └── telemetry/                 # redacted daily platform log
├── deploy/
│   ├── nginx/                         # HTTP bootstrap + HTTPS/WSS config
│   ├── systemd/                       # app and certificate timers
│   └── scripts/                       # repeatable release deployment
├── protocol/                          # cross-client JSON/PCM contracts
├── docs/
├── tests/                             # paid model/latency evaluations
└── scripts/                           # model and ASR experiments
```

## 模块依赖

```text
API routers
    ↓
AuthService / TaskService / AgentHub / MobileHub
    ↓
RuntimeRegistry ── InterviewCoordinator ── ASR/LLM adapters
    ↓
SQLAlchemy metadata + TaskEventRecorder + PCMArchive
```

依赖规则：

- Router 只处理鉴权、协议转换和 HTTP 状态码。
- 任务状态迁移只允许由 `TaskService` 执行。
- Focus 触发规则只存在于 `InterviewCoordinator`。
- 用户模型 Key 不进入数据库、平台日志或浏览器存储。
- 高频 `audio.level` 不落数据库；转写、Focus、回答、延迟、错误和完整 LLM 输入都按任务保存。
- 每个任务拥有独立 Coordinator、EventHub、事件队列和内存模型客户端。
- Beta 只运行一个 Uvicorn worker；多 worker 之前必须把连接路由迁移到 Redis。

## 数据边界

PostgreSQL：

- `users`
- `activation_keys`
- `auth_sessions`
- `tasks`
- `task_events`
- `agent_devices`
- `platform_audit`

本地任务目录：

```text
/var/lib/anti-bagu/storage/tasks/<task-id>/
├── events/YYYY-MM-DD.jsonl
└── audio/
    ├── interviewer.pcm
    ├── interviewer.json
    ├── candidate.pcm
    └── candidate.json
```

平台日志保存在 `/var/lib/anti-bagu/logs/YYYY-MM-DD.jsonl`，默认脱敏正文和所有 Token/Key。

## 鉴权

- Web Session：随机不可预测的 opaque token，默认 7 天，数据库只保存 SHA-256。
- Agent Token：CLI 使用用户名密码登录后签发，默认 30 天，保存在 macOS Keychain。
- 模型 Key：只保存在 macOS Keychain；任务预检时通过 WSS 临时发送到单个任务运行时内存。
- 手机端：任务所有者生成 10 分钟临时配对 Token，扫码后只订阅当前任务的 Focus 和回答事件。

## 部署约束

- Ubuntu 24.04、Nginx、PostgreSQL 16、Python 3.12。
- FastAPI 只监听 `127.0.0.1:8765`。
- Nginx 是唯一公网入口，负责 React SPA、HTTPS 和 WebSocket Upgrade。
- Let’s Encrypt 可信 IP 证书有效约 6 天，systemd timer 每天两次检查续期。
- systemd 使用独立 `antibagu` 用户，应用只能写 `/var/lib/anti-bagu`。
