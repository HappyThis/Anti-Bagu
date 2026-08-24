# Anti-Bagu Cloud Beta 技术方案

## 已实现范围

- 一次性激活密钥注册；注册只需要用户名和密码。
- 用户、管理员、Web Session 和 30 天 Agent Token。
- 用户任务列表、自定义命名、创建、检查、开始、暂停、恢复和结束。
- 桌面 Agent 控制 WebSocket、心跳、断线自动暂停。
- 系统音频和麦克风两个独立任务级 WebSocket。
- Agent 权限、ASR、LLM 和手机端真实预检；未通过时禁止启动。
- 每个任务独立的 ASR、Focus、回答状态和事件订阅。
- 手机二维码临时配对和 Focus/回答实时推送。
- PostgreSQL 元数据与持久化任务事件、按日脱敏系统日志、双路原始 PCM 音频与截图。
- 用户复盘事件时间线和管理员控制台。
- Nginx HTTPS/WSS、systemd 服务与 Let’s Encrypt IP 证书续期。

## 核心时序

```text
用户创建任务
  → Web POST /tasks/:id/preflight
  → Server 通过 /ws/agent 请求桌面检查
  → Agent 返回权限和内存中的模型凭据
  → Server 验证 ASR、LLM、手机连接
  → 全部通过后 Task=ready
  → 用户点击开始
  → Server 推送 task.start
  → Agent 打开两路音频 WSS 并开始采集
  → ASR final → Focus window → DeepSeek → Web/Mobile
  → 核心任务事件异步写 PostgreSQL，运行日志异步写按日 JSONL
```

## 当前刻意不做

- 不引入 Redis、Kafka、Celery 或微服务。
- 不提供平台模型额度。
- 不向浏览器或 Agent 下发模型 Key；用户 Key 在服务端加密保存。
- 不实现多设备并行采集。
- 不实现离线音频重放队列与跨 worker 路由。
- 不实现 OSS；后续磁盘容量和备份压力出现后再迁移对象存储。

## 上线前剩余外部配置

腾讯云安全组必须允许入站 TCP 443。服务器已监听 443，可信 IP 证书已签发并通过本机验证；安全组未开放时公网 HTTPS/WSS 会超时。
