# 里程碑 12：独立异步压测执行器设计

## 目标

为质量平台增加独立于 pytest 插件的异步压测执行器，可对 Reference Agent 的
普通 HTTP 聊天接口和 SSE 流式接口重复发送隔离会话请求，并输出可机器消费的
性能、错误、Token、成本和 Trace 结果。

## 范围与边界

- 压测代码位于 `qe_platform/loadtest/`，通过独立 `llmtest-load` 命令运行。
- 配置使用 YAML，支持目标 URL、HTTP/SSE 模式、请求模板、并发数、请求总数、
  预热、超时和报告路径；不把秘密写入配置回显或报告。
- 每个采样请求生成独立 `session_id`，并允许配置固定 `user_id` 和消息模板。
- 采集端到端延迟、TTFT、HTTP 状态、错误类别、429、SSE 中断、Trace ID、
  Token usage 和成本；聚合为吞吐量和 P50/P95/P99。
- 使用 `httpx.AsyncClient` 与 `asyncio.Semaphore`，不把压测并发塞进 pytest。
- 里程碑 13 才负责 SLA/SLO 阈值门禁；本里程碑只提供原始指标和可选元数据。
- 不新增 FastGPT 支持，不将断言逻辑放入 Reference Agent。

## 数据流

```text
YAML -> LoadTestConfig -> async workers -> SampleResult[]
                         -> MetricsSummary -> JSON/HTML report
```

普通 HTTP 请求读取完整 JSON 响应；SSE 请求在收到第一个 `chunk` 或 `complete`
事件时记录 TTFT，完整 `complete` 事件视为成功，连接异常或缺少完成事件视为
流式中断。服务返回 429 作为独立错误分类，同时计入错误总数。

## 指标口径

- `duration_ms`：从发送请求开始到完整响应/错误结束的单次墙钟时间。
- `ttft_ms`：SSE 首个有效内容事件相对请求开始的时间；非流式为空。
- `throughput_rps`：完成请求数除以压测总墙钟秒数。
- `p50/p95/p99`：成功和失败样本的 `duration_ms` 全体分布，采用相邻顺序统计量
  的线性插值；空样本返回 null。
- `error_rate`：错误样本数 / 总样本数；`429_rate`：429 样本数 / 总样本数。
- `stream_interruption_rate`：SSE 启动后未收到完整事件的样本数 / SSE 总样本数。
- Token 与 cost：只聚合响应中存在的 usage/cost；缺失值保持 null，不猜测价格。

## 错误与安全

配置错误在发压前失败并返回非零退出码；运行时按 `timeout`、`http_error`、
`invalid_response`、`stream_interrupted`、`transport_error` 分类。报告仅保存
脱敏请求元数据、状态码、错误信息、Trace ID 和聚合指标，不保存 API key 或完整
Authorization 头。

## 验收

1. 单元测试覆盖配置校验、分位数、吞吐/错误/429/SSE 中断聚合。
2. 异步集成测试覆盖并发上限、普通 HTTP、429、超时、SSE TTFT 和中断。
3. CLI 测试覆盖 YAML 加载、JSON/HTML 输出和错误退出码。
4. 本地 Reference Agent Docker 类部署压测成功，并运行全量回归。
