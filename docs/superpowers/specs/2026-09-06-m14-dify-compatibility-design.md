# 里程碑 14：Dify 适配扩展设计

## 目标

为质量平台提供受限、可验证且可审计的 Dify Chat 应用兼容能力。平台将把 Dify 的
`POST /chat-messages` blocking 响应转换为既有 `ResponseEnvelope`，并用离线 HTTP
契约夹具和真实环境可选门禁验证已声明能力。该设计实现开发流程中“Dify 接入能力与
限制被测试和记录”的验收项。

## 范围与约束

- 主要被测系统仍是 Reference Agent；Dify 是次要兼容目标。
- 新能力属于 `qe_platform`，Reference Agent 不导入或依赖 Dify 代码。
- 保持 `AppResponse`、`ResponseEnvelope`、`ApplicationAdapter`、YAML 场景 DSL 和
  V1 gate 的公共兼容性。
- 只支持 Dify **Chat 应用**的 blocking `POST /chat-messages` 调用。请求包含
  `inputs`、`query`、`response_mode`、`user`，并在后续同一平台 session 请求中包含
  Dify 返回的 `conversation_id`。
- 不把 API key、Authorization 值、原始请求正文或原始上游响应正文写入异常、报告、
  `raw_response`、版本库或配置文件。
- 不在 CI 调用真实 Dify；本地 HTTP 契约夹具是自动化验收，真实 Dify 调用只能由用户
  显式提供 `DIFY_BASE_URL` 和 `DIFY_API_KEY` 后启动。
- 不添加 FastGPT 依赖、适配器、场景、部署步骤或 CI 作业。

## 方案比较

### 方案 A：平台级 Chat 适配器与声明式能力矩阵（采用）

在 `qe_platform.adapters.dify` 中实现受限的 Chat blocking 适配器、严格环境配置与
能力描述；用独立 CLI 将两个普通 YAML 对话场景与能力矩阵写入 JSON/HTML 报告。测试
使用标准库 HTTP 服务模拟 Dify 的真实 URL、请求负载与多轮响应。

优点是与现有 `ScenarioRunner` 和 `ResponseEnvelope` 对齐，范围和不可观测能力均可被
明确验证。真实服务验证不依赖 CI 密钥。

### 方案 B：扩展遗留 `examples/dify_bot`

只给示例增加更多 pytest 用例，改动最少，但仍返回 `AppResponse`，无法进入平台场景
执行器、统一报告或能力门禁，也无法满足本里程碑的交付证据要求。因此不采用。

### 方案 C：同时实现 Chat、Workflow、流式、多模态和文件 API

可覆盖更多 Dify 功能，但这些端点与响应协议不同，缺少当前平台的统一场景模型和真实
服务验收条件，会把“至少支持已声明能力”的目标扩张为不可验证的集成项目。因此不采用。

## 架构与数据流

```text
Dify YAML 场景
       │
       ▼
ScenarioRunner ──► DifyChatAdapter ──► POST {base_url}/chat-messages
       │                    │                         │
       │                    ▼                         ▼
       │          session_id → conversation_id     Dify blocking JSON
       ▼                    │                         │
ResponseEnvelope ◄─────────┴──── answer/sources/id ───┘
       │
       ▼
DifyCompatibilityReport = 场景结果 + 能力矩阵 + 限制
```

`DifyChatAdapter` 以调用方给出的平台 `session_id` 为键，在实例内维护 Dify
`conversation_id`。第一轮不发送 `conversation_id`；成功响应中的 ID 仅用于后续同一
用户和 session 的请求。不同 session 和不同用户绝不共享会话 ID。

适配器使用标准库 `urllib.request`，不增加运行时依赖。请求成功后只把以下可观测且无
敏感数据的字段映射到统一协议：

| Dify 字段 | 平台字段 | 规则 |
| --- | --- | --- |
| `answer` | `answer` | 必须为字符串 |
| `conversation_id` | `conversation_id` | 必须为非空字符串，供下一轮调用 |
| `message_id` | `trace_id` | 可选字符串；不可用时为空 |
| `retriever_resources` 或 `metadata.retriever_resources` | `sources` | 读取每项 `content`、`segment_content` 或 `segment` 文本 |
| 资源数量、Dify message ID | `metadata` | 仅记录可观测元数据 |

不会虚构 Dify 的工具调用、业务状态、Token、成本、TTFT 或模型版本；这些字段保持空值。
`raw_response` 始终是空对象，避免把用户消息、凭据或 Dify 私有响应写入报告。

## 配置、错误和安全边界

`DifyAdapterConfig` 是不可变配置，包含 `base_url`、`api_key`、`inputs` 与
`timeout_seconds`。`from_environment()` 读取：

| 环境变量 | 规则 |
| --- | --- |
| `DIFY_BASE_URL` | 必填，指向带或不带 `/v1` 的 API 根路径 |
| `DIFY_API_KEY` | 必填，只在内存中构造 Bearer 请求头 |
| `DIFY_INPUTS_JSON` | 可选 JSON 对象，作为静态应用输入；非对象拒绝 |
| `DIFY_TIMEOUT_SECONDS` | 可选正数，默认 30 秒 |

配置错误、网络错误、非 2xx 响应、无效 JSON 和无效成功负载都抛出
`ApplicationAdapterError`。错误文本只含稳定分类和 HTTP 状态码，绝不回显上游正文。
适配器不支持 `response_mode=streaming`；任何尝试构造非 blocking 配置都会在本地失败。

## 能力矩阵

报告和文档使用同一个不可变 `DifyCapabilityMatrix`，避免把限制只写在 README 中：

| 能力 | 状态 | 验证方式 |
| --- | --- | --- |
| Chat blocking 消息 | 支持 | 离线 HTTP 契约门禁检查请求与回答映射 |
| 多轮会话 | 支持 | 第二请求必须携带首轮 `conversation_id` |
| 检索来源可观测性 | 条件支持 | 顶层及 metadata 资源均映射；服务未返回资源时 `sources=[]` |
| Bearer 鉴权与错误分类 | 支持 | 请求头、401/5xx、网络和无效 JSON 夹具测试 |
| Dify 工具调用与业务状态 | 不支持 | Dify Chat API 未暴露可与 Reference Agent 等价的工具/状态协议 |
| Token、成本、模型版本 | 不支持 | blocking Chat 返回并非稳定的完整计量协议 |
| SSE/TTFT | 不支持 | 本里程碑不实现 streaming 适配器 |
| Workflow、Completion、文件、多模态 | 不支持 | 端点和响应协议不同，未在此里程碑实现 |

## 场景、门禁和报告

新增两个打包 YAML 场景：一个验证回答与检索来源，一个验证同一平台 session 的两轮
对话。它们只使用平台可观测的 `response.contains` 和 `sources_present` 断言，不声明
Reference Agent 专有工具或业务状态。

`dify-compat-gate` CLI 从固定资产目录加载场景，使用 `DifyChatAdapter.from_environment`
并生成 JSON 与自包含 HTML。JSON 顶层包含 `capabilities`、`limitations`、普通运行报告
和 `gate_passed`。退出码为：`0` 通过，`1` 执行或报告错误，`2` 配置错误，`3` 断言门禁
失败。CLI 不打印 key，不接受 key 命令行参数。

CI 不运行真实网络调用；`tests/test_dify_gate.py` 用本地标准库 HTTP 服务运行完整门禁，
验证报告、退出码和请求会话关联。这样自动化证据实际覆盖适配器协议，而不是只验证静态
文档。

## 文档与交付

README 将旧的 Dify 文档链接改为新的 `docs/Dify 兼容性测试指南.md`。指南记录环境配置、
真实环境门禁命令、支持范围、报告脱敏行为和不支持能力。开发流程状态表先记录
“实施中”，全部本地、CI、PR、Release 和本机类生产交付完成后再改为完成。

本里程碑遵循 Issue #49 → `codex/m14-dify-compatibility` → 本地测试 → PR → Actions →
独立审查 → 合并 → Release → 本机类生产交付与 Issue 关闭的链路。

## 验收标准

1. Dify Chat blocking 的请求、响应、来源、会话延续、错误分类和脱敏均有失败先行的
   离线契约测试。
2. 能力矩阵和限制可由代码报告序列化，报告不含 API key、Authorization 值或消息正文。
3. 打包 Dify YAML 场景可经既有 `ScenarioRunner` 执行；本地 HTTP 夹具的门禁为全绿。
4. 真实 Dify 只通过显式环境变量运行，缺少或无效配置安全失败。
5. 默认回归、V1 gate、Dify 定向门禁、编译、Compose 配置和差异检查通过；CI 新增 Dify
   离线兼容检查。
6. PR、Actions、独立审查、合并、预发布、发布镜像/主服务验收和 Issue 跟踪完成前，不将
   里程碑标记为交付完成。
