# Trace 与反馈 API 指南

本文记录里程碑 15 已交付的 Trace 存储、反馈 API、Reference Agent 遥测上报和保留策略。Trace 与反馈属于质量平台能力，数据库、配置和 API 都与 Reference Agent 的业务数据库分离。

## 配置边界

Trace/反馈平台只通过环境变量接收运行配置，示例不得把密钥、令牌或真实业务数据写进命令行参数、YAML、报告或文档正文。

| 环境变量 | 用途 |
| --- | --- |
| `QE_TELEMETRY_DATABASE` | Trace/反馈 SQLite 数据库路径；默认 `telemetry.db`，不得复用 `REFERENCE_AGENT_DATABASE`。 |
| `QE_TELEMETRY_HASH_KEY` | HMAC 脱敏密钥，用于请求、回答、用户、会话、版本和反馈报告人指纹。 |
| `QE_TELEMETRY_INGEST_TOKEN` | `POST /api/traces` 的写入令牌，也用于 Reference Agent HTTP sink 的 `X-QE-Telemetry-Token` 请求头。 |
| `QE_TELEMETRY_RETENTION_DAYS` | Trace 保留天数，默认 `30`；必须为正整数。 |
| `QE_TELEMETRY_ENDPOINT` | Reference Agent 可选遥测上报目标，例如平台 Trace ingest API 地址；缺少 endpoint、token 或 hash key 时上报为 no-op。 |

`telemetry-prune` 不接收任何命令行参数。它从环境变量读取数据库、HMAC key、ingest token 和保留天数，删除过期 Trace，并依赖外键级联删除关联反馈。

```powershell
$env:QE_TELEMETRY_DATABASE = "C:\path\to\telemetry.db"
$env:QE_TELEMETRY_HASH_KEY = $env:LOCAL_QE_TELEMETRY_HASH_KEY
$env:QE_TELEMETRY_INGEST_TOKEN = $env:LOCAL_QE_TELEMETRY_INGEST_TOKEN
$env:QE_TELEMETRY_RETENTION_DAYS = "30"
telemetry-prune
```

## API

平台应用由 `qe_platform.telemetry.api.create_telemetry_app(settings, repository=None)` 构造。当前交付的端点为：

| 端点 | 行为 |
| --- | --- |
| `POST /api/traces` | 需要 `X-QE-Telemetry-Token`；只接受已经脱敏的 Trace payload；成功返回 `201`。 |
| `GET /api/traces` | 按 application 或 trace_id 分页读取未过期 Trace。 |
| `GET /api/traces/{trace_id}` | 读取单条未过期 Trace；不存在返回 `404`。 |
| `POST /api/traces/{trace_id}/feedback` | 为已存在 Trace 写入反馈类别、报告人指纹和来源；Trace 不存在返回 `404`。 |
| `GET /api/feedback` | 按 trace_id 或 category 分页查询未过期 Trace 关联的反馈。 |

写入示例使用占位符和环境变量。payload 中只能出现脱敏后的字段，不得包含原始 message、answer、user_id、session_id、authorization、token、api_key、raw request/response、tool arguments、tool result 或自由文本反馈。

```bash
curl -X POST "$QE_TELEMETRY_ENDPOINT" \
  -H "Content-Type: application/json" \
  -H "X-QE-Telemetry-Token: $QE_TELEMETRY_INGEST_TOKEN" \
  -d '{
    "trace_id": "trace-example",
    "application": "reference-agent",
    "timestamp": "2026-09-08T00:00:00Z",
    "request_fingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "answer_fingerprint": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    "request_length": 12,
    "answer_length": 8,
    "source": {"user_fingerprint": "1111111111111111111111111111111111111111111111111111111111111111", "session_fingerprint": "2222222222222222222222222222222222222222222222222222222222222222"},
    "tool_calls": [{"name": "query_user", "status": "succeeded"}],
    "metadata": {}, "usage": {}, "cost": null,
    "model_version": {}, "latency": {"status": "succeeded"}
  }'
```

反馈写入只保存固定类别、报告人指纹和来源，不保存自由文本：

```bash
curl -X POST "$QE_TELEMETRY_ENDPOINT/trace-example/feedback" \
  -H "Content-Type: application/json" \
  -d '{"category":"inaccurate","reporter_id":"local-reviewer","source":"ui"}'
```

## 反馈类别

里程碑 15 固定支持七类反馈：

| 类别 | 含义 |
| --- | --- |
| `correct` | 回答正确。 |
| `inaccurate` | 回答不准确。 |
| `irrelevant` | 答非所问。 |
| `incomplete` | 信息不完整。 |
| `hallucination` | 存在幻觉。 |
| `tool_execution_error` | 工具执行错误。 |
| `slow_response` | 响应过慢。 |

## 隐私与保留策略

Trace 默认保留 `30 天`。`prune_expired` 以 Trace 时间戳计算到期边界，删除过期 Trace 时级联删除相关反馈。线上样本和测试数据分库保存；Reference Agent 的业务状态仍在自己的数据库中，Trace/反馈数据库不承载工单或审批业务状态。

平台只持久化指纹、长度、工具名称和状态、版本指纹、Token/成本/延迟指标等质量工程字段。请求明文、回答明文、用户和会话明文、鉴权头、令牌、API key、原始请求响应、工具参数、工具结果和自由文本反馈都在脱敏边界外，模型和仓储会拒绝这些字段。

## 当前限制

当前 `POST /api/traces` 已有 ingest token 校验；读接口 `GET /api/traces`、`GET /api/traces/{trace_id}`、`GET /api/feedback` 以及反馈写入 `POST /api/traces/{trace_id}/feedback` 尚未实现独立读/反馈鉴权。部署到共享环境前，需要在服务前增加网关鉴权或在后续里程碑补齐应用级授权。

PostgreSQL 仅保留工厂边界和错误语义。传入 `postgresql://...` 时会得到 `NotImplementedError("PostgreSQL telemetry storage is not enabled")`，当前可运行驱动为本地 SQLite。

M16 的人工复核、归因、优先级、回归用例晋级和 YAML 导出不属于 M15。M17 的趋势对比、线上离线关联报告、闭环演示和发布验证也不属于 M15。M15 只交付脱敏 Trace 持久化查询、固定反馈 API、保留策略 CLI 和 Reference Agent 可选上报。
