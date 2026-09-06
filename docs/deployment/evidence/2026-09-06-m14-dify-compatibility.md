# Issue #49 里程碑 14 Dify 兼容性测试交付验收

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

## GitHub 交付

- 分支已推送，PR [#50](https://github.com/Neil558719/llm-test-framework/pull/50)
  经独立审查后合并到 `master`，合并提交为
  `2739e8fc2c5db7e2f16a117c03fb581eef9421b9`。
- PR 的 Offline tests（Python 3.12、3.14）、V1 API gate（Python 3.12、3.14）、
  Load-test contract（Python 3.12、3.14）、M13 fault and SLA/SLO gate、Dify
  compatibility contract、Playwright 和 local-production-drill 全部成功。
- 合并后 `master` 复验默认非 UI `329 passed`、UI `4 passed`、V1 API gate、
  `compileall`、`docker compose config --quiet` 与 `git diff --check` 均通过。
- Issue [#49](https://github.com/Neil558719/llm-test-framework/issues/49) 已随 PR
  合并关闭；预发布 [v0.2.0-alpha.20](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.20)
  指向该合并提交。

## 本机类生产部署

- 升级前以 SQLite online backup 写入 `/data/m14-predeploy-backup.db`，备份完整性
  为 `ok`。
- 使用提交 `2739e8fc2c5db7e2f16a117c03fb581eef9421b9` 构建
  `llmtest-reference-agent:v0.2.0-alpha.20`；容器标签
  `org.opencontainers.image.revision` 与该完整 SHA 一致。
- 本机 `llmbackup-reference-agent-1` 在 `127.0.0.1:8000` 完成重建并为 `healthy`；
  `deploy/smoke.ps1` 的 health、知识问答、工单和权限申请 `4/4` 通过，运行数据库
  `PRAGMA integrity_check` 为 `ok`。
- 故障控制保持 `REFERENCE_AGENT_TEST_FAULTS_ENABLED=false` 且没有配置令牌；部署
  产物 `reports/m14-postdeploy-smoke.json` 是本地忽略文件，不含 Dify 凭据。

## 结论与范围边界

里程碑 14 已达到本机类生产交付条件。真实 Dify Chat 环境仅在使用者显式提供正式
地址和凭据后运行，不是离线契约门禁的前置条件；其运行结果不应写入版本库。Dify
Workflow、Completion、文件、多模态、工具调用、流式 TTFT 和稳定的用量/成本/模型
版本契约仍不在本里程碑范围内；FastGPT 不在本项目范围内。
