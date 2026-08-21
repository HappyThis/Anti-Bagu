# Anti-Bagu 技术验证报告

测试日期：2026-08-21

## 结论

当前方案可以进入桌面端 PoC 开发：

```text
ASR：Qwen-Audio-3.0-ASR-Flash-Streaming
回答模型：DeepSeek V4 Flash
事实型问题：非思考模式
计算/算法/代码/系统设计：思考模式 High
```

不应对所有问题统一开启思考模式。事实型八股使用思考模式不会明显提升准确率，却会把首字 P95 从约 1 秒增加到约 5 秒。正确策略是本地快速门控和模型路由。

## 最终实时链路

```text
系统音频 ──→ ASR A ──→ interviewer
麦克风   ──→ ASR B ──→ candidate
                         │
                         ▼
                   本地事件与硬规则
                         │
              ┌──────────┴──────────┐
              │                     │
       明显计算/代码/算法       其他面试发言
              │                     │
              ▼                     ▼
       DeepSeek Thinking       Focus Responder
                                     │
                          ┌──────────┴─────────┐
                          │                    │
                        WAIT                RESPOND
                                               │
                                   ┌──────────┴─────────┐
                                   │                    │
                                 FAST                 THINK
                                   │                    │
                              直接显示         DeepSeek Thinking
```

## 协议收敛

最初计划使用 `WAIT / ANSWER / UPDATE`。测试发现 ANSWER 与 UPDATE 对系统的行为完全相同：都需要更新当前焦点、取消旧回答并开始新回答。强行区分会产生语义歧义和额外推理。

最终协议收敛为：

```json
{
  "action": "WAIT | RESPOND",
  "answer_mode": "NONE | FAST | THINK",
  "focus_question": "完整、自包含的问题",
  "answer": "FAST 时直接返回；THINK 时为空"
}
```

## ASR 测试

### 单路实时推流

测试音频按真实速度、100ms PCM 分块发送，VAD 静音阈值为 400ms。

| 指标 | P50 | P95 |
|---|---:|---:|
| WebSocket 建连 | 57ms | 66ms |
| partial 相对音频进度落后 | 44ms | 53ms |
| final 相对语音结束延迟 | 753ms | 787ms |

### 双路并发

模拟系统音频和麦克风同时维持两条连接，共 3 组、6 条流。

| 指标 | P50 | P95 |
|---|---:|---:|
| WebSocket 建连 | 55ms | 62ms |
| partial 相对音频进度落后 | 40ms | 45ms |
| final 相对语音结束延迟 | 756ms | 766ms |

6 条流全部识别正确，双路并发没有造成明显延迟增长。

### 长连接多句测试

在同一个 WebSocket 任务中实时发送 34.27 秒音频，包含 8 个技术问题和句间静音。

| 指标 | 结果 |
|---|---:|
| 源问题 | 8 |
| final 分句 | 8 |
| 语义完整 | 8/8 |
| 术语精确字符串命中 | 7/8 |
| final 延迟 P50 | 0.67s |
| final 延迟 P95 | 0.91s |

未精确命中的一句将“有哪些改进”转成“有哪些改”，语义仍可被 Focus Responder 理解。这说明 ASR 结果不能通过精确字符串规则判断问题完整性。

## 回答模型测试

### Qwen3.7 Flash

Qwen3.7 Flash 被排除为主回答模型。

| 配置 | 速度 | 问题 |
|---|---:|---|
| 无思考 | 首字约 0.4～0.5s | `9.9` 与 `9.11` 连续 5 次全部答错；八股题有事实错误 |
| `thinking_budget=128` | 首字约 1s | 出现思考内容泄漏 |
| `thinking_budget=256` | 首字约 2～2.7s | 仍有思考泄漏和不严谨表述 |
| 默认思考 | 约 9～12s | 延迟不可接受 |

### DeepSeek V4 Flash

思考模式在数学题上重复 5 次全部正确且无泄漏；Redis 八股题首字 P50 约 1.31 秒、P95 约 1.49 秒。

非思考模式使用 60 道常见计算机八股进行专项测试。收紧 Prompt、关闭本地事实注入后的单轮结果如下：

| 指标 | 结果 |
|---|---:|
| 题目数 | 60 |
| 首字 P50 | 0.59s |
| 首字 P95 | 0.94s |
| 首字最大值 | 1.05s |
| 完整回答 P50 | 1.34s |
| 完整回答 P95 | 1.76s |
| JSON 可解析 | 60/60 |
| 思考内容泄漏 | 0/60 |

多轮并发复测中，首字 P50 为 0.59～0.75 秒，P95 为 0.78～1.03 秒，说明延迟比较稳定。它仍不适合直接处理数值计算，因为可能先流出错误结论再自我纠正。

### GPT-5.6 Luna（Teamorouter）

使用与 DeepSeek 完全相同的 60 道八股题、Prompt、流式 JSON 和并发数进行测试。

网关在未指定推理强度时会对少数题自动使用推理，单题出现 69～226 个 reasoning tokens，首字最长 7.07 秒。显式传入 `reasoning_effort=none` 后，60/60 的 reasoning tokens 均为 0，因此非思考路径必须显式配置该参数。

关闭推理后的 60 题结果：

| 指标 | 结果 |
|---|---:|
| 题目数 | 60 |
| 首字 P50 | 2.09s |
| 首字 P95 | 5.11s |
| 首字最大值 | 9.23s |
| 完整回答 P50 | 3.25s |
| 完整回答 P95 | 6.27s |
| JSON 可解析 | 60/60 |
| reasoning tokens | 全部为 0 |
| 思考内容泄漏 | 0/60 |

为排除 6 路并发导致的网关排队，又选取 10 道完全相同的问题串行对照：

| 模型 | 首字 P50 | 首字 P95 | 完整回答 P50 | 完整回答 P95 |
|---|---:|---:|---:|---:|
| DeepSeek V4 Flash | 0.58s | 0.70s | 1.30s | 1.59s |
| GPT-5.6 Luna | 2.36s | 4.19s | 2.90s | 5.84s |

Luna 的知识质量优于 DeepSeek：人工严格审查约 56/60 可直接使用，线程状态、现代类加载器、最左前缀、Redis Cluster、DNS 和 Token 等问题回答更准确。剩余问题主要是 Spring 非 public 事务方法仍缺少版本与代理类型条件，以及 AQS、TIME_WAIT、ReentrantLock 偶尔遗漏 CAS、2MSL、Condition 等关键点。

结论：Luna 更准确，但通过 Teamorouter 的当前延迟不满足实时 FAST 路径。它可以作为离线评测模型或后台第二意见，不应替换 DeepSeek 主回答模型。对面试助手而言，本地事实库比把 FAST 路径切到 Luna 更符合低延迟目标。

## Focus Responder 测试

测试集包含 36 个场景：

- 12 个 WAIT。
- 12 个新问题。
- 12 个追问、约束或话题更新。

最终 Prompt 和 `WAIT / RESPOND` 协议下，非思考模式连续两轮共 72 个场景全部通过：

| 指标 | 结果 |
|---|---:|
| 动作准确率 | 72/72 |
| JSON 错误 | 0 |
| 思考泄漏 | 0 |
| 回答超长 | 0 |
| 首字 P95（两轮） | 0.82～1.17s |
| 最大首字时间 | 1.22s |

### 输入 Token 预算

使用极简 Markdown Prompt 对 1K～128K 输入进行了宽扫描，并对新问题、追问、WAIT、THINK 和关键内容位于开头/中间/结尾等场景执行超过 100 次请求。

结论：默认目标为 8K tokens，硬上限为 12K tokens。约 12.7K 之后，前置多约束问题在重复测试中稳定丢失数字、一致性和容灾约束；64K 和 128K 的完整响应分别约 3 秒和 6.36 秒。

详见 [Focus 输入 Token 预算实验报告](FOCUS_TOKEN_BUDGET_REPORT.md)。

## FAST / THINK 路由

20 个路由场景覆盖事实八股、数值比较、代码输出、算法、SQL、QPS 估算、系统设计和并发约束。

最终规则：

- 数值大小比较、算术、容量、QPS 和概率估算必须 THINK。
- 明确要求写代码、算法求解、SQL、系统设计或复杂动态约束时 THINK。
- 稳定事实、标准流程、常规对比和简单错误模式使用 FAST。

| 指标 | 结果 |
|---|---:|
| 本地规则准确率 | 20/20 |
| 模型路由准确率 | 20/20 |
| 模型路由首字 P95 | 1.12s |

本地规则优先处理明显 THINK，可以跳过一次模型路由调用。

## 回答质量

质量集已扩展到 60 道常见知识型八股，覆盖 Java、JVM、Spring、MySQL、Redis、网络、操作系统、分布式与基础算法。所有题目均关闭思考，不混入计算、代码生成或系统设计题。

自动关键词检查单轮通过 45/60，但它把大量同义表达当成失败，例如“叶子存整行”没有命中“叶子节点/行数据”，“逻辑地址空间”没有命中“虚拟地址”。因此自动分数只用于发现遗漏，不能直接等同事实准确率。

人工按“整段回答不存在实质错误或误导”严格审查，52/60 可以直接使用。其余 8 道的核心方向大多正确，但存在下面这些风险：

| 风险类型 | 典型表现 |
|---|---|
| 状态定义错误 | Java `Thread.State` 说有六种，却把就绪和运行拆开列成七项；规范中二者同属 `RUNNABLE` |
| 旧口诀绝对化 | 把联合索引写成“跳过最左列就完全失效、范围条件后列不生效”，忽略优化器、索引下推和 skip scan |
| 组件关系错误 | 说 Redis Sentinel 可以和 Redis Cluster 结合部署；官方定位是 Sentinel 服务非 Cluster Redis |
| 递归与迭代混淆 | 把客户端、递归解析器以及根/TLD/权威服务器之间的 DNS 查询过程混为一谈 |
| 概念边界过窄 | 把所有 Token 都说成自包含签名凭证，并把跨域当成 Token 独有能力 |
| 版本实现过时 | 双亲委派示例固定写成 `ExtClassLoader`；现代 JDK 已改为平台类加载器 |
| 次要作用归因错误 | 虚拟节点主要改善一致性哈希的数据分布和负载均衡，不应简单归结为减少迁移量 |
| 框架规则缺少版本条件 | 把 Spring 非 public 事务方法一律判为无效；Spring 6 的类代理已支持 protected/package-visible 方法 |

已审核的短事实片段能够稳定修正 AQS、`synchronized`、线程状态、Spring 事务、最左前缀、TLS、epoll 和 CAP 等已覆盖问题，检索成本是毫秒级。但这不能证明未覆盖知识也可靠。

最终结论是：DeepSeek V4 Flash 关闭思考足以承担八股回答主路径，速度合格、核心知识较强，但裸模型约 87% 的严格可用率不够稳。生产方案必须使用“非思考模型 + 本地审核事实库”，并持续用回归题集补充暴露出的错误。开启思考不能替代事实校正。

## 端到端延迟

### FAST

真实速度中文音频经过 ASR 和非思考 Focus Responder：

| 问题 | 端到端首字 |
|---|---:|
| Redis 为什么快 | 2.02s |
| volatile 的作用 | 1.83s |

结合 ASR 与模型分布，FAST 路径 P95 预计约 2.1 秒。

### THINK

本地门控后跳过模型路由，直接调用思考模式：

| 问题 | 端到端首字 | 结果 |
|---|---:|---|
| 9.9 与 9.11 | 3.64s | 正确 |
| 峰值 QPS 估算 | 2.90s | 正确，约 463 QPS |

THINK 允许更高延迟，验收阈值建议设为 P95 不超过 5 秒。

## 取消与中断

同步 SDK 的 `stream.close()` 会立即返回，但阻塞读取线程在 2 秒内没有退出，不适合长时间运行。

异步 SDK 通过取消消费任务并关闭流，5 次测试全部成功：

| 指标 | 结果 |
|---|---:|
| 成功取消 | 5/5 |
| 取消耗时 P50 | 0.48ms |
| 最大取消耗时 | 0.90ms |

生产实现使用异步 HTTP 客户端和结构化任务取消。最新方案不再因任意 interviewer partial 取消请求；新的 300ms 合并窗口结束并启动更高 generation 时，才抢占旧 Focus。新 committed Focus 成功后再取消旧 THINK 答案。

## 验收阈值

| 指标 | 目标 | 当前结果 |
|---|---:|---:|
| ASR final P95 | ≤1.0s | 0.91s |
| FAST 端到端 P95 | ≤2.5s | 约 2.1s |
| THINK 端到端 P95 | ≤5.0s | 当前样例 2.9～3.6s |
| Focus 动作准确率 | ≥98% | 100% |
| 模式路由准确率 | ≥95% | 100% |
| JSON 可解析率 | 100% | 100% |
| 思考泄漏 | 0 | 0 |
| 异步取消成功率 | 100% | 100% |

## 已知风险与下一阶段

当前已验证真实 macOS 采集与合成中文问题，以下项目尚未验证：

1. 腾讯会议、飞书、Zoom 等真实会议软件的 30 分钟连续采集。
2. 不同真人口音、麦克风、网络压缩、重叠说话和背景噪声。
3. macOS 系统音频与耳机麦克风的长期双路采集稳定性。
4. 大规模八股事实片段库的覆盖率和维护方式。
5. 屏幕截图输入。

下一阶段应进行真实会议软件与真人语音的长期测试，不再继续横向测试模型。

## macOS 真实采集联调

已完成 ScreenCaptureKit 系统音频、AVAudioEngine 麦克风、双路 Qwen ASR、DeepSeek 回答和 React 页面联调。

一次真实系统音频合成问题“Java 的 volatile 有什么作用？”测得：

| 指标 | 结果 |
|---|---:|
| 系统音频采集到本地后端 | 0.26ms |
| 麦克风采集到本地后端 | 0.51ms |
| ASR final | 758ms |
| 模型完整回答 | 2495ms |
| 端到端可见 | 3254ms |

系统音频正确归入 interviewer 并触发回答；麦克风正确归入 candidate，candidate final 不触发刷新。页面显示两路真实 Canvas 声波和延迟快照。

本轮模型延迟高于之前 API 独立测试，说明真实链路必须持续记录分位数，不能用单次最快值代替线上延迟。macOS 权限修改后需要完整重启宿主应用，否则 ScreenCaptureKit 可能返回 `SCStreamErrorFailedApplicationConnectionInterrupted`。

## 安全事项

测试使用的 API Key 曾经出现在聊天内容中。测试结束后必须在阿里云百炼、DeepSeek 和 Teamorouter 控制台撤销并重新创建，生产 Key 不得写入仓库。

## 官方参考

- [阿里云实时 ASR WebSocket API](https://help.aliyun.com/zh/model-studio/fun-asr-realtime-websocket-api)
- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek V4 Flash 模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [Oracle `Thread.State`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html)
- [Oracle 类加载、链接与初始化规范](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html)
- [Spring `@Transactional` 方法可见性](https://docs.spring.io/spring/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Redis Sentinel 官方文档](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis 过期键官方文档](https://redis.io/docs/latest/commands/expire/)
- [ICANN DNS 根服务说明](https://www.icann.org/en/rssac/faq)
