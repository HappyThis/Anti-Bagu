# Anti-Bagu Protocol

这个目录保存 macOS 采集器、Python 实时核心和 Web UI 之间的共享 JSON Schema。

V1 以 schema 为协议事实来源。修改实时事件前，应先更新对应 schema 和示例，再修改各端类型。

音频 WebSocket 的第一条消息是 `audio-metadata` JSON。后续每个二进制包由两部分组成：

```text
8-byte little-endian Float64 captured_at Unix timestamp
3200-byte pcm_s16le audio frame
```

因此默认 100ms 音频包总长度为 3208 字节。时间戳用于计算真实采集传输、ASR 和端到端延迟。
