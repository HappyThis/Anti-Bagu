# 日志系统

后端把关键实时链路写成结构化 JSONL 审计日志。日志使用本机时区，按自然日存储：

```text
.runtime/logs/
├── 2026-08-20.jsonl
└── 2026-08-21.jsonl
```

每行是一个独立 JSON 对象，包含时间、级别、事件名、会话 ID、对话版本和事件字段。跨零点后自动写入下一天的文件，不按文件大小轮转，也不自动删除旧日期。

## 关键事件

- `transcript.partial/final/committed/duplicate`
- `focus.window.started/reset/fired`
- `focus.started/cancelled/responded/wait/discarded/skipped/timeout/error/updated`
- `answer.started/first_delta/delta/completed/cancelled/error`
- `audio.connected/disconnected`
- `asr.connected/reconnecting/reconnected/reconnect.failed`
- `ui.connected/disconnected`

`audio.level` 不落盘；音频传输延迟也不持续落盘，避免每 100–500ms 产生大量日志。ASR、模型和端到端延迟仍会记录。

## 隐私与调试

默认不保存转写正文、问题、答案和提示词。这些字段会替换成字符数和短哈希，音频、API Key、Authorization 和模型推理过程始终不应写入日志。

需要在本机复现具体语句时，可在 `.env.local` 临时开启：

```dotenv
ANTIBAGU_LOG_INCLUDE_TEXT=true
```

完成排查后建议恢复为 `false`。

最近事件也保存在内存环形缓冲区，管理员可通过以下接口查看，不需要等待文件刷新：

```text
GET /api/v1/admin/logs?limit=200
```

相关配置：

```dotenv
ANTIBAGU_LOG_DIR=.runtime/logs
ANTIBAGU_LOG_INCLUDE_TEXT=false
ANTIBAGU_LOG_RING_SIZE=1000
ANTIBAGU_LOG_QUEUE_SIZE=4096
```

业务协程只做非阻塞入队，后台任务批量写文件。队列满或磁盘写入失败时会增加 `/health` 中的 `audit_dropped_events`，不会让音频、ASR 或 Focus 链路等待磁盘 I/O。

任务业务事件与系统日志职责不同：

- PostgreSQL `task_events` 保存重启恢复、复盘和管理员诊断需要的持久化事件。
- `/var/lib/anti-bagu/logs/YYYY-MM-DD.jsonl` 保存按日脱敏系统运行日志。
- 不再生成 `/storage/tasks/<task-id>/events/*.jsonl`，避免与 PostgreSQL 重复保存业务正文。
