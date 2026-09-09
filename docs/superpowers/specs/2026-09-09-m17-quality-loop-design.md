# M17 趋势、线上离线关联与发布验证设计

日期：2026-09-09

Issue：[58](https://github.com/Neil558719/llm-test-framework/issues/58)

## 背景与目标

M15 已经持久化脱敏 Trace 和反馈，M16 已经提供人工复核、归因、优先级和低质量样本晋级。M17 将这条链扩展为可查询、可复现、可审计的质量闭环：

```text
线上 Trace -> Feedback -> Review -> Promotion -> scenario_id
             -> 离线 Scenario Run -> baseline/candidate -> Release Validation
```

完成定义是：给定临时 SQLite、脱敏线上 fixture、一个晋级 YAML 场景以及两个离线 RunReport JSON，可以生成趋势、关联链和发布验证 JSON/HTML；候选通过和失败的门禁均有测试；报告能保留所有关联 ID，且不包含 Trace 明文、用户身份、密钥或遥测令牌。

## 非目标与边界

- 不在 Reference Agent 中加入测试断言、趋势计算或发布逻辑。
- 不修改 `llmtest` pytest 插件的执行语义；M17 能力放在 `qe_platform/quality_loop/`。
- 不调用真实供应商、真实公网遥测端点或云服务；CI 和验收只使用临时 SQLite、脱敏 fixture 和占位版本。
- 不增加 FastGPT 依赖、适配器、部署步骤、测试或 CI 验收目标。
- PostgreSQL 只保留既有数据访问层边界，不在本里程碑实现迁移。
- M17 只比较结构化指标，不恢复 Trace 原始请求或响应文本。

## 架构

新增 `qe_platform/quality_loop/`，分为四个边界：

1. `models.py` 定义不可变的趋势点、离线运行元数据、关联记录、门禁策略和发布验证结果。
2. `storage.py` 使用与遥测相同的 SQLite 文件，创建 `quality_offline_runs`、`quality_links`、`quality_release_validations` 表；通过只读 JOIN 读取 M15/M16 表，保留 30 天过滤和外键级联。存储层不接受原始 Trace 文本。
3. `engine.py` 将遥测、反馈、复核、晋级、离线报告聚合为趋势和显式关联，并执行 baseline/candidate 发布门禁。门禁失败返回结构化失败项，不通过异常字符串传递。
4. `cli.py` 提供 `quality-loop` 命令，用临时或显式 SQLite、离线 RunReport JSON 和输出路径完成导入、趋势、关联及发布验证；`api.py` 将查询和验证暴露给现有 FastAPI telemetry app。

`qe_platform.reporting.RunReport` 增加可选 `application`、`release_id`、`version`、`environment` 元数据，缺省值保持向后兼容。既有报告字段和 `AppResponse` 不变。

## 数据模型与关系

### OfflineRun

- `run_id`：非空 UUID 字符串。
- `application`、`release_id`、`version`、`environment`：非空且不含控制字符；仅保存标识，不保存凭据。
- `source_path`：本地报告来源的脱敏标签，不保存绝对路径。
- `started_at`、`finished_at`：UTC ISO-8601。
- `total`、`passed`、`failed`、`gate_passed`、`p95_latency_ms`、`total_tokens`、`total_cost`：从 RunReport 校验并计算。
- `scenario_ids`：运行中出现的唯一场景 ID 集合，排序后 JSON 保存。

### QualityLink

关联必须由调用者显式提供 `promotion_id`、`scenario_id` 和 `offline_run_id`。存储层验证：

- 晋级记录存在且未过期；
- 晋级的 `scenario_id` 与请求相同；
- 离线运行存在且包含相同场景 ID；
- 同一晋级与离线运行重复关联时幂等返回原记录；
- 任一 ID 不匹配都返回结构化 `invalid_link`，不得按名称或时间自动猜测。

关联记录保存 `link_id`、`trace_id`、`feedback_id`、`review_id`、`promotion_id`、`scenario_id`、`offline_run_id`、`created_at`，用于报告回溯。

### TrendPoint

趋势按 UTC 日桶、应用和版本聚合，字段包括：`bucket`、`application`、`version`、`online_trace_count`、`feedback_count`、`confirmed_low_quality_count`、`low_quality_rate`、`offline_run_count`、`offline_pass_rate`、`p95_latency_ms`、`total_tokens`、`total_cost`。没有样本的指标使用 0 或 `null`，不伪造分母。

### ReleaseValidation

输入为 `baseline_run_id`、`candidate_run_id` 和 `ReleaseGatePolicy`：

- `max_candidate_failure_rate` 默认 `0.0`；
- `max_pass_rate_drop` 默认 `0.0`；
- `max_low_quality_rate_increase` 默认 `0.0`；
- `require_complete` 默认 `true`；
- 可选 `application` 和 `release_id` 必须与候选运行一致。

结果保存 `validation_id`、基线/候选运行 ID、策略、`passed`、结构化 `checks`、关联记录摘要和创建时间。每个检查包含 `name`、`actual`、`threshold`、`passed`、`message`。候选缺少场景、运行不完整、通过率下降、失败率或线上低质量率超阈值时门禁失败。

## API 与 CLI

现有 `create_telemetry_app` 增加：

- `GET /api/quality/trends?application=&version=&from=&to=`：返回趋势点。
- `GET /api/quality/links?offline_run_id=&promotion_id=`：返回显式关联链。
- `POST /api/quality/offline-runs`：导入已生成的脱敏 RunReport JSON 元数据。
- `POST /api/quality/links`：创建或幂等返回关联。
- `POST /api/quality/release-validations`：执行并保存发布门禁，返回 JSON 结果；门禁失败使用 HTTP 422，响应仍包含完整检查。
- `GET /api/quality/release-validations/{validation_id}`：读取 JSON 证据。

写接口使用现有 telemetry ingest token；查询接口沿用当前受控访问边界，不新增伪造的生产鉴权。

`quality-loop` CLI 支持：

```text
quality-loop import-run --database DB --report REPORT.json
quality-loop link --database DB --promotion-id ID --offline-run-id ID
quality-loop trends --database DB --json OUT.json --html OUT.html
quality-loop validate-release --database DB --baseline ID --candidate ID --json OUT.json --html OUT.html
```

所有输出 JSON/HTML 只包含结构化指标和关联 ID，并对 HTML 文本进行转义；命令返回码为 0 表示门禁通过，1 表示门禁失败，2 表示输入或配置错误。

## 报告与演示

`quality_loop.reporting` 生成自包含 HTML，至少展示：线上趋势表、反馈/低质量率、离线运行对比、Trace/Feedback/Review/Promotion/Scenario/Run 关联表、门禁检查和失败原因。演示 fixture 必须按真实顺序创建 Trace、Feedback、Review、Promotion，导入 baseline/candidate 报告，创建 Link，最后执行验证；测试读取 JSON 和 HTML 断言关联 ID、阈值和通过/失败结果。

## 隐私、保留与错误处理

- 所有输入先通过现有 `assert_sanitized_payload` 或等价字段校验；发现请求文本、回答文本、API key、Cookie、Authorization、Telemetry token 或路径中的密钥时拒绝。
- 所有查询使用 Trace 的 30 天保留截止时间；过期链路不可导入、关联或查询。
- 外键删除 Trace 时级联删除反馈、复核、晋级和质量关联，但离线运行与发布验证保留其自身审计记录，并将关联状态标记为不可用而非读取已删除数据。
- API 将校验错误映射为 400/422、缺失实体映射为 404、存储故障映射为 500；响应不回显敏感输入。

## 验收证据

定向测试必须覆盖：模型校验、趋势聚合、SQLite 保留/幂等/级联、关联拒绝边界、发布门禁通过/失败、API、CLI、脱敏 HTML/JSON 和端到端闭环。完成后运行默认回归、UI 回归、compileall、Compose config、diff check，并记录 PR/Actions、独立审查、合并、Release、部署 smoke、SQLite integrity 和 Issue #58 状态到 M17 证据文档和开发流程状态表。
