# 里程碑 16：人工复核与回归用例晋级设计

## 目标

将 M15 的反馈记录接入结构化人工复核，并允许人工提交经过脱敏的场景草稿，校验后生成现有 YAML 场景 DSL 可加载的回归用例。闭环只覆盖“反馈 -> 复核 -> 晋级 -> 离线执行”，趋势、线上离线对比和发布门禁留给 M17。

## 边界与约束

- Trace 仍只保存 M15 的指纹、长度、工具摘要、版本和指标；不得从 Trace 重建原始请求或答案。
- 复核字段仅允许状态、归因、优先级和复核者指纹；不接受自由文本、原始答案、Token、密钥或请求头。
- 场景草稿由人工显式提供，作为隔离的测试数据；必须通过当前 `SCENARIO_SCHEMA` 和 `load_scenario_text` 校验后才可晋级。
- 只有低质量反馈（除 `correct` 外）可晋级；同一复核只能产生一个晋级记录，重复请求返回同一产物。
- 默认 SQLite 延续 M15 的保留策略和外键级联；PostgreSQL 仍只保留接口边界。
- 不增加 FastGPT 适配器、断言或部署步骤。

## 领域模型

`qe_platform.feedback.review` 提供：

- `ReviewStatus`: `pending`、`confirmed`、`rejected`；
- `ReviewAttribution`: `model`、`prompt`、`knowledge_base`、`tool`、`infrastructure`、`user_input`、`unknown`；
- `ReviewPriority`: `low`、`medium`、`high`、`critical`；
- `FeedbackReview`: review ID、feedback ID、trace ID、复核者 HMAC 指纹、状态、归因、优先级、UTC 时间；
- `PromotionRecord`: promotion ID、review/feedback/trace 关联、scenario ID、YAML 文本、UTC 时间。

场景草稿只接受现有 DSL 的字段。API 在序列化前先做严格 schema 校验、再次加载 round-trip，并拒绝敏感字段和值；YAML 采用安全转储，禁止任意 Python 对象。

## API

- `POST /api/feedback/{feedback_id}/review`：创建或幂等更新复核；请求字段为 `reviewer_id`、`status`、`attribution`、`priority`。反馈不存在返回 404，非法枚举返回 400。
- `GET /api/reviews`：按 feedback、trace、状态和分页查询，只返回指纹与结构化字段。
- `GET /api/reviews/{review_id}`：读取复核及晋级状态，过期记录按 M15 保留策略返回 404。
- `POST /api/reviews/{review_id}/promote`：仅接受 `scenario` 对象；复核必须为 `confirmed` 且反馈类别不能为 `correct`。成功返回 promotion ID、关联 ID、YAML 和 scenario ID；重复调用返回同一 YAML。
- `GET /api/promotions/{promotion_id}`：返回晋级产物及关联证据，不返回 Trace 明文。

复核与读取接口沿用当前平台受控访问假设；写入场景草稿不使用 M15 的 Trace ingest token，也不把任何 token 写入存储或错误。

## 持久化

增加 `telemetry_reviews` 和 `telemetry_promotions` 表。复核以 `feedback_id` 唯一，反馈删除时级联删除复核与晋级产物；晋级以 `review_id` 唯一。查询先按关联 Trace 的保留窗口过滤。所有写事务使用 M15 的同锁 `BEGIN IMMEDIATE` 机制。

## 离线执行证据

晋级响应中的 YAML 可直接传给 `load_scenario_text`，并使用已有 `ScenarioRunner` 和 Reference Agent adapter 执行。测试会证明生成场景可 round-trip、执行结果保留 scenario ID，并在报告/JSON 证据中保留 promotion、feedback、trace 关联字段；不会新增线上 telemetry 趋势能力。

## 验收

1. 模型和仓储：枚举/状态边界、外键、幂等、保留期和并发事务。
2. API：复核创建/查询、低质量限制、敏感草稿拒绝、重复晋级和错误脱敏。
3. DSL：生成 YAML 安全加载、round-trip 与离线 runner 执行通过。
4. 回归：M15 定向测试、现有默认回归、编译、Compose 配置和差异检查通过。
5. 交付：Issue #55、隔离分支、PR/Actions、独立审查、合并、预发布、部署证据和状态表记录完整；M17 明确保持未开始。
