# Anti-Bagu V1 技术方案

状态：已确定，可进入 PoC 开发
日期：2026-08-21

## 1. V1 目标

验证真实线上面试中的完整低延迟链路：

```text
macOS 双路音频采集
  → 双路流式 ASR
  → 面试问题焦点识别
  → DeepSeek V4 Flash 回答
  → 本地页面显示
```

V1 优先验证音频采集、角色区分、触发时机、回答延迟和中断行为，不追求完整产品形态。

## 2. V1 范围

包含：

- macOS 系统音频采集，作为 `interviewer` 通道。
- 耳机或电脑麦克风采集，作为 `candidate` 通道。
- 两条独立的实时 ASR WebSocket。
- 面试官 final 触发 Focus Responder。
- 候选人 final 只更新上下文，不触发回答或刷新。
- FAST 与 THINK 两种回答模式。
- 面试官重新说话时取消旧回答。
- 本地 H5 页面显示双路转写、当前问题和回答。
- 全链路延迟和取消事件埋点。

暂不包含：

- RAG 八股题库。
- partial 提前推测性触发。
- 手机端和远程 H5。
- 屏幕截图与视觉模型。
- 云端账号、同步和历史记录。
- 本地模型。

## 3. 模型选择

| 职责 | 模型 | 配置 |
|---|---|---|
| 双路语音识别 | Qwen-Audio-3.0-ASR-Flash-Streaming | 16kHz、单声道、PCM、流式 WebSocket |
| 焦点判断与事实八股 | DeepSeek V4 Flash | 关闭思考、结构化输出 |
| 计算、算法、代码、系统设计 | DeepSeek V4 Flash | Thinking High |

GPT-5.6 Luna 当前通过 Teamorouter 的首字延迟明显高于 DeepSeek，不进入实时主链路。

## 4. 技术栈

### 4.1 macOS 采集器

- Swift。
- ScreenCaptureKit：采集系统输出音频。
- AVAudioEngine：采集麦克风音频。
- AVAudioConverter：统一转换为 16kHz、单声道、16-bit PCM。
- URLSessionWebSocketTask：把两个通道分别发送给本地核心服务。

选择原生 Swift 是因为系统音频、屏幕录制权限和麦克风权限都属于 macOS 原生能力。V1 不引入虚拟声卡依赖。

最低系统版本暂定 macOS 13。首次启动需要请求：

- 屏幕与系统音频录制权限。
- 麦克风权限。

### 4.2 实时核心

- Python 3.11+。
- `asyncio`：事件循环和任务生命周期。
- `websockets`：连接 Qwen ASR 与本地音频通道。
- `AsyncOpenAI`：DeepSeek 流式请求和任务取消。
- FastAPI：本地控制 API 和 UI WebSocket。
- Pydantic：事件与模型输出校验。

现有模型测试、Prompt、路由和异步取消代码可以直接迁移到核心服务。

### 4.3 本地界面

- React + TypeScript + Vite。
- 通过本地 WebSocket 接收状态和增量答案。
- V1 由浏览器打开 `localhost` 页面，后续再封装为 Tauri 或原生窗口。

页面只需包含：

- ASR 和模型连接状态。
- 面试官实时转写。
- 候选人实时转写。
- 当前焦点问题。
- 当前回答。
- 开始、停止和清空按钮。
- 延迟调试面板。

## 5. 进程结构

```text
┌──────────────── macOS Capture Helper ────────────────┐
│ ScreenCaptureKit ── interviewer PCM ─┐              │
│ AVAudioEngine    ── candidate PCM ───┼── localhost  │
└──────────────────────────────────────┘              │
                                                      ▼
┌──────────────── Python Realtime Core ────────────────┐
│ Audio Gateway                                       │
│   ├── ASR Session A → interviewer events            │
│   └── ASR Session B → candidate events              │
│                                                     │
│ Conversation Store → Event Router → Focus Responder │
│                                      ├── FAST       │
│                                      └── THINK      │
│                                                     │
│ UI Event Hub → local WebSocket                      │
└─────────────────────────────────────────────────────┘
                              │
                              ▼
                    React Local Web UI
```

## 6. 本地音频协议

采集器分别连接：

```text
ws://127.0.0.1:<port>/ws/audio/interviewer
ws://127.0.0.1:<port>/ws/audio/candidate
```

连接后的第一条消息是 JSON 元数据：

```json
{
  "sample_rate": 16000,
  "channels": 1,
  "sample_format": "pcm_s16le",
  "frame_duration_ms": 100
}
```

后续消息发送带时间戳的二进制音频包：

```text
8-byte little-endian Float64：captured_at Unix 时间戳
3200-byte pcm_s16le：100ms 音频
```

每包共 3208 字节。每个通道独立连接、独立重连，候选人通道故障不得阻塞面试官通道。

## 7. 转写事件

核心服务把 ASR 输出统一为：

```json
{
  "event_id": "uuid",
  "channel": "interviewer | candidate",
  "phase": "partial | final",
  "text": "Redis 为什么这么快",
  "utterance_id": "uuid",
  "audio_started_at": 0,
  "audio_ended_at": 0,
  "received_at": 0
}
```

`partial` 允许覆盖同一 `utterance_id` 的旧文本；只有 `final` 会写入正式对话上下文。

## 8. 模型触发规则

### 8.1 面试官事件

`interviewer.partial`：

- 更新实时字幕。
- 如果正在等待 Focus 合并窗口，重置 300ms 静默计时。
- 不取消已经运行的 Focus，也不触发新请求。
- V1 不在 partial 阶段发起新模型请求。

`interviewer.final`：

- 写入对话上下文。
- 递增 `conversation_revision`。
- 启动或重置 300ms 静默窗口，最大合并等待 1200ms。
- 窗口结束后生成最新 generation，并抢占旧 Focus 请求。
- 旧请求覆盖的 final 不删除，全部进入最新 8K Prompt。

### 8.2 候选人事件

`candidate.partial`：

- 只更新实时字幕。
- 不取消回答。
- 不调用模型。

`candidate.final`：

- 写入对话上下文，供后续追问使用。
- 不调用模型。
- 不刷新当前回答。
- 不改变当前焦点问题。

V1 不识别“我不会”“帮我回答”等候选人求助语句。后续版本再增加显式快捷键或本地规则。

## 9. Focus Responder 协议

每次输入是极简 Markdown：

```markdown
# 历史焦点

## Focus 1
Q: Redis 为什么快？
A: Redis 快主要因为内存、单线程和 I/O 多路复用。

# 最近对话
- C: 我刚才主要回答了内存。
- I: 除了内存呢？
- I: 那 I/O 模型呢？
```

输出固定为：

```json
{
  "action": "WAIT | RESPOND",
  "answer_mode": "NONE | FAST | THINK",
  "focus_question": "完整、自包含的问题",
  "answer": "FAST 时返回，THINK 时为空"
}
```

处理规则：

- `WAIT`：保留监听状态，不显示新答案。
- `RESPOND + FAST`：更新焦点并显示 `answer`。
- `RESPOND + THINK`：更新焦点，再发起 Thinking High 请求。
- 只有结果 generation 等于 active generation 时才能提交。
- 新 committed Focus 提交后才取消旧 THINK 答案；已显示部分保存为 interrupted answer。

## 10. 状态机

```text
LISTENING
  └── interviewer.final → DEBOUNCING

DEBOUNCING
  ├── 新 partial/final → 重置静默窗口
  └── 窗口结束 → EVALUATING

EVALUATING（单个 active generation）
  ├── WAIT → LISTENING
  ├── FAST → ANSWERING_FAST
  ├── THINK → ANSWERING_THINK
  └── 新窗口结束 → 抢占旧 generation → EVALUATING

ANSWERING_FAST / ANSWERING_THINK
  ├── completed → LISTENING
  └── 新 committed Focus → 取消旧答案 → ANSWERING_FAST/THINK
```

候选人的 partial 和 final 不造成状态跳转。

## 11. 上下文策略

V1 在内存中完整保存本次面试的 `final_turns`，不因 Token 预算删除原始对话。每次 Focus 生成固定 8K 总输入：

- System Prompt 约 400 tokens。
- 最近时间有序对话目标约 6000 tokens。
- 多个历史 committed Focus/Answer 目标约 1600 tokens。
- 两部分可动态借用未使用空间。
- 全中文按约 1 token ≈ 1.7 字符估算，并记录 API 实际 usage 校准。
- 删除无意义噪声，合并明显连续的同角色碎片。
- 最近 committed Focus 始终携带，确保推荐回答不会丢失。
- Prompt 只包含 Markdown I/C 对话，不发送 turn ID、generation 或调度状态。

音频默认不落盘，转写默认仅保存在内存。调试日志必须通过显式配置开启，并对 API Key 脱敏。

## 12. UI 事件

核心服务向界面发送：

```text
session.status
transcript.partial
transcript.final
focus.updated
answer.started
answer.delta
answer.completed
answer.cancelled
latency.updated
audio.connected
audio.disconnected
audio.level
error
```

所有 answer 事件都必须包含：

```json
{
  "focus_id": "uuid",
  "conversation_revision": 12
}
```

界面只接受当前 revision 的事件。

FAST 的结构化 JSON 可以在完整解析后一次显示。若后续需要更强的流式体验，再实现对 `answer` 字段的增量 JSON 解码；V1 不为节省几百毫秒引入不稳定解析。

## 13. 超时、取消与重连

- 所有模型调用使用异步任务。
- 新 generation 启动时取消旧 Focus 请求；旧结果通过 generation 再次防护。
- 面试官 partial 不取消正在运行的 Focus。
- Focus 请求超时设为 5 秒，失败不删除 final。
- THINK 请求超时设为 20 秒。
- 超时后不自动重复回答，等待下一事件或用户手动重试。
- 两条 ASR 连接独立指数退避重连。
- ASR 重连期间保留另一通道和 UI 状态。
- 本地连接断开时采集器最多缓存约 3 秒 PCM，超过后丢弃旧帧，避免恢复后产生高延迟积压。

## 14. 延迟埋点与验收

每个问题记录：

```text
audio_end_at
asr_final_at
focus_request_at
focus_first_byte_at
answer_visible_at
answer_completed_at
cancel_requested_at
cancel_completed_at
```

V1 验收目标：

| 指标 | 目标 |
|---|---:|
| ASR final P95 | ≤ 1.0s |
| FAST 端到端可见 P95 | ≤ 2.5s |
| THINK 端到端可见 P95 | ≤ 5.0s |
| JSON 可解析率 | 100% |
| 新面试官发言后的 UI 停止转发 | ≤ 50ms |
| 候选人 final 触发模型次数 | 0 |
| 双路连续运行 | ≥ 30min |

页面延迟均来自真实时间戳：采集延迟是音频回调到本地后端，ASR 延迟是语音结束到 final，模型延迟是请求到可见回答，端到端延迟是语音结束到可见回答。

## 15. 建议目录结构

```text
apps/
  capture-macos/       # Swift ScreenCaptureKit + AVAudioEngine
  web/                 # React + TypeScript + Vite
backend/
  app/
    api/               # FastAPI 与本地 WebSocket
    audio/             # PCM 通道与格式校验
    asr/               # 两条 Qwen ASR Session
    conversation/      # final 对话窗口与 revision
    orchestration/     # 事件路由、状态机、取消
    models/            # DeepSeek Focus/FAST/THINK
    telemetry/         # 延迟与错误埋点
tests/
  fixtures/
  integration/
```

## 16. 开发顺序

1. 创建 Python 实时核心骨架和事件类型。
2. 接入现有双路 ASR 测试代码，支持本地 PCM WebSocket。
3. 实现事件路由、revision 和候选人不触发规则。
4. 接入 AsyncOpenAI Focus Responder 与取消逻辑。
5. 创建最小 React 页面。
6. 实现 Swift 双路采集器和权限处理。
7. 用真实耳机、麦克风和会议软件完成 30 分钟测试。
8. 根据真实延迟决定是否加入 partial 提前触发。

## 17. V1 关键风险

- ScreenCaptureKit 与腾讯会议、飞书、Zoom 同时运行时的系统音频稳定性。
- 部分设备可能把麦克风监听声混入系统输出，需要后续做文本去重。
- ASR 对重叠说话、口音、网络压缩和英文术语的准确率。
- 面试官短暂停顿造成 ASR 提前 final，导致一次 WAIT 和一次后续调用。
- 本地 H5 在共享整个屏幕时可能被面试官看到；V1 只验证链路，手机端或隐蔽显示属于后续产品方案。

以上风险不影响 V1 的模型和事件协议，可以通过真实会议测试逐项验证。
