# 里程碑 13：故障注入与 SLA/SLO 门禁设计

## 目标

在里程碑 12 的独立异步压测执行器之上，增加可重复、可隔离的故障矩阵与
机器可判定的 SLA/SLO、恢复和成本门禁。Reference Agent 提供受保护的测试
故障钩子，质量平台负责场景编排、断言、报告和退出码，两者仍保持职责分离。

本里程碑对应 GitHub Issue
[#46](https://github.com/Neil558719/llm-test-framework/issues/46)。

## 边界

- Reference Agent 只负责按请求执行获授权的故障，不包含 SLA/SLO 断言。
- 门禁属于 `qe_platform/loadtest/` 的独立执行模式，不进入 pytest 插件。
- 保持 `AppResponse`、既有 `LoadTestConfig` 和 `llmtest-load` 行为兼容；新增
  独立故障门禁配置与命令。
- 默认部署不开放故障能力。只有显式启用并提供非空独立密钥的测试部署才能
  接受故障请求。
- 不增加 FastGPT 依赖、适配器、用例、部署步骤或 CI 验收。
- 真实供应商公网 SLA 和独立云服务器部署不属于本地类生产验收；报告中的
  本机阈值是回归门禁，不作为对外服务承诺。

## 方案选择

采用请求级故障控制。压测门禁请求通过两个 HTTP Header 发送故障控制：

- `X-QE-Test-Token`：与服务端独立测试密钥进行常量时间比较；
- `X-QE-Fault`：严格 JSON 对象，只允许文档列出的故障类型和参数。

请求级对象从 API 入口显式传入存储、模型运行时、业务图和 SSE 生成器，不写入
全局可变状态。这样同一并发批次中的正常请求和故障请求互不影响，也不要求为
每个场景重启容器。

部署级环境变量方案会产生全局故障状态和重启开销，无法证明并发隔离；外部
网络代理可以作为未来的网络真实性增强，但不能独立覆盖数据库和业务恢复。

## 安全模型

服务端读取：

- `REFERENCE_AGENT_TEST_FAULTS_ENABLED`，默认 `false`；
- `REFERENCE_AGENT_TEST_FAULT_TOKEN`，启用时必须为非空值。

启动时若已启用但密钥为空，应用创建失败。请求未携带 `X-QE-Fault` 时完全走
正常路径且不要求测试密钥。携带故障 Header 时：

- 功能未启用、密钥缺失或密钥不匹配：HTTP 403；
- JSON 格式错误、字段未知、类型未知或参数越界：HTTP 400；
- 鉴权和校验通过：只对当前请求创建不可变 `FaultProfile`。

两个控制 Header、密钥值、原始故障 JSON 和用户消息都不进入报告、响应、
Trace 或 SQLite。质量平台只记录故障类型和非敏感的期望/实测结果。健康检查、
登录、模型配置和会话查询接口不接受故障控制。

## 故障类型与期望行为

| 类型 | 注入点 | 故障阶段的可观察结果 | 恢复阶段 |
| --- | --- | --- | --- |
| `model_timeout` | 模型意图识别调用前 | Agent 捕获 `TimeoutError`，HTTP 200，确定性业务路径继续，`fallback_reason=TimeoutError` | 同请求模板不带故障后回到正常模型路径 |
| `model_429` | 模型意图识别调用前 | Agent 捕获 `ModelRateLimitError`，HTTP 200，确定性业务路径继续，`fallback_reason=ModelRateLimitError` | 后续正常请求成功 |
| `downstream_5xx` | 指定 `user`、`asset`、`ticket` 或 `approval` 服务调用前 | 业务返回稳定 `unavailable` 状态，失败工具调用包含受控错误，HTTP 200 | 后续正常业务请求成功 |
| `tool_slow_response` | 指定下游工具调用前 | 延迟达到配置值后正常完成；报告证明慢响应被测量且未破坏业务结果 | 后续正常请求不再携带延迟 |
| `knowledge_unavailable` | 知识库查询前 | HTTP 200，`knowledge_status=unavailable`，无伪造来源 | 后续知识查询恢复为 `answered` |
| `sse_interruption` | SSE 已发出 `start` 后 | 流在 `complete` 前结束，执行器分类为 `stream_interrupted` | 后续 SSE 收到完整 `complete` |
| `database_error` | 会话写入前 | HTTP 503，失败写入不污染连接或会话数据 | 后续正常请求写入和查询成功 |

`downstream_5xx` 和 `tool_slow_response` 必须指定 `target`。慢响应的
`delay_seconds` 只允许有限正数，避免测试钩子造成无界阻塞。模型故障模拟供应商
异常，由现有运行时回退逻辑处理；它不伪装成 Agent 自身的 HTTP 429。

## 门禁配置

新增独立 YAML 门禁套件，不扩张现有单次 `LoadTestConfig`：

```yaml
id: reference-agent-m13
target_url: http://127.0.0.1:8000
fault_token_env: REFERENCE_AGENT_TEST_FAULT_TOKEN
reports:
  json: reports/m13-gate.json
  html: reports/m13-gate.html
defaults:
  requests: 4
  concurrency: 2
  timeout_seconds: 5
thresholds:
  max_error_rate: 0
  max_latency_p95_ms: 1000
  min_throughput_rps: 1
  max_cost_total: 0
scenarios:
  - id: model-timeout
    protocol: http
    message: "如何使用 VPN？"
    fault: {type: model_timeout}
    expect: {fallback_reason: TimeoutError}
    recovery: true
```

顶层和嵌套对象都执行严格字段校验。套件中的请求数、并发、超时、用户、消息和
协议使用里程碑 12 的数据模型验证。`fault_token_env` 只保存环境变量名；密钥从
运行环境读取，不允许把密钥直接写入 YAML。

支持的数值门禁为：

- `max_error_rate`、`max_429_rate`、`max_stream_interruption_rate`；
- `max_latency_p95_ms`、`max_ttft_p95_ms`；
- `min_throughput_rps`；
- `max_cost_total`、`max_cost_per_success`。

所有比例范围为 0 到 1，时间、吞吐和成本不得为负。配置了阈值但实测指标为空、
成本币种混合或成本缺失时，相关检查失败，不能以缺数据绕过门禁。比较边界包含
阈值本身：最大值使用 `actual <= limit`，最小值使用 `actual >= limit`。

## 编排和数据流

```text
Gate YAML
  -> strict GateSuiteConfig
  -> each scenario
       -> injected LoadTestRun with authenticated request-scoped fault
       -> fault expectation checks
       -> recovery LoadTestRun without fault (when recovery=true)
       -> SLA/SLO and cost checks
  -> GateSuiteResult
  -> JSON + standalone HTML
  -> process exit code
```

每个故障场景先执行故障阶段，再立即执行无故障恢复阶段。恢复阶段使用新的独立
会话并应用同一组阈值；`database_error` 额外查询恢复会话，证明连接和持久化仍
可用。故障阶段允许通过显式期望把预期错误视为“故障已观察”，但原始
`LoadTestSummary` 仍保持真实成功/失败计数，报告不会篡改压测指标。

为支持业务故障证据，`SampleResult` 只提取允许列表中的非敏感观察值：
`fallback_reason`、三个业务状态、来源数量、失败工具数量。现有字段和序列化格式
保持不变，只追加 `observations`。

## 结果模型与报告

每项 `GateCheck` 包含：检查名、阶段、比较符、期望值、实际值、单位、是否通过
和失败原因。每个场景保存故障类型、故障阶段摘要、恢复阶段摘要及检查列表；套件
保存总场景数、通过数、失败数和 `gate_passed`。

JSON 报告完整保存上述结构和经过脱敏的压测结果。自包含 HTML 展示：

- 总体门禁状态；
- 每个故障及恢复阶段的性能、错误和成本摘要；
- 每项阈值的期望值、实测值和通过/失败原因；
- Trace ID 与错误分类，不显示消息、密钥或原始故障 Header。

新增独立命令 `llmtest-gate <config>`，退出码固定为：

- `0`：所有场景、故障期望、恢复和阈值通过；
- `1`：执行、网络或报告写入错误；
- `2`：配置错误；
- `3`：门禁正常执行但存在失败检查。

## 错误处理与隔离

- 故障解析在任何业务副作用之前完成。
- 故障对象不可变并沿当前请求显式传递，不修改服务单例或运行时全局配置。
- 数据库注入发生在事务前，并映射为稳定 503；真实未知数据库异常仍由原有异常
  路径暴露，避免测试钩子吞掉产品缺陷。
- 故障阶段运行异常与“预期故障指标不满足”分开表示；前者是执行错误，后者是
  门禁失败。
- 任一场景失败不阻止其恢复探测和其余场景运行，使报告保留完整故障矩阵。

## 测试策略

按 TDD 分为以下证据层：

1. 故障控制单元测试：默认关闭、启动失败、403、400、严格字段、密钥比较和参数
   边界。
2. Reference Agent 集成测试：七种故障均通过真实 HTTP/SSE 入口观察；正常与
   故障请求并发执行并证明请求级隔离；数据库故障后连接可继续使用。
3. 门禁单元测试：所有阈值的通过、等于边界、失败、缺失指标、混合币种和成本
   单位行为。
4. 编排与 CLI 测试：严格 YAML、故障/恢复顺序、失败仍继续、脱敏报告和四类
   退出码。
5. 回归：全部非 UI pytest、V1 API gate、Playwright、`compileall`、
   `git diff --check`。
6. 类生产验收：以候选 Docker 镜像运行完整 HTTP/SSE 故障矩阵，保存 JSON/HTML；
   以发布镜像复跑；主服务保持故障控制关闭并通过 smoke 与 SQLite 完整性检查。

## CI 与交付

独立 Load Test workflow 在 Python 3.12 和 3.14 继续运行契约测试，并新增一个
网络级 M13 job：启动启用测试故障控制的 Reference Agent，等待健康后执行仓库
内的固定故障矩阵，上传 JSON/HTML artifact。现有 V1 gate 和 Playwright 继续提供
关键流程和 UI 质量门禁。

交付严格执行：Issue #46、独立分支、本地验收、Push、PR、Actions、独立代码
审查、合并 `master`、合并后验证、预发布 Release、独立候选/发布镜像部署演练、
Issue 证据和关闭。状态表只有在这些环节全部完成后才标记 M13 已完成。

## 完成标准

- 七种故障均由真实 Reference Agent HTTP/SSE 请求观察并通过恢复探测；
- 测试控制的关闭、鉴权、严格校验和并发隔离全部有自动化证据；
- SLA/SLO、成本及故障结果均能自动判定，失败时返回退出码 3；
- JSON/HTML 能定位阈值、故障和恢复失败且不泄露敏感数据；
- 定向、全量、V1、UI、CI 和 Docker 验收通过；
- PR、Actions、审查、合并、Release、部署和 Issue 跟踪全部完成。
