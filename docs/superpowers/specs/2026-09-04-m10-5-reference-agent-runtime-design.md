# 里程碑 10.5：Reference Agent 模型客户端接入与运行时适配

## 目标

将 `llmtest` 的 Mock、OpenAI-compatible 和 Anthropic 客户端接入 Reference Agent 的实际业务执行链路，使模型可参与意图识别、参数提取和自然语言回答生成，同时保持权限、状态机、工具执行、幂等性和数据库写入由确定性代码控制。

## 位置与依赖

10.5 位于里程碑 10（Playwright UI）之后、里程碑 11（Token、成本和版本数据）之前。它依赖现有 `ResponseEnvelope`、Reference Agent LangGraph、Mock 业务服务和 UI/API 入口；里程碑 11 将在本里程碑输出的模型元数据和 usage 基础上扩展成本持久化。

## 设计原则

- `reference_agent/runtime/` 是唯一的 Agent 模型适配边界；`graph.py` 不直接导入 OpenAI 或 Anthropic SDK。
- runtime 内部只依赖 `llmtest.LLMClient` 公共接口；真实提供商由 `llmtest` 现有工厂和配置解析负责。
- 默认 `mock`，只有显式配置 `REFERENCE_AGENT_MODEL_MODE=real` 才访问外部模型。
- Agent 模型与 Judge 模型使用不同配置命名空间，不能读取或覆盖 `LLM_*` 裁判配置。
- 模型输出必须经过 JSON 解析、Schema 校验和确定性业务校验；模型不得直接执行工具或决定权限。
- 外部模型不可用时必须返回稳定的降级状态；不伪造 token、成本或成功工具调用。
- 首期产品只内置 DeepSeek 官方供应商配置；provider 选择通过注册表/工厂接口解析，新增供应商只需增加独立 provider 配置/适配器和测试，不得修改 Agent 业务图或 API 协议。
- UI 只能切换后端已注册的配置 profile；不得允许浏览器任意注入 provider、base URL 或 API key。

## 运行时接口

新增 `AgentRuntime.respond(message, user_id, session_id, trace_id, context) -> AgentResponse`。`AgentResponse` 至少包含：`intent`、`parameters`、`answer`、`tool_calls`、`sources`、`metadata`、`usage`、`latency`、`fallback_reason`。

runtime 流程：

```text
用户消息
  -> intent prompt + LLMClient.complete
  -> 结构化意图/参数解析与校验
  -> 确定性用户、资产、权限和状态规则
  -> Mock 或真实下游工具
  -> answer prompt + RAG/工具上下文 + LLMClient.complete
  -> AgentResponse / ResponseEnvelope
```

意图枚举固定为 `knowledge`、`ticket`、`access`、`unknown`。参数模型至少覆盖 `asset_id`、`category`、`priority`、`software`、`justification`。缺字段、非法字段和越权参数必须走已有业务错误分支。

## 配置协议

```text
REFERENCE_AGENT_MODEL_MODE=mock|real
REFERENCE_AGENT_MODEL_PROVIDER=openai|anthropic|deepseek|qwen|zhipu|moonshot|ollama|local
REFERENCE_AGENT_MODEL=（填写目标模型标识）
REFERENCE_AGENT_MODEL_BASE_URL=（可选，留空使用提供商默认地址）
REFERENCE_AGENT_MODEL_API_KEY=（真实模式必填，使用环境密钥注入）
REFERENCE_AGENT_MODEL_TEMPERATURE=0
# REFERENCE_AGENT_MODEL_MAX_TOKENS=（可选）
```

Mock 模式不需要 API key；Real 模式缺少 provider、model 或 key 时在启动/首次调用返回可诊断配置错误，但不得泄露 key。provider 别名复用 `llmtest.config.PROVIDER_PRESETS` 的 base URL 规则。

### 首期供应商与扩展约束

10.5 首期只注册一个真实模型 profile：`deepseek-official`，固定使用 DeepSeek 官方 OpenAI-compatible endpoint（默认 `provider=deepseek`，默认 base URL 由 `llmtest` preset 提供），模型名由部署配置填写。Mock profile 始终保留。

配置层必须提供稳定的 provider/profile 注册接口（例如 `ModelProviderRegistry.register()` / `resolve()`），runtime 只消费解析后的通用客户端，不依赖具体供应商名称。后续增加 Anthropic、其他 OpenAI-compatible 网关或本地模型时，应通过新增注册项/适配器完成，并为该 provider 增加独立 stub、错误和配置测试；不得在 `graph.py`、UI 业务组件中增加 provider 分支。

### UI 与非 UI 切换

- UI 提供 profile 下拉选择和模式状态展示；首期选项为 `Mock` 与 `DeepSeek 官方`。
- UI 可填写/覆盖模型名和 base URL（base URL 默认显示为 DeepSeek 官方地址），但提交时只能选择后端白名单 profile；API key 不在 UI 展示、回显或持久化。
- 后端环境变量/CLI 仍是部署、CI 和无 UI 场景的权威配置入口：`REFERENCE_AGENT_MODEL_*`；UI 选择只作用于受控的服务端运行配置。
- 真实密钥通过服务端环境变量或密钥管理注入，配置读取和日志均须脱敏。

## 失败与降级

覆盖配置缺失、超时、429、5xx、空文本、非法 JSON、Schema 不匹配和模型返回未知意图。Intent 阶段失败时使用现有确定性分类作为降级；回答生成失败时返回确定性模板回答，并在 metadata 中记录 `generation_status=fallback` 和安全的 `fallback_reason`。工具和权限规则失败不能被回答模型覆盖。

## 观测与兼容性

`ResponseEnvelope.metadata` 增加 `model_mode`、`model_provider`、`model_name`、`intent`、`intent_source`、`parameter_extraction_status`、`generation_status`、`fallback_reason`。同一请求的识别、工具和生成共享 `trace_id`。客户端已有 usage/latency 有值时原样映射；没有 usage 时保持 `None`。

现有 `/api/chat`、`/api/chat/stream`、UI、V1 场景和 `AppResponse` 兼容。Mock 默认结果必须与当前 V1 断言一致；Real 模式不在默认 CI 中调用公网模型，使用 HTTP stub/假客户端验证协议。

## 验收标准

1. Mock runtime 执行知识、工单、权限三类流程，现有 V1 场景全部通过。
2. Fake `LLMClient` 测试验证 intent、参数提取、回答生成 prompt、调用顺序和 trace 传递。
3. OpenAI-compatible 与 Anthropic 客户端通过 HTTP stub 验证配置映射、响应解析、usage/latency 和错误转换。
4. 非法 JSON、超时、429、未知意图和缺字段均有稳定降级测试，且不得产生错误工具调用或越权状态。
5. API 和 UI 使用同一 runtime；UI 可显示模型模式、生成状态和 trace，但不显示 API key。
6. 默认离线回归不需要网络或密钥；真实模型手工命令和安全配置文档完整。
7. 首期 UI/API 仅暴露 `Mock` 与 `DeepSeek 官方` 两个 profile；注册表扩展测试证明新增 provider 不需修改 runtime、graph 或既有响应协议。
8. UI profile 切换、环境变量/CLI 覆盖优先级、服务端 API key 脱敏和非法 provider 拒绝均有测试证据。

## 明确不包含

本里程碑不实现成本价格表、Token 持久化、独立压测、线上 Trace 存储、生产认证或自动模型路由；这些分别属于里程碑 11、12、15 和后续部署工作。
