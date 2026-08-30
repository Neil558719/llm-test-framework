# AI 应用全链路质量平台开发流程

## 1. 项目目标与边界

本项目从现有 `llmtest` LLM 质量评测框架演进为 AI 应用全链路质量工程与自动化测试平台。

主测试对象是自建的企业 IT 服务台 Agent，而非 Dify、FastGPT 或裸模型。Agent 应覆盖 IT 知识问答、故障工单、软件权限申请，并具备多轮对话、RAG、工具调用、确定性业务规则、Mock 下游服务和可观测调用链。

Dify 和 OpenAI 兼容应用是次级兼容性测试目标，用于证明平台可通过适配器接入不同 AI 应用。FastGPT 完全不在本项目范围内，不新增、不部署、不测试 FastGPT。次级目标也不应替代可完全控制的参考 Agent。

系统角色必须隔离：

```text
参考 Agent / 外部 AI 应用 = 被测对象
测试平台 = 场景编排、断言、执行、报告、门禁
Judge 模型 = 回答质量评测者，不是被测对象
```

## 2. 既有能力基线

截至 2026-08-30，仓库已有的 `llmtest` 能力为：

- pytest 插件、Mock/Real 双模式和应用注册机制；
- OpenAI 兼容与 Anthropic 评测客户端；
- 语义、相似度、JSON/JSON Schema、LLM-as-Judge、幻觉率断言；
- Dify 知识库机器人适配示例；
- 多轮会话示例、延迟记录、HTML 报告、历史归档与基础 CI 脚本。

基线验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

基线结果：`9 passed, 1 skipped`。跳过项为当前环境没有可用的 Embedding 模型。这一结果只证明现有评测内核运行正常，不代表后续平台能力已经实现。

## 3. 固定开发原则

1. 先建设被测 Agent 和确定性业务边界，再建设测试平台扩展；测试平台不得与 Agent 自证正确性耦合。
2. 保留 `llmtest` 作为评测内核。对 `AppResponse` 采用兼容性演进，不能破坏既有 Dify 适配器。FastGPT 遗留示例不属于新平台兼容性承诺。
3. 工具名、参数、调用顺序、权限、幂等性、HTTP 状态和数据库状态只能用确定性断言验证；Judge 仅用于自然语言质量。
4. 功能回归、UI 自动化、性能压测、线上遥测采用独立执行模型，最终写入统一结果协议。
5. 每项生产行为遵循 TDD：先新增并运行失败测试，再最小实现，再跑定向与相关回归测试。
6. 不将 README、Mock 演示、规划项视为已实现功能；只有满足该项验收标准并有验证证据时才可标记完成。
7. 任何 API Key、真实用户数据和生产业务数据均不得进入版本库、测试夹具、报告或示例。
8. 每个可独立评审的里程碑使用一个隔离的 `codex/` worktree 分支。该里程碑达到验收标准并通过相关回归后，必须执行独立 diff 检查、提交、合并到 `master`，并在合并后的 `master` 上再次验证；不完整、失败或未经验证的分支不得合并。

## 4. 目标架构

```text
reference_agent/              被测企业 IT 服务台 Agent
  FastAPI + LangGraph + SQLite + Mock 业务服务 + 简单 Web UI

llmtest/                      保留的 LLM 质量评测内核
  语义、Schema、Judge、幻觉、现有客户端与 pytest 基础设施

qe_platform/                  新增质量平台层
  contracts/                  Tool Calling 与结构化输出契约
  scenarios/                  YAML 场景 DSL、校验与测试资产
  workflow_runner/            多轮业务场景执行器
  adapters/                   Reference Agent、Dify、通用 API
  browser/                    Playwright 页面对象与 UI 验收
  loadtest/                   独立异步压测与成本统计
  telemetry/                  Trace、Token、成本、版本信息
  storage/                    SQLite 起步，预留 PostgreSQL
  feedback/                   线上反馈、人工复核、回归用例晋级
  reporting/                  统一 JSON/HTML/趋势报告与发布门禁
```

统一结果协议必须至少可表达：

```text
Run, Scenario, StepResult, ToolCall, BusinessAssertion,
QualityScore, LatencyMetrics, TokenUsage, Cost, Trace, FeedbackCase
```

建议将现有 `AppResponse(answer, sources)` 保留为兼容模型，并新增 `ResponseEnvelope`，至少包含：

```text
answer, sources, tool_calls, conversation_id, trace_id,
usage, latency, raw_response, metadata
```

## 5. 参考 Agent 的固定范围

### 5.1 技术边界

参考 Agent 使用 FastAPI 服务化，LangGraph 管理状态与分支。LangChain 仅在需要 Prompt、Retriever 或 Tool 封装时引入，不为堆叠技术栈而引入。

LLM 的职责：意图识别、参数提取、工具调用建议、自然语言生成。

确定性代码的职责：权限、状态机、审批、业务规则、参数校验、幂等性与数据库写入。

### 5.2 三个核心业务流程

1. IT 知识问答：检索企业 IT 知识库，返回回答与引用，正确拒答知识库外问题。
2. 故障工单：识别故障，查询用户与资产，创建或查询工单，返回工单编号并处理重复请求。
3. 软件权限申请：查询身份和现有权限，创建审批单或直接拒绝，支持补充信息和人工转接。

Mock 服务至少包括：`UserService`、`AssetService`、`TicketService`、`ApprovalService`、`KnowledgeBase`。

参考 API 最低集合：

```text
POST /api/chat
POST /api/chat/stream
GET  /api/sessions/{session_id}
GET  /api/tickets/{ticket_id}
GET  /api/assets/{asset_id}
POST /api/approvals
GET  /api/health
```

## 6. 三层版本和验收标准

### 版本一：核心功能与工具契约测试

范围：参考 Agent、Mock 业务服务、SQLite、统一响应协议、YAML 场景 DSL、工具契约、业务状态断言、API 端到端测试、质量评测和 HTML 报告。

必须实现：

- 三个核心业务流程均可在 Mock LLM 下离线执行；
- 工具调用名称、参数、顺序和 JSON Schema 可被采集并用确定性断言验证；
- 订单式业务状态替换为工单和审批状态，支持幂等性检查；
- 场景 DSL 支持多轮对话、测试数据准备、工具预期、业务状态预期、自然语言质量预期；
- 覆盖正常、缺字段、权限不足、重复请求、空结果、超时、5xx 和人工转接场景；
- 旧 `llmtest` 测试和 Dify 示例保持可运行；FastGPT 遗留示例不纳入新平台验收；
- 每次运行输出结构化结果与 HTML 报告。

验收：关键三流程的成功、错误和恢复路径都有自动化测试；全量测试通过；运行报告可定位失败步骤、调用链和业务状态差异。

### 版本二：质量工程增强

范围：UI/API 双通道、测试资产版本、Token/成本、TTFT/P50/P95/P99、独立异步压测、故障注入、SLA/SLO 门禁，以及 Dify 适配扩展。

必须实现：

- Playwright 页面对象覆盖登录、会话、发送消息、流式回复、业务结果、错误提示和转人工；
- API 与 UI 可复用同一业务场景数据，并能以 Trace ID 关联；
- 单次调用记录输入/输出 Token、计价版本和成本；
- 压测不运行在 pytest 插件中，输出并发、吞吐、TTFT、P50/P95/P99、错误率、429 比例、流式中断率和成本；
- 可注入模型超时/429、下游 5xx、工具慢响应、知识库不可用、SSE 中断和数据库错误；
- 测试资产具备场景/知识库/工具 Schema/Prompt/模型版本关联；
- CI 根据关键流程、质量阈值、SLA 和成本预算执行门禁。

验收：本地可重复运行 API/UI/压测；报告包含性能分布、成本与故障结果；Dify 至少支持已声明能力的兼容性测试。FastGPT 不在验收矩阵中。

### 版本三：线上质量闭环

范围：Trace 持久化、用户反馈、人工复核、样本晋级、版本关联、趋势和线上离线对比。

必须实现：

- 采集请求、响应、Trace、工具调用、模型/Prompt/知识库/工具版本与隐私脱敏后的上下文；
- 支持反馈类型：正确、不准确、答非所问、信息不完整、幻觉、工具执行错误、响应过慢；
- 支持人工复核、归因和优先级；
- 经复核的低质量样本可导出并晋级为 YAML 离线回归用例；
- 支持运行结果、反馈和版本之间的查询与趋势对比；
- 默认使用 SQLite，数据访问层预留 PostgreSQL；
- 线上样本必须脱敏、设置保留策略，并与测试数据隔离。

验收：可演示完整闭环“线上 Trace/反馈 -> 人工复核 -> 回归用例 -> 离线执行 -> 发布验证”，并能在报告中找到关联证据。

## 7. 固定开发顺序

| 序号 | 里程碑 | 所属版本 | 依赖 | 完成定义 |
| --- | --- | --- | --- | --- |
| 0 | 基线冻结与兼容性清单 | 准备 | 无 | 现有全量测试和报告基线已记录 |
| 1 | 统一领域模型与结果协议 | V1 | 0 | `ResponseEnvelope` 等模型及兼容测试完成 |
| 2 | Agent 骨架、健康检查和 SQLite | V1 | 1 | FastAPI/LangGraph/数据库最小闭环可运行 |
| 3 | Mock 用户、资产、工单、审批、知识库服务 | V1 | 2 | 服务的成功/失败/慢响应可控且有测试 |
| 4 | IT 知识问答流程 | V1 | 3 | RAG、引用、拒答和质量回归测试通过 |
| 5 | 故障工单流程 | V1 | 3 | 工具调用、工单状态、幂等性和恢复测试通过 |
| 6 | 权限申请与人工转接流程 | V1 | 3 | 审批、权限、补充信息和转人工测试通过 |
| 7 | Tool Contract 与业务断言库 | V1 | 1, 5, 6 | 工具名/参数/顺序/状态断言可复用 |
| 8 | YAML 场景 DSL 与工作流执行器 | V1 | 4-7 | 多轮业务场景可不写 Python 用例而执行 |
| 9 | V1 统一报告、API E2E 与 CI 门禁 | V1 | 8 | 关键流程的结构化结果、HTML 报告和门禁通过 |
| 10 | Playwright UI 自动化 | V2 | 9 | UI 与 API 场景一致，Trace 可关联 |
| 11 | Token、成本和版本数据 | V2 | 1, 9 | 结果可追溯模型/Prompt/知识库/工具版本及成本 |
| 12 | 独立压测执行器 | V2 | 11 | 输出 TTFT、吞吐、P50/P95/P99、错误率和成本 |
| 13 | 故障注入与 SLA/SLO 门禁 | V2 | 12 | 故障恢复行为和性能阈值可自动判定 |
| 14 | Dify 适配扩展 | V2 | 7, 11 | Dify 接入能力与限制被测试和记录 |
| 15 | Trace 存储与反馈 API | V3 | 11 | 脱敏 Trace 和反馈可持久化查询 |
| 16 | 人工复核与回归用例晋级 | V3 | 15 | 反馈可转 YAML 场景并离线执行 |
| 17 | 趋势、线上离线关联与发布验证 | V3 | 16 | 闭环演示和发布证据完整 |

不允许在前置里程碑未完成时，宣称后续里程碑已实现。

## 8. 场景 DSL 最小示例

```yaml
id: ticket-create-vpn
name: 创建 VPN 故障工单
tags: [ticket, tool_call, happy_path]
setup:
  user_id: U1001
  asset_id: PC-1001
conversation:
  - user: "我的 VPN 无法连接，设备编号是 PC-1001，请帮我创建工单"
  - user: "优先级设为高"
expect:
  tools:
    - name: query_asset
      arguments:
        asset_id: PC-1001
    - name: create_ticket
      arguments:
        category: vpn
        priority: high
  tool_order: [query_asset, create_ticket]
  business_state:
    ticket.status: created
    ticket.priority: high
  response:
    contains: ["工单", "已创建"]
quality:
  relevance:
    min_score: 0.8
  hallucination_rate:
    max_rate: 0.2
performance:
  ttft_ms: 1500
  p95_latency_ms: 8000
```

## 9. 测试策略

| 测试类型 | 验证对象 | 运行方式 |
| --- | --- | --- |
| 单元测试 | 状态机、业务规则、参数校验、存储层 | pytest，默认离线 |
| 契约测试 | 工具名、参数、Schema、调用顺序 | pytest + 统一响应协议 |
| Agent E2E | 多轮对话、业务状态、异常恢复 | pytest 或场景执行器 |
| 质量评测 | 准确性、相关性、忠实度、幻觉率 | 复用 `llmtest` 和独立 Judge |
| API 自动化 | HTTP、会话、SSE、鉴权、错误码 | HTTP 客户端 |
| UI 自动化 | 用户交互和页面状态 | Playwright，独立测试层 |
| 压测 | 并发、TTFT、分位延迟、吞吐、成本 | 独立异步执行器，不放入 pytest 插件 |
| 线上闭环 | Trace、反馈、复核、回归晋级 | API + 持久化存储 |

## 10. 进度状态表

本表是后续对话中回答“开发进度”的唯一事实来源之一。每完成一个里程碑，必须同时更新状态、证据和剩余工作。

| 里程碑 | 状态 | 已实现证据 | 未实现/下一步 |
| --- | --- | --- | --- |
| 0. 基线冻结与兼容性清单 | 已完成 | 2026-08-30：`.venv\\Scripts\\python.exe -m pytest -q` 结果为 `9 passed, 1 skipped`；现有模块和适配器已评估 | 后续变更需持续回归 |
| 1. 统一领域模型与结果协议 | 已完成 | `llmtest/specs.py` 新增 `ToolCall`、`TokenUsage`、`LatencyMetrics`、`ResponseEnvelope`；`tests/test_response_envelope.py` 定向结果 `3 passed`；2026-08-30 全量结果 `12 passed, 1 skipped` | 进入里程碑 2：创建独立 `reference_agent` 模块 |
| 2. Agent 骨架、健康检查和 SQLite | 已完成 | 新增 `reference_agent` 的 FastAPI 应用工厂、LangGraph 最小状态图、SQLite 会话存储和 `/api/health`、`/api/chat`；`tests/test_reference_agent_core.py` 定向结果 `3 passed`；2026-08-30 全量结果 `15 passed, 1 skipped` | 进入里程碑 3：实现 Mock 用户、资产、工单、审批、知识库服务 |
| 3. Mock 业务服务 | 未开始 | 无 | 实现用户、资产、工单、审批和知识库 Mock |
| 4. IT 知识问答流程 | 未开始 | 无 | 实现 RAG、引用、拒答与回归用例 |
| 5. 故障工单流程 | 未开始 | 无 | 实现工具调用、状态、幂等与故障恢复 |
| 6. 权限申请与人工转接流程 | 未开始 | 无 | 实现审批、权限和转人工 |
| 7. Tool Contract 与业务断言库 | 未开始 | 无 | 新增确定性断言 API |
| 8. YAML 场景 DSL 与工作流执行器 | 未开始 | 无 | 定义 Schema、加载器、执行器和结果写入 |
| 9. V1 报告、API E2E 与 CI | 未开始 | 无 | 完成功能版本发布门禁 |
| 10. Playwright UI 自动化 | 未开始 | 无 | 增加 Web UI 与页面对象测试 |
| 11. Token、成本和版本数据 | 未开始 | 无 | 扩展响应采集与可配置价格表 |
| 12. 独立压测执行器 | 未开始 | 无 | 实现异步并发、TTFT、分位指标 |
| 13. 故障注入与 SLA/SLO | 未开始 | 无 | 故障矩阵与门禁 |
| 14. Dify 适配扩展 | 未开始 | 既有 Dify RAG 示例适配器存在，但不含统一新协议能力 | 为统一协议增加并验证 Dify 适配器；FastGPT 明确不实现 |
| 15. Trace 存储与反馈 API | 未开始 | 无 | 建立脱敏存储与反馈接口 |
| 16. 人工复核与回归晋级 | 未开始 | 无 | 反馈转 YAML 回归用例 |
| 17. 趋势、线上离线关联与发布验证 | 未开始 | 既有 HTML 历史归档存在，但不是闭环能力 | 建立闭环趋势和关联报告 |

## 11. 固定进度汇报格式

当用户询问开发进度时，必须按照下列格式回答，不以模糊百分比代替事实：

```text
当前阶段：版本 X，里程碑 N：<名称>

已实现：
- <能力>：<文件/命令/测试结果证据>

进行中：
- <能力>：<已完成部分>；剩余 <明确工作>

未实现：
- <后续里程碑或能力>

验证状态：
- <最近执行命令与结果>

阻塞或风险：
- <没有则写“无”>
```

状态必须以本文件“进度状态表”和实际代码、测试结果为准。功能写入计划、README、Mock 或示例，不等于功能已实现。

## 12. 每阶段的完成流程

每个里程碑都按以下循环执行：

```text
阅读本文件和当前状态
-> 写一项最小失败测试
-> 执行并确认因功能缺失而失败
-> 写最小生产实现
-> 执行定向测试并确认通过
-> 执行相关回归
-> 更新文档、状态表和验证证据
-> 再开始下一项
```

在项目最终完成前，使用完整回归、参考 Agent E2E、UI 测试、压测和闭环演示分别验证。只有相应版本的验收标准均有证据，才能将版本标为完成。

## 13. 分支完成与合并流程

每个独立里程碑遵循以下分支流程：

```text
从已验证的 master 创建 codex/<里程碑名> worktree
-> 在 worktree 中按 TDD 完成该里程碑
-> 执行该里程碑验收和相关完整回归
-> 独立检查 diff、状态表与文档证据
-> 提交该分支
-> 合并到 master
-> 在合并后的 master 再次运行相关验证
-> 更新状态表为已完成并记录证据
```

分支检查、提交和合并由实施代理执行。发生冲突、验收失败、回归失败或用户指令与既定范围冲突时，停止合并并如实报告原因。
