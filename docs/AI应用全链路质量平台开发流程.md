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

A06交接尾注：k64已有限确认3135b468两夹具迁移及138窄回归无剩余，原17Python哈希不变；最后仅docs提交且19Python冻结，不重复root。下表唯一root失败历史保持，当前head CI与主合并树full/独立安装发行待主接续。

本表是后续对话中回答“开发进度”的唯一事实来源之一。每完成一个里程碑，必须同时更新状态、证据和剩余工作。

| 里程碑 | 状态 | 已实现证据 | 未实现/下一步 |
| --- | --- | --- | --- |
| A07 / Issue [#78](https://github.com/Neil558719/llm-test-framework/issues/78)：真实耗时、首内容与成功吞吐 | 本地定向/相关完成，准备冻结独审，未root | base a8b3ac2/dev6；真实单调耗时/缺值null、有效响应契约、simulated首内容与兼容network TTFT来源分离、goodput/成功延迟/建立流分母、门禁报告链。56新增/10顶层pytest，相关379通过/2警告，最终M13同0/1000ms协议限定与新增/报告窄集97通过/2警告；完整RED/夹具失败保留，见docs/evidence/A07/summary.md | 独审关闭后唯一finalroot；主后续dev7、当前SHA CI/合并/安装Release/部署。无真实provider/Docker/E01流式/E02队列/A08预算；用户练习待做/掌握未评估 |
| A06 主交付接续（A07依赖） | 同SHA CI/合并、合并验收/独立安装、dev6发行回下载与Issue76关闭 | 主提供PR77全部34成功，merge fe197042与base a8b3ac2同产品树；合并1110通过/7排除/2警告98.41秒，wheel74完整性（3harness+2上游警告）+14场景/3资源通过；三附件大小/hash/tag/source验证，详见A07证据 | 本行更新下方历史交付状态，不覆盖旧root失败/138迁移记录，不计A07验证。真实provider/IdP/HTTPS/持久部署未验收，无Docker变动，用户掌握未评估 |
| A06 唯一root与夹具迁移最终本地边界 | 独审三项关闭；唯一root未全绿，遗漏两正向seed仅测试迁移后138定向通过，待主CI/mergedfull | 5b17bd1 root实际993pass/1fail/116errors/7排除/2警告/0skip，92.99秒；telemetry_access/retention_clock旧legacy发布seed改独立可信v2/不同ID，保留actor/角色/CSRF/时间/TTL/默认阈值，两个完整文件138pass2warn41.21秒。生产17哈希不变；20顶层+3继承消费者=23进程，86新增；准确失败见A06证据 | 本行更新下方历史387/329；不得声称localfullpassed，不重跑本任务root。两文件diff有限确认后交主，当前head CI完整回归全绿才可merge，主唯一mergedfull/安装Release/持久环境另验 |
| A06 独审窄修接续（2026-10-28） | 2Important/1Minor实际RED后窄修，重新冻结待有限复审，仍无root | 空消息异常按status保留失败报告；持久化proof局部数组校验及已有run统一scope预检404，RuntimeError仍500；双verified-v2 app/env对照。9失败/13已有守卫通过→22定向/11文件329相关通过2警告42.06秒；86新增，18顶层pytest/18进程，限3生产文件 | 本行更新下方首冻结387/15命令历史；k64有限复审收敛后唯一root，主CI/合并/安装Release/持久部署待续，版本依赖不改，练习待完成 |
| A06 / Issue [#76](https://github.com/Neil558719/llm-test-framework/issues/76)：报告完整性与基线可比性 | 本地相关通过，准备冻结独立k64审查，尚无finalroot | base725a413/dev5；独立不可变manifest、canonical控制/评分摘要、步骤/质量/断言重算、外部信任与自报分离、内容幂等、安全来源投影、schema1→2保留旧记录/links/快照；初始化/中断错误可写但不能绿。72新增，15顶层pytest，最新21文件387通过/2上游警告；初始9真实RED/3已有守卫与接口/夹具错误分列，见docs/evidence/A06/summary.md | 独立审查收敛后唯一finalroot；主CI/合并树/wheel/安装/Release/部署接续，主统一dev6。Agent部署恢复范围不变；无真实供应商/SDK/IdP/用户DB操作，用户练习待完成、掌握未评估 |
| A05 主交付接续（A06依赖） | 主已合并、当前CI与独立安装、dev5预发行及回下载验证完成 | merge b16aa0b与base725a413测试源一致；34CI、合并树1024通过/7排除/2警告，wheel114质量+14场景/3资源通过；dev5三附件逐字节/hash/tag/source核验，Issue73关闭；wheel摘要见A06证据 | 本行取代下方A05历史交付待办；由主提供、不计A06覆盖。真实provider/IdP与持久部署未验收，用户练习待完成 |
| A05 最终本地验收接续 | 独立复审无剩余项，冻结源唯一全量通过，待主串行交付 | `be21c8d`关闭1Important/1Minor；114项，初稿57+12真实RED及审查26失败/1已有守卫通过；定向27/相关226，唯一根1024通过/7排除/2警告、0skip、69.91秒。累计11顶层pytest+3继承消费者=14进程。仅新wrapper窄修，内核/版本依赖不改；之后仅docs收口 | Push/PR/同SHA CI、合并树/独立安装/Release/部署由主接续，主统一dev5；当前仍dev4，本地/Mock不代表真实效果，用户练习待完成。本行取代下方A05初稿待审状态，原310归初稿、不重复验证 |
| A05 / Issue [#73](https://github.com/Neil558719/llm-test-framework/issues/73)：执行YAML质量声明与聚合 | 本地定向/相关通过，源码冻结待独立review | base `2356b1e` 含已复审A04b接续；五指标required、显式Judge、最终回答/问题/sources、缺grounding零相关调用、回调策略/结果校验、规范化量纲及转义差异/Trace。初始真实RED57/补边界12；新87项，相关21文件310通过/2警告；7次顶层pytest保留两次测试错误及117通过/2旧契约失败，12个Python静态编译/diff/metadata通过。见 `docs/evidence/A05/summary.md` | 独立审查后唯一finalroot，Push/PR/当前SHA CI、合并树验证、安装Release/部署由主接续；版本保持dev4、主后续统一dev5。Mock只证明离线接线，真实质量与用户掌握未评估，练习待完成；无本任务全量/真实调用证据 |
| A04b 主流程验收接续（A05依赖） | PR/CI/合并、合并树与独立安装、dev4预发行及回下载核验完成 | 主报告PR74 head2356b1e的34项checks成功，merge `55b22550e9beb35693a19f8a50135cb08f7d7f25` 同树全量910通过/7排除/2警告，wheel202鉴权隔离+14场景/3资源通过；独立复审无剩余项；[dev4](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev4) 回下载hash/tag/三附件核验，Issue72关闭，hash见A05证据 | 本行更新下方A04b历史交付状态；本任务不重复验证，真实IdP/HTTPS/持久部署未验收，用户练习待完成/掌握未评估 |
| A04b / Issue [#72](https://github.com/Neil558719/llm-test-framework/issues/72)：应用范围隔离 | 本地相关验证、独立复审完成，主整合dev4准备交付 | base `7bc45e1`；可信subject/app策略及机器allowed apps、SQL先过滤后分页/聚合、完整归属链、同app关联、server scope证明。初稿RED30/边界5/快照3失败及根890通过保留；复审Minor另RED14失败/6已有守卫通过，`3b68332`窄修相关248通过，最终86隔离tests；独立复审无剩余项，整合master0cdc713，dev4三处一致且依赖不变。见 `docs/evidence/A04b/summary.md` | 当前head Push/PR/CI、合并后全量、安装/Release、部署与Issue跟踪另行验收，不把初稿890算窄修全量；用户练习待完成。旧无/异常scope生产快照404，不回填；A06完整性不在本轮 |
| A04a / Issue #70：读取鉴权与可信actor接续 | 代码/CI/合并/预发行与回下载核验完成；真实环境待验收 | PR #71 head7bc45e1的34项检查与独立审查通过，merge0cdc713同树；合并根824通过/7排除/2警告，独立wheel116鉴权契约/14场景/三资源通过；dev3发布回下载hash/tag/三附件核验，Issue #70关闭；旧773通过/1夹具失败保留 | 本项读取/actor已发行；A04b应用隔离按上行独立跟踪；真实IdP/HTTPS/持久部署未验收，用户练习待完成 |
| A03 主流程交付接续 | PR #69全部同SHA检查与复审通过，已合并并发布dev2预发行版 | merge `6993aa6` 与已审查/CI的 `9046f80` 同树，合并后708通过/7排除/2警告，独立wheel47契约/3策略消费者/14场景/三资源通过；[dev2](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev2) | 本行取代下方A03历史待办状态；真实供应商/embedding质量/持久环境及未来manifest仍未验收，用户待复现 |
| A03 / Issue [#68](https://github.com/Neil558719/llm-test-framework/issues/68)：真实Embedding能力与必需策略 | dev2分支本地实现与离线验证通过，未发布 | base `a764f4e`；RED44失败/2通过，报告来源补RED1失败/3通过/46排除；定向53通过，相关169通过/2警告；根默认非UI全量一次708通过/7排除/2警告、0skip。删除真实Anthropic伪向量、typed unsupported负缓存、required默认/optional探索、强制必需入口、Mock来源展示；dev2三处metadata一致、锁依赖未变；见 `docs/evidence/A03/summary.md` | 独立审查、Push/PR/当前SHA CI、合并后验证、安装包/Release/部署/Issue跟踪及用户复现由主流程继续；未接未来manifest，不扩A04/A05 |
| A02/A01 主流程验收接续（A03依赖） | A02已合并并完成合并后/独立安装验证；[dev1预发布](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev1)与A01 [dev0](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev0) 已发布 | 主代理报告A02 merge `f7c28b08360e6aa981ea43d677f67cba2065d31c`与base a764同树，合并后显式Mock658通过/7排除/2警告；独立dev1包14/14场景/三静态资源、隔离有效性95通过无skip；回下载wheel SHA256=`0d3096ec94b85b29c5e05a8cbae72fe8ed56715d3911dd6f2a0f235ee5a72d96`，tag指向核对一致，Issue64已关；A01 dev0回下载hash/tag校验通过，Issue61/63/65已关 | 此行更新下方历史阶段记录；本子代理未重复这些验收，不将A03本地通过当CI/发布；真实环境与用户掌握仍未验证 |
| A01 合并与 Issue #65 安装包接续 | PR #62 已合并；发行候选安装缺陷已本地修复 | master `3bfc43a` 与已通过全部远端检查的 `4d8ff42` 同树，合并后显式Mock 563通过/7排除/2警告；独立wheel因缺web使14场景全失败，新消费者入口先RED后补package-data，三静态资源与14/14场景GREEN；见 `docs/evidence/A01/installed-wheel.md` | 本行更新下方A01历史状态；Issue #65 分支尚待独立审查、当前SHA CI、合并后安装验证、Release及环境/Issue跟踪；不得将源码或离线安装绿灯当持久部署完成 |
| Issue #63 恢复快照只读检查补充 | 属主修复远程已越过；新WAL快照检查修复本地60通过、独立复审通过 | `762da56` 的PR run `39909703097` 中备份读取/上传成功，恢复后只读卷checker报SQLite unable to open；两项旧checker负例先失败，改immutable只读URI后相关60通过/2系统项排除/2上游警告，保持完整性与marker正反断言 | 待推送并验证当前SHA真实Linux CI、合并后验证、Release与部署跟踪；快照检查不证明活动WAL实时状态 |
| A01 / Issue #63 接续（2026-10-23） | PR #62 当前远程容器失败；补充修复已本地验证、独立复审通过 | `9ad1fbd` 的 run `39448584021` 暴露 root-owned 私有备份导致 host 读取/上传失败；交还 backup/manifest 给 host，并从可信 appuser 解析UID/GID在恢复原子替换前设置属主；含旧root-owned目标和权限失败保留原DB负例，最终相关58通过、2 Windows系统集成项排除、2上游警告；见 `docs/evidence/A01/container-ownership.md` | 本行更新先前 A01 行交付状态：PR 已创建；补充修复仍需提交、Push、当前SHA CI、合并后验证、Release与部署跟踪；不得标交付完成 |
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
| 10.5. Reference Agent 模型客户端接入与运行时适配 | 交付完成（本地类生产验收；云端迁移待未来部署） | 2026-09-04：新增 `reference_agent/runtime/` 配置、provider 注册表和 `AgentRuntime`；API 提供 `/api/model-profiles`、`/api/model-profile`，UI 提供 Mock/DeepSeek profile 切换且不接收 API key；runtime 将模型意图/参数送入确定性业务图，Real 模式基于业务结果生成回答并失败回退；Compose 已传递 `REFERENCE_AGENT_MODEL_*`；本地全量回归 `140 passed, 1 skipped, 4 deselected`，Playwright `4 passed`；PR #27 已合并为 `222b058`，Compose 配置修复 PR #28 已合并为 `0a996c0`；两次 PR 的 Actions CI/V1 gate/Playwright/Container Readiness 全部通过；已发布 `v0.2.0-alpha.12`；本地类生产部署是本阶段交付条件，部署资产保留迁移到云端独立服务器的能力。2026-09-04 自动刷新改进：`deploy/start-reference-agent.ps1` 启动后台 `.env` 监听器，配置保存后自动重新创建容器并等待健康；本机实测非法端口导致刷新失败时 watcher PID 仍存活，恢复合法配置后同一 watcher 自动重建容器，API 模型更新为 `watch-test-recovered-final` 且容器为 `healthy`；重复启动保持单一 watcher，未手动传入端口时从 Compose 自动识别发布端口；PR [#35](https://github.com/Neil558719/llm-test-framework/pull/35) 已合并为 `48c7e557`，其 Python 3.12/3.14 离线回归、V1 API gate、Playwright、Container Readiness 全部通过；主分支合并后全量回归 `154 passed, 1 skipped, 4 deselected`；已发布预发布 Release [v0.2.0-alpha.15](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.15)，Issue [#34](https://github.com/Neil558719/llm-test-framework/issues/34) 已关闭。2026-09-04 登录自启动改进：新增 `deploy/register-reference-agent-task.ps1`，幂等注册仅限当前用户登录触发的 Windows 计划任务，动作确定性延迟 30 秒并配置失败后每分钟重试、最多 5 次，支持 `-Unregister`；真实注册/重复更新/导出 XML/卸载验证通过，任务参数不含密钥；PR [#38](https://github.com/Neil558719/llm-test-framework/pull/38) 已合并为 `3a3d32e`，Python 3.12/3.14 离线回归、V1 API gate、Playwright、Container Readiness 全部通过；主分支全量回归 `157 passed, 1 skipped, 4 deselected`；正式任务已从 master 路径注册并在 Issue [#37](https://github.com/Neil558719/llm-test-framework/issues/37) 记录部署证据；已发布预发布 Release [v0.2.0-alpha.16](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.16) | 暂无独立云服务器计划，后续具备服务器、正式凭据和生产鉴权方案后执行云端迁移、部署后 smoke 和公网追踪 |
| 11. Token、成本和版本数据 | 已完成（本地类生产交付） | 2026-09-04：新增 `ModelVersion`、`CostMetrics`、`PriceTable`；客户端采集 Mock/OpenAI/Anthropic usage；Reference Agent 响应包含模型、Prompt/知识库/工具版本、Token 和可配置成本；`ScenarioRunResult` 与 Run JSON/HTML 报告聚合展示；全量回归 `149 passed, 4 deselected`，未知价格显式为空，非法费率拒绝，混合币种/价格版本标记为 `MIXED`；PR #30 已合并为 `6815040`；Actions 的 Python 3.12/3.14、V1 gate、Playwright、local-production-drill 全部通过；已发布 `v0.2.0-alpha.14` | 进入里程碑 12：独立压测执行器；真实供应商公网调用和独立服务器部署仍按 Issue #25 跟踪 |
| 12. 独立压测执行器 | 已完成（本地类生产交付；云端迁移待未来部署） | 2026-09-05：新增 `qe_platform/loadtest/` 独立 `asyncio + httpx` 执行器、严格 YAML 配置、HTTP/SSE 采样、会话隔离、固定请求数/持续时间模式、超时/传输/429/无效响应/SSE 中断分类；输出吞吐、总延迟和 TTFT 的 P50/P95/P99、错误率、429 比例、流式中断率、HTTP 状态、Token、成本和 Trace，并生成脱敏 JSON/自包含 HTML；注册 `llmtest-load` CLI，提供 HTTP/SSE 示例配置和独立 Actions 工作流。PR [#42](https://github.com/Neil558719/llm-test-framework/pull/42) 已通过独立代码审查及全部 Actions（Python 3.12/3.14 离线回归、V1 gate、Load-test contract、Playwright、Container Readiness），并于合并提交 `25fffd5` 合并到 `master`；合并后里程碑定向测试 `33 passed`，完整回归 `190 passed, 1 skipped, 4 deselected`，`compileall`、`git diff --check`、CLI smoke 通过；本地健康 Docker 服务完成 20 请求/4 并发 HTTP 和 10 秒/4 并发 SSE 演练，报告成功输出并正确记录服务端 500，敏感信息扫描无命中；已发布预发布 Release [v0.2.0-alpha.17](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.17)，Issue [#40](https://github.com/Neil558719/llm-test-framework/issues/40) 已记录部署追踪并关闭 | SLA/SLO 阈值判定属于里程碑 13；Issue [#41](https://github.com/Neil558719/llm-test-framework/issues/41) 的 SQLite 并发存储缺陷已在修订交付 12.1 修复；暂无独立云服务器计划，后续具备服务器、正式凭据和生产鉴权方案后执行云端迁移 |
| 12.1. SQLite 并发存储缺陷（Issue #41） | 修复已交付（本地类生产） | 2026-09-06：`reference_agent/storage.py` 同锁保护连接写事务（提交/回滚）、读取与关闭；5 项真实 SQLite/HTTP/SSE 回归先失败再通过，独立审查与复跑通过；PR [#44](https://github.com/Neil558719/llm-test-framework/pull/44) 全部 Actions 通过并合并为 `1529bcd`；合并后默认回归 `196 passed, 4 deselected`，V1 gate `14/14`，分支 UI `4 passed`；已发布 [v0.2.0-alpha.18](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.18)，本地 8000 服务镜像 revision=1529bcd 且 healthy；同一发布镜像 Mock 验收 HTTP/SSE 各 200 请求、8 并发均零失败，400 会话逐条核对，smoke 4/4、SQLite 完整性 ok；详见 `docs/deployment/evidence/2026-09-06-sqlite-concurrency.md` 和 Issue #41 | 下一步仍为里程碑 13；本次不构成 SLA/SLO 门禁、跨重启工单/审批持久化或云端生产验收 |
| 13. 故障注入与 SLA/SLO | 已完成（本地类生产交付） | Issue [#46](https://github.com/Neil558719/llm-test-framework/issues/46)；PR [#47](https://github.com/Neil558719/llm-test-framework/pull/47) 已合并为 `29ee1c42`，分支新增请求级、鉴权且默认关闭的七类 Reference Agent 故障控制，故障与恢复顺序编排，错误率/429/SSE 中断/P95/TTFT/吞吐/成本阈值、样本级业务结果断言、脱敏 JSON/HTML 报告和固定七场景配置；两轮独立审查缺陷均已修复并有回归覆盖；PR 的 Offline tests、V1 API gate、Load-test contract、M13 gate、Playwright、local-production-drill 全部通过；合并后默认非 UI 回归 `293 passed, 4 deselected, 171 warnings`，V1 gate `14/14`，同源 Playwright `4 passed`；候选及发布镜像的七故障/恢复网络门禁均为 `7/7`，0 失败检查/执行错误，SQLite 完整性 `ok`；预发布 [v0.2.0-alpha.19](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.19) 已发布并以该镜像升级本机主服务，部署后 smoke `4/4`、容器 healthy、故障控制关闭且故障 Header 返回 `403`，详见 `docs/deployment/evidence/2026-09-06-m13-fault-slo-gate.md` | 真实供应商压测、云端独立服务器和生产鉴权边界仍待具备正式环境与凭据后执行；FastGPT 不在范围内 |
| 14. Dify 适配扩展 | 已完成（本机类生产交付） | Issue [#49](https://github.com/Neil558719/llm-test-framework/issues/49) 已关闭；PR [#50](https://github.com/Neil558719/llm-test-framework/pull/50) 合并为 `2739e8f`，其 Offline tests、V1 gate、Load-test contract、M13 gate、Dify compatibility contract、Playwright 和 local-production-drill 均通过；新增 `qe_platform.adapters.DifyChatAdapter`、严格环境配置和能力矩阵，支持 Dify Chat blocking、同用户/会话 `conversation_id` 延续、条件检索来源映射及脱敏错误分类；新增 `dify-compat-gate`、两个只断言可观测响应的 Dify YAML 场景、JSON/HTML 脱敏报告和离线 HTTP 契约测试；独立审查后的嵌套输入隔离、API Key 换行拒绝、URL 规范化、2xx 状态保留及错误/断言消息脱敏均有红绿回归；合并后默认非 UI `329 passed`、UI `4 passed`，已发布 [v0.2.0-alpha.20](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.20) 并将同 SHA 镜像升级本机服务，smoke `4/4` 与 SQLite 完整性均通过；详见 `docs/deployment/evidence/2026-09-06-m14-dify-compatibility.md`；`AppResponse`、Reference Agent、V1 gate 保持兼容，FastGPT 未纳入本次改动 | 真实 Dify Chat 只在使用者显式提供正式环境与凭据后执行；Workflow、Completion、文件、多模态、工具调用、流式 TTFT 和稳定的用量/成本/模型版本契约仍不在本里程碑范围内 |
| 15. Trace 存储与反馈 API | 已完成（本机类生产交付） | PR [#53](https://github.com/Neil558719/llm-test-framework/pull/53) 已通过全部 Actions 并合并为 `13df65e7f9eeccc3587e4ece0ca8af6266b2b3d2`；新增脱敏 Trace/反馈模型、SQLite 仓储与 30 天清理、FastAPI/CLI、可选异步 Reference Agent 上报、用户指南和离线 CI 合约；合并后默认非 UI 回归 `385 passed, 4 deselected`，UI `4 passed`，compileall、Compose config 和 diff check 通过；已发布 [v0.2.0-alpha.21](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.21)，本机 `llmbackup` 已部署同 revision 镜像并 healthy，Smoke `4/4`，SQLite 完整性 `ok`，遥测未配置时保持 no-op；部署证据见 `docs/deployment/evidence/2026-09-09-m15-trace-feedback.md`，Issue [#52](https://github.com/Neil558719/llm-test-framework/issues/52) 已关闭 | 共享环境读/反馈鉴权、真实供应商凭据、独立云服务器和线上反馈闭环仍待后续环境/里程碑；FastGPT 不在范围内 |
| 16. 人工复核与回归晋级 | 已完成（本机类生产交付） | Issue [#55](https://github.com/Neil558719/llm-test-framework/issues/55) 已关闭；新增 `qe_platform/feedback/review.py`、`promotion.py`、SQLite 复核/晋级表、复核与晋级 API、脱敏 YAML 场景校验和离线 Runner 契约；PR [#56](https://github.com/Neil558719/llm-test-framework/pull/56) 已通过全部 GitHub Actions、独立审查并合并为 `8ce8a5fa85a452e25cb95fbb2601f5836cca4439`；定向回归 `65 passed, 5 warnings`；合并后完整回归 `406 passed, 4 deselected, 177 warnings`，UI `4 passed, 406 deselected, 3 warnings`，compileall、Compose config、diff check 通过；已发布预发布 [v0.2.0-alpha.22](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.22)；本机服务已部署同 revision 且 healthy，部署后 smoke `4/4`，SQLite 完整性 `ok`；证据见 `docs/deployment/evidence/2026-09-09-m16-review-promotion.md` | 真实公网生产鉴权、独立云服务器、正式供应商凭据和跨重启业务持久化仍待后续环境；M17 趋势、线上离线关联和发布验证保持未开始；FastGPT 不在范围内 |
| 17. 趋势、线上离线关联与发布验证 | 已完成（本机类生产交付） | Issue [#58](https://github.com/Neil558719/llm-test-framework/issues/58)；PR [#59](https://github.com/Neil558719/llm-test-framework/pull/59) 已通过全部 Actions、独立审查并合并为 `0fba6aa5ef8469c84e7eaa54b4713aa078b8e943`；新增 `qe_platform/quality_loop/` 的离线运行导入、趋势聚合、Trace -> Feedback -> Review -> Promotion -> scenario -> offline run 显式关联、baseline/candidate 发布门禁、结构化 JSON/HTML 证据、`quality-loop` CLI 和 `/api/quality/*` API；分支完整回归 `444 passed, 4 deselected, 205 warnings`，合并 master 定向回归 `37 passed, 1 warning`；预发布 [v0.2.0-alpha.23](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.23) 已发布；同 revision 本机服务 healthy，部署后 smoke `4/4`，SQLite integrity `ok`；证据见 `docs/deployment/evidence/2026-09-09-m17-quality-loop.md` | 真实公网环境、正式凭据、独立云服务器和跨重启业务持久化仍待后续环境；FastGPT 不在范围内 |
| M17 后生产加固（服务器迁移准备） | 离线实现、本地回归、本机 Docker 演练与仓库质量收尾完成；交付生命周期待办 | `codex/production-hardening` 分支实现 generic OIDC/OAuth2 + PKCE、四角色授权、SQLite WAL/事务/版本迁移与跨重启业务状态、备份/恢复/就绪/指标、Docker secrets 与生产 Compose 覆盖。2026-09-13 补齐包版本元数据（`0.2.0a24.dev0`）、MIT `LICENSE`、`uv.lock` 锁定依赖与 CI 的 `uv sync --locked` 可复现安装。2026-09-11 最终定向回归 `74 passed, 49 warnings`；完整非 UI 回归 `534 passed, 5 deselected, 261 warnings`；UI `5 passed, 534 deselected, 5 warnings`；本机 Docker 已验证镜像 digest `sha256:9c8d7a2f...`、schema 版本 `2`、备份 SHA-256 `d3679ef...`、迁移/恢复/跨重启/rollback 报告；`compileall`、`git diff --check`、PowerShell、POSIX shell 和 Compose config 均通过。`llmtest/` 无改动，未增加 FastGPT 文件或实现引用。证据见 `docs/deployment/evidence/2026-09-10-production-hardening.md` 与 `docs/deployment/production-readiness-runbook.md` | 先创建生产加固 Issue，再 push、PR、Actions、独立审查、合并 `master`、合并后验证和预发布。完整 Bearer Smoke、真实 IdP、HTTPS 域名、正式凭据、独立服务器与公网验收仍待正式环境；FastGPT 仍不在范围内 |
| A01. 统一仓储/API 时钟与跨日期回归恢复 | 本地实现、独立审查与离线回归通过；PR #62 远程部分通过，容器验收另有 Issue #63 修复中 | 2026-10-20：Issue [#61](https://github.com/Neil558719/llm-test-framework/issues/61)；容器权限 Issue [#63](https://github.com/Neil558719/llm-test-framework/issues/63)；基线 `cd51114b` 在新锁定环境复现 `18 failed, 516 passed, 5 deselected`；仓储注入 UTC Clock、显式 now 优先、API 去掉墙上时间覆盖、CLI 注入 factory，保留 30 天 TTL；晋级到期校验覆盖首次与幂等重放。相关回归 `81 passed`，完整非 UI 回归 `556 passed, 5 deselected, 2 warnings`；原18项逐项 PASS；脱敏证据 `docs/evidence/A01/summary.md`，基线 `docs/remediation/baseline.md`，面试素材 `docs/interview/ledger.md` | Push、PR、Actions、独立审查、合并及合并后验证、Release、部署与 Issue 关闭均待主流程；Container Readiness 首次因 helper 挂载权限失败，已补 helper-only 用户覆盖并完成本地守卫；其他改造任务未开始 |

本轮 A02 状态补充（不改变上方历史交付记录）：

| 任务 | 当前状态 | 本地证据 | 剩余交付环节 |
| --- | --- | --- | --- |
| A02 / Issue [#64](https://github.com/Neil558719/llm-test-framework/issues/64)：评测有效性与 Judge 契约 | 分支本地实现与离线回归通过，尚未发布 | `codex/a02-validity` 起点 `4d8ff42`；首批 RED 84 failed/2 passed，补充 RED 3 failed/6 passed/86 deselected；相关 119 passed/2 warnings；默认非 UI 全量一次 658 passed/7 deselected/2 warnings，0 skipped；7 排除为 5 UI、2 Windows 系统集成。空 claims 为 inconclusive/None，必需断言阻断；严格真实 JSON；均分与显式金标准确率分离；证据 `docs/evidence/A02/summary.md` | 独立审查、Push/PR/当前 SHA CI、合并及合并后验证、Release、部署/Issue 跟踪由主流程执行；用户复现练习待完成。A01 依赖代码已验证，不标 A01 已发布；A03/A04/A05 未扩展 |

本轮 A04a 状态补充（保留上方历史记录，交付状态由主流程更新）：

| 任务 | 当前状态 | 本地证据 | 剩余交付环节 |
| --- | --- | --- | --- |
| A04a / Issue [#70](https://github.com/Neil558719/llm-test-framework/issues/70)：读取门禁与可信操作者 | 本地实现、相关验证完成；尚未发布 | `codex/a04a-auth-actor` 起点 `f7c28b0`；RED 校正后29失败/50通过，相关157通过；唯一根全量773通过/1失败/7排除/2警告，旧跨subject成功夹具迁移后定向128通过，0 skipped；没有最终全量全绿运行。四角色读取/无角色403，metrics admin；反馈/审核subject绑定，写角色和CSRF保持。见 `docs/evidence/A04a/summary.md`；版本暂保留dev1待主整合 | 独立审查、Push/PR、当前SHA CI、合并/合并后验证、Release、部署和Issue跟踪由主流程执行；用户练习待完成/掌握未评估。A04b的application授权、对象/查询/分页隔离、机器allowed application均未实施 |

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
