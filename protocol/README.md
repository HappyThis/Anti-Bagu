# Anti-Bagu Protocol

这个目录保存 macOS 采集器、Python 实时核心和 Web UI 之间的共享 JSON Schema。

V2 以 schema 为协议事实来源。模型输出只有 `wait` 和 `answer` 两种；算法题在 `answer` 中额外携带带注释的 Python `code`。思考模式、截图来源和生成状态属于系统运行信息，不进入模型输出协议。

DeepSeek 当前使用 `response_format={"type":"json_object"}` 保证合法 JSON，再由后端按照 `model-result.schema.json` 对应的 Pydantic 判别联合校验。

音频 WebSocket 的第一条消息是 `audio-metadata` JSON。后续每个二进制包由两部分组成：

```text
8-byte little-endian Float64 captured_at Unix timestamp
3200-byte pcm_s16le audio frame
```

因此默认 100ms 音频包总长度为 3208 字节。时间戳用于计算真实采集传输、ASR 和端到端延迟。
