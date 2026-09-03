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
| 3. Mock 业务服务 | 已完成 | `reference_agent/services/` 新增共享故障控制、`UserService`、`AssetService`、`TicketService`、`ApprovalService`、`KnowledgeBase`；2026-08-31 定向结果 `12 passed`，全量结果 `28 passed, 5 warnings`；覆盖成功、空结果、可配置 4xx/5xx、慢响应和工单/审批幂等 | 进入里程碑 4：实现 IT 知识问答流程 |
| 4. IT 知识问答流程 | 已完成 | `reference_agent/graph.py` 接入 `KnowledgeBase`，`reference_agent/app.py` 返回 sources 和 `metadata.knowledge_status`；`tests/test_reference_agent_knowledge.py` 定向结果 `4 passed`，含命中引用、知识库外拒答和 504 恢复；2026-08-31 相关回归 `7 passed`，全量结果 `32 passed, 13 warnings` | 进入里程碑 5：实现故障工单流程 |
| 5. 故障工单流程 | 已完成 | `reference_agent/graph.py` 增加工单意图识别、用户/资产校验、归属校验、工单创建和 ToolCall 记录；`reference_agent/app.py` 注入服务并返回 `tool_calls`、`metadata.ticket_status`；`tests/test_reference_agent_ticket.py` 覆盖正常、用户/资产失败、归属不匹配、幂等和 5xx；2026-09-01 相关回归 `12 passed`，全量结果 `37 passed, 23 warnings` | 进入里程碑 6：实现权限申请与人工转接流程 |
| 6. 权限申请与人工转接流程 | 已完成 | `reference_agent/graph.py` 增加权限申请意图、用户校验、软件/理由提取、受限软件转人工、审批创建和幂等；`reference_agent/app.py` 支持同会话补充信息并返回 `approval_status`、`handoff_reason`；`tests/test_reference_agent_access.py` 覆盖正常申请、缺字段、受限软件、用户失败、审批 5xx、幂等和多轮补充；2026-09-01 定向结果 `9 passed`，全量结果 `46 passed, 41 warnings` | 进入里程碑 7：实现 Tool Contract 与业务断言库 |
| 7. Tool Contract 与业务断言库 | 已完成 | 新增 `qe_platform/contracts/`，提供 `ToolContract`、可序列化 `AssertionResult`、工具名/参数 JSON Schema/字段值/调用顺序/状态断言和业务状态点路径断言；`tests/test_tool_contracts.py`、`tests/test_business_assertions.py`、`tests/test_contract_integration.py` 覆盖错误定位、严格与子序列顺序、工单及审批真实调用链；2026-09-02 Task 3 定向结果 `11 passed, 5 warnings`，审查修复后里程碑定向结果 `27 passed, 5 warnings`，相关回归 `31 passed, 41 warnings`，全量结果 `72 passed, 1 skipped, 45 warnings`；构建 wheel 已确认包含 `qe_platform`；已修复非法点路径和非 `ToolCall` 输入边界 | 进入里程碑 8：实现 YAML 场景 DSL 与工作流执行器；Embedding 跳过项、LangGraph 上游警告及生产部署仍需持续跟踪 |
| 8. YAML 场景 DSL 与工作流执行器 | 交付完成（本机类生产演练） | PR [#14](https://github.com/Neil558719/llm-test-framework/pull/14) 已合并为 `52fc37c`；PR [#18](https://github.com/Neil558719/llm-test-framework/pull/18) 已合并为 `4de5c42`，PR [#19](https://github.com/Neil558719/llm-test-framework/pull/19) 已合并为 `f3b84cd`；相关 GitHub Actions 检查通过，独立差异审查完成；新增 `qe_platform/scenarios/` 严格 YAML Schema、类型模型与安全加载器，`qe_platform/adapters/` 参考 Agent API 适配器，`qe_platform/workflow_runner/` 多轮执行器及可序列化结果；3 个包内 YAML 文件覆盖知识、工单、权限共 14 条离线路径；合并后 `master` 全量结果 `123 passed, 1 skipped, 85 warnings`；`compileall`、`git diff --check` 和 `docker compose config --quiet` 通过；本机 Docker Compose 演练完成镜像构建、服务 Healthy、强 Smoke 4 项、SQLite 备份与 `PRAGMA integrity_check`、恢复标记验证和回滚后 Smoke 4 项，详见 `docs/deployment/` 与 Issue [#17](https://github.com/Neil558719/llm-test-framework/issues/17)；工单和审批服务仍为进程内 Mock，不具备跨重启业务持久化；不同应用版本间的真实镜像回滚兼容性尚未验证；已发布预发布 Release [v0.1.0-alpha.8](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.1.0-alpha.8)，Issue #17 已记录部署追踪 | 真实公网生产、生产部署后 smoke、线上 telemetry/问题追踪仍待独立服务器、正式凭据和后续版本；Embedding 跳过项和 LangGraph 上游警告持续跟踪 |
| 9. V1 报告、API E2E 与 CI | 已完成 | PR [#22](https://github.com/Neil558719/llm-test-framework/pull/22) 已合并为 `1f35349`；GitHub Actions 的 Python 3.12/3.14 回归、V1 API gate 和 Container Readiness 全部通过；`qe_platform/reporting/` 提供 Run 级 JSON/HTML 报告，`qe_platform/v1_gate.py` 执行全部 14 条参考 Agent 场景并按完整性/断言结果返回门禁码；合并后 `master` 全量回归 `127 passed, 1 skipped, 113 warnings`，V1 gate `14/14`，`compileall`、`git diff --check` 和 `docker compose config --quiet` 通过；报告包含场景状态、失败断言、工具调用和业务状态差异，并由 CI 上传 artifact | 已发布稳定 V1 `v0.1.0` 后进入版本二里程碑 10；Embedding 跳过项和 LangGraph 上游警告持续跟踪 |
| 10. Playwright UI 自动化 | 已完成（代码与修订预发布已交付，部署待验证） | PR [#24](https://github.com/Neil558719/llm-test-framework/pull/24) 已合并为 `7c70c3a`，补强 PR [#26](https://github.com/Neil558719/llm-test-framework/pull/26) 已合并为 `f628c84`；GitHub Actions 的两套 Playwright、Python 3.12/3.14 离线回归、V1 gate 和本地生产演练均通过；合并后 `master` 默认回归 `132 passed, 1 skipped, 4 deselected`，UI 验收 `4 passed, 133 deselected`；场景 helper 按 YAML 场景 ID 复用期望值，页面暴露可机器断言的 `trace_id`；已发布修订预发布 Release [v0.2.0-alpha.11](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.11) | Issue [#25](https://github.com/Neil558719/llm-test-framework/issues/25) 跟踪独立服务器部署、部署后 smoke 和生产鉴权边界；演示登录不是生产鉴权，工单/审批跨重启持久化与线上 telemetry 仍未实现 |
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

## 14. 统一交付生命周期与验收提醒

所有需求和缺陷都必须沿以下顺序交付，后续开发不得省略其中环节：

```text
需求/缺陷
  ↓
Issue
  ↓
分支开发
  ↓
本地测试
  ↓
Push 到 GitHub
  ↓
Pull Request
  ↓
GitHub Actions 自动检查
  ↓
代码审查
  ↓
合并主分支
  ↓
发布 Release
  ↓
部署与问题追踪
```

其中，本地测试是必要证据但不是完成定义。只有适用的 GitHub Push、PR、
Actions 检查、代码审查、合并主分支、Release 发布以及部署和问题追踪均
完成，才能把里程碑或版本标记为完成并声明具备发布条件。当前环境无法执行
其中任何一步时，必须明确标注“待办/阻塞”，不得将其默认为已完成。

### 14.1 每阶段验收提醒

每个里程碑达到本文件规定的功能验收标准后，实施代理必须主动提醒用户，
再进入下一里程碑。提醒至少包含：

- 当前验收环节，以及已完成的测试、报告和其他证据；
- Push、PR、GitHub Actions、代码审查、合并、Release、部署与问题追踪的
  已完成项和待执行项；
- 当前是否满足发布条件；若不满足，列出明确阻塞原因和责任动作。

推荐使用以下固定模板：

```text
验收提醒：版本 X，里程碑 N：<名称>
当前环节：<本地验收 / PR / Actions / 代码审查 / 发布 / 部署追踪>
已有证据：<命令、结果、报告或链接>
待执行交付环节：<逐项列出 Push、PR、Actions、审查、合并、Release、部署追踪>
发布条件：<已满足 / 未满足>
阻塞与责任动作：<没有则写“无”>
```

后续对话中询问开发进度时，除遵守“固定进度汇报格式”外，还必须说明当前
交付生命周期所在环节和距离发布条件的差距。本节规则与 `AGENTS.md` 同步，
适用于本项目目录下的新对话。
