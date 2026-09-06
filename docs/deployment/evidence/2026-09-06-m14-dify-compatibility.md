# Issue #49 里程碑 14 Dify 兼容性测试分支验收

## 范围

- 交付分支：`codex/m14-dify-compatibility`；当前候选提交
  `d6c06d4`。
- Issue：[#49](https://github.com/Neil558719/llm-test-framework/issues/49)。
- 兼容性范围仅为 Dify Chat API 的 blocking 消息、同一用户和平台会话内的
  `conversation_id` 延续，以及 Dify 返回时的检索来源映射。工具调用、流式
  TTFT、用量/成本/模型版本及 Workflow、Completion、文件、多模态 API 均被明确
  声明为不支持。
- 仅从 `DIFY_BASE_URL`、`DIFY_API_KEY`、`DIFY_INPUTS_JSON` 和
  `DIFY_TIMEOUT_SECONDS` 读取外部环境配置；命令行不接收密钥。测试和 CI 使用本地
  HTTP fixture，不传输外部 Dify URL 或凭据。

## 本地验收

```powershell
python -m pytest tests/test_dify_adapter_config.py tests/test_dify_adapter.py tests/test_dify_gate.py tests/test_m14_dify_assets.py tests/test_m14_docs.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m14-acceptance-1
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m14-ui-2
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

- M14 定向契约、资产与文档测试：`36 passed, 1 warning`。
- 全部默认非 UI 测试分三组完成：`189 + 75 + 65 = 329 passed`；UI 标记集
  `4 passed`。
- 安装后的 `dify-compat-gate --help` 正常显示；未配置环境时 CLI 输出
  `DIFY_BASE_URL is required` 并返回码 `2`。
- 独立审查先以失败测试复现，再修复：嵌套输入隔离与非 JSON 输入拒绝、带查询或
  片段的地址拒绝、含换行密钥拒绝、无效 2xx 响应保留原始状态码，以及 JSON/HTML
  报告中执行错误和断言消息脱敏。定向复验为 `30 passed, 1 warning`。

## 交付状态

本文件记录分支本地验收。后续仍需完成 push、PR、GitHub Actions、审查、合并到
`master`、Release、本机类生产部署及 Issue 跟踪后，才能将里程碑标记为交付完成。
真实 Dify Chat 环境仅在使用者显式提供正式地址和凭据后运行，不是离线契约门禁的
前置条件。
