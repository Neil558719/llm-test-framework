# 里程碑 15：Trace 存储与反馈 API 设计

**Issue：** [#52](https://github.com/Neil558719/llm-test-framework/issues/52)  
**状态：** 已确认设计，待实施  
**范围：** V3 的第一个里程碑；不包含人工复核、YAML 回归晋级、趋势分析或线上离线关联。

## 目标与边界

平台需要持久化可安全查询的线上质量证据，并将用户反馈关联到同一 Trace。它必须采集
请求、响应、工具调用、Token、成本和版本的**脱敏摘要**，默认保留 30 天，并且不让
遥测链路故障改变参考 Agent 的业务结果。

实现保留以下系统边界：

- `qe_platform` 拥有 Trace、反馈、存储、HTTP API 与保留策略；不把质量断言放进
  `reference_agent`。
- 参考 Agent 只在显式配置遥测端点、上报令牌和哈希密钥时创建可选上报器。默认是
  no-op；任何上报、序列化或网络错误均被吞掉并留在平台侧诊断，不影响 `/api/chat`
  或 `/api/chat/stream` 的状态、正文、Trace ID 或延迟结果。
- 参考 Agent 的会话数据库与平台的遥测数据库使用不同配置项和文件。默认遥测库是
  `telemetry.db`，而不是 `reference_agent.db`。
- FastGPT 不在适配、事件、文档、测试、CI 或部署范围内。

## 架构

```text
Reference Agent
  Chat/Stream response (ResponseEnvelope)
            |
            | optional best-effort HTTP event, no request/answer plaintext
            v
qe_platform.telemetry API
  input validation + ingest-token authentication
            |
            v
TelemetryRepository protocol
  |                         |
  v                         v
SQLiteTelemetryRepository   PostgreSQLRepository boundary (future implementation)
  traces + feedback         explicit unsupported-driver result
            |
            +--> query API / retention-prune CLI
```

新增包按开发流程中的平台分层组织：

- `qe_platform.telemetry`：不可变领域模型、HMAC 脱敏器、事件构造器、HTTP 上报器、
  FastAPI 工厂和保留策略 CLI。
- `qe_platform.storage`：`TelemetryRepository` 协议、SQLite 实现、PostgreSQL
  预留实现及工厂。
- `qe_platform.feedback`：反馈类型、输入校验和 Trace 关联服务。

SQLite 是本里程碑唯一可运行驱动。工厂为 PostgreSQL DSN 保留稳定的协议和显式的
“当前未启用”错误；不会伪造 PostgreSQL 已可用。

## 数据模型与脱敏

`TelemetryTrace` 的主键是 Agent 已生成的 `trace_id`，并包含：应用名、采集时间、
哈希化用户/会话标识、请求/响应 HMAC 指纹与长度、来源标识、工具名称与状态摘要、
总延迟/TTFT、HTTP 或执行状态、Token、成本、模型与 Prompt/知识库/工具版本，以及
经过白名单筛选的业务状态元数据。

系统不持久化下列内容：明文用户消息、答案、API key、Authorization header、原始
请求/响应、原始工具参数或结果、用户 ID、会话 ID、自由文本反馈。标识和正文指纹均
使用 `HMAC-SHA256(QE_TELEMETRY_HASH_KEY, value)`；相同密钥下可关联，不能从数据库
直接还原。递归输入检查拒绝敏感字段名（如 `message`、`answer`、`authorization`、
`api_key`、`tool_arguments`）以及未声明字段。

反馈记录仅保存反馈类别、Trace 外键、反馈方的 HMAC 标识、来源和时间。类别固定为：
`correct`、`inaccurate`、`irrelevant`、`incomplete`、`hallucination`、
`tool_execution_error`、`slow_response`。自由文本说明留给里程碑 16 的人工复核工作流，
避免在 V3 起点引入未定义的个人信息处理。

## API、认证与查询

平台独立应用由 `create_telemetry_app(settings, repository)` 构造：

| 端点 | 行为 |
| --- | --- |
| `POST /api/traces` | 验证脱敏 Trace 事件；要求 `X-QE-Telemetry-Token`；幂等写入同一 Trace ID。 |
| `GET /api/traces/{trace_id}` | 返回单个已保存的脱敏 Trace 和关联反馈摘要。 |
| `GET /api/traces` | 按应用、时间范围、模型、版本、状态、Trace ID 分页查询；不返回任何被禁止字段。 |
| `POST /api/traces/{trace_id}/feedback` | 验证固定反馈类别；Trace 不存在返回 404；写入关联反馈。 |
| `GET /api/feedback` | 按 Trace、类别、应用和时间范围分页查询。 |

上报认证令牌只用于 Trace 写入；它不会写入日志、数据库、报告或异常文本。读取与反馈
授权属于后续生产认证边界，本地服务以平台受控访问为前提，并在文档中明确该限制。

## 保留策略

`TelemetrySettings` 从环境读取独立数据库路径、哈希密钥、上报令牌和
`QE_TELEMETRY_RETENTION_DAYS`。保留期默认 30，必须为正整数。查询默认排除已过期的
Trace；`telemetry-prune` CLI 调用仓储的事务性 `prune_expired(now)`，删除过期 Trace
及其级联反馈并输出删除数。测试用显式时钟证明边界为“采集时间 + 30 天”。

## Reference Agent 集成

`create_app` 可注入 `telemetry_sink` 供测试，生产默认从环境构造 sink。`_run_chat`
在完整 `ResponseEnvelope` 已生成、成本已计算后，将 `TelemetryEvent` 交给 sink。事件
只读取安全字段；sink 异常不会改变已准备返回给调用者的对象。流式接口复用同一
`_run_chat`，因而每次业务请求只上报一个 Trace，完成事件仍携带原始业务 Trace ID。

## 验收与测试

1. 领域模型和脱敏器测试：稳定 HMAC、禁止字段递归拒绝、工具参数及明文不落库。
2. SQLite 仓储测试：幂等 Trace、版本/时间/状态查询、反馈外键、分页、并发读写和
   30 天过期清理。
3. API 测试：令牌认证、输入 400、Trace 404、七类反馈、查询只输出脱敏字段。
4. Agent 集成测试：上报事件含 Token/成本/版本/工具摘要；无配置不发送；网络失败或
   sink 失败时 `/api/chat` 与 SSE 仍成功且无敏感内容泄露。
5. 文档和 CI 测试：使用安全环境变量示例、不增加 FastGPT；现有 Reference Agent、
   V1 gate、UI、独立压测和 Dify 契约回归保持通过。

里程碑完成前还必须按仓库生命周期完成 Issue、分支、测试、Push、PR、Actions、独立
审查、合并、Release、本机类生产部署及 Issue 跟踪。真实线上平台认证、人工复核、
YAML 晋级和趋势闭环不在本里程碑的完成定义中。
