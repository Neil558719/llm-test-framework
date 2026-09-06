# Dify 兼容性测试指南

## 适用范围

本指南说明质量平台对 Dify 的受限兼容能力。Reference Agent 仍是平台的主要被测
系统；Dify 只作为外部 Chat 应用兼容目标。适配器调用 Dify Chat 的
`POST /chat-messages` blocking 模式，并把可观测结果转换为平台的
`ResponseEnvelope`。

本机和 CI 的自动化验收使用本地 HTTP 契约夹具，不会连接外部 Dify，也不需要真实
凭据。真实 Dify 验证由使用者显式提供环境变量后执行。

## 能力矩阵

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| `chat_blocking` | 支持 | Chat blocking 请求和回答映射为统一响应协议。 |
| `conversation_continuation` | 支持 | 同一平台用户和 session 的后续请求复用 Dify `conversation_id`。 |
| `retrieval_resources` | 条件支持 | 仅当 Dify 返回 `retriever_resources` 时映射检索文本。 |
| `authentication_errors` | 支持 | Bearer 鉴权请求及脱敏的网络、HTTP 错误分类均有离线契约测试。 |
| `tool_calls` | 不支持 | Chat API 未提供可与 Reference Agent 等价的工具调用观测协议。 |
| `usage_cost_model_version` | 不支持 | blocking 响应没有稳定且完整的 Token、成本和模型版本协议。 |
| `streaming_ttft` | 不支持 | 当前适配器只支持 blocking，不实现 SSE 或 TTFT。 |
| `workflow_completion_files_multimodal` | 不支持 | Workflow、Completion、文件和多模态 API 不在本里程碑范围内。 |

不支持能力会出现在 JSON/HTML 报告的 `limitations` 字段，不能被当作已经完成的
平台能力。

## 真实 Dify 门禁

先在 Dify Chat 应用的访问 API 页面创建应用密钥，再在 PowerShell 中仅通过环境变量
提供连接信息。API Key 不应写进 YAML、命令行、报告或版本库。

```powershell
$env:DIFY_BASE_URL = "https://your-dify.example/v1"
$env:DIFY_API_KEY = "app-你的应用密钥"
$env:DIFY_INPUTS_JSON = '{"language":"zh-CN"}'
$env:DIFY_TIMEOUT_SECONDS = "30"
python -m qe_platform.dify_gate
```

安装项目后可使用：

```powershell
dify-compat-gate
```

默认报告为 `reports/dify-compatibility.json` 和
`reports/dify-compatibility.html`。退出码 `0` 表示全部已声明场景通过；`1` 表示
执行或报告错误；`2` 表示本地配置无效；`3` 表示已执行场景存在断言失败。

真实门禁只运行两个打包场景：检索来源可观测性和两轮会话延续。它不执行质量裁判、
供应商压测、Dify 工具断言或未声明 API。

## 数据脱敏与故障处理

适配器不会把原始请求正文、Authorization 值、API Key 或完整 Dify 响应保存到
`raw_response`。兼容门禁报告会脱敏用户消息、回答、检索文本以及断言的期望和实际值；
报告只保留场景状态、完成状态、能力边界和安全的 Dify message ID 元数据。

缺少 `DIFY_BASE_URL` 或 `DIFY_API_KEY` 会安全失败。网络错误、非 2xx 响应、无效 JSON
和无效成功负载会被分类为 `ApplicationAdapterError`，错误文本不回显上游正文或请求数据。

## 离线契约验证

开发和 CI 通过标准库本地 HTTP 服务验证请求结构、会话 ID 隔离、来源映射、错误分类、
报告脱敏和 CLI 返回码：

```powershell
python -m pytest -q tests/test_dify_adapter_config.py tests/test_dify_adapter.py tests/test_dify_gate.py tests/test_m14_dify_assets.py tests/test_m14_docs.py
```
