# Issue #46 里程碑 13 故障注入与 SLA/SLO 门禁验收

## 范围与安全边界

- 交付分支：`codex/m13-fault-slo-gate`；候选代码提交
  `d6085310ded554cdf92af26827b363eb9a94899d`。
- Issue：[#46](https://github.com/Neil558719/llm-test-framework/issues/46)。
- 参考 Agent 只接受请求级故障对象；故障控制默认关闭，开启时必须同时提供
  `REFERENCE_AGENT_TEST_FAULTS_ENABLED=true` 和非空
  `REFERENCE_AGENT_TEST_FAULT_TOKEN`。控制令牌和原始故障 Header 不写入 YAML、
  JSON/HTML 报告或 API 响应。
- 覆盖 `model_timeout`、`model_429`、`downstream_5xx`、
  `tool_slow_response`、`knowledge_unavailable`、`sse_interruption`、
  `database_error` 七种故障。每个故障阶段后使用新会话进行无故障恢复；数据库
  场景额外查询每个恢复会话。

## 本地回归与独立审查

在 Windows 上为 pytest 分配唯一系统临时目录，并禁用历史缓存：

```powershell
$m13Temp = Join-Path $env:TEMP ('m13-final-full-' + [guid]::NewGuid().ToString('N'))
python -m pytest -q --no-report --no-history -p no:cacheprovider --basetemp $m13Temp
python -m qe_platform.v1_gate --json reports/m13-branch-v1.json --html reports/m13-branch-v1.html
python -m pytest -q -m ui --no-report --no-history -p no:cacheprovider --basetemp $m13UiTemp
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

- 默认非 UI 回归：`293 passed, 4 deselected, 171 warnings`。
- V1 API gate：`14/14`，`gate_passed=true`。
- Playwright：`4 passed, 293 deselected`。
- `compileall`、Compose 配置和差异空白检查均通过。LangGraph 上游弃用警告仍
  存在，未作为本里程碑的产品缺陷处理。
- 独立审查先后定位并修复部分成本漏记、空 YAML 列表绕过、阶段异常中断、报告
  脱敏、响应消息回显、重复恢复会话、失败样本成本完整性和恢复查询传输错误分类。
  相应的红绿回归纳入当前测试集；最终复查代理因额度耗尽未返回新的结论，因此
  在推送前仍需 PR 上的独立人工/代码审查。

## 候选 Docker 网络门禁

候选镜像使用精确代码提交 `d608531` 构建，标签
`llmtest-reference-agent-m13:candidate`，运行在 `127.0.0.1:18046` 的独立
命名卷 `llmtest-m13-candidate-data`。容器使用 Mock 模型和版本化零费率表，主
服务未停止或改写。

```powershell
$env:REFERENCE_AGENT_TEST_FAULT_TOKEN = 'local-m13-candidate-token'
python -m qe_platform.loadtest.gate_cli reports/m13-candidate-gate.yaml
```

- `/api/health` 返回 `{"status":"ok","service":"reference-agent"}`；镜像标签
  `org.opencontainers.image.revision` 为完整的 `d608531` SHA。
- 门禁报告：`7` 个场景均通过，`0` 个失败场景、`0` 个失败检查、`0` 个阶段执行
  错误；每个故障和恢复阶段各运行 3 个请求。
- 所有恢复阶段 `cost_complete=true`；`database_error` 的
  `database_recovery_session_count` 为 `3 == 3`；SSE 恢复阶段的 TTFT 正常采集。
- 容器内 `PRAGMA integrity_check` 返回 `ok`，安装后的 `llmtest-gate --help`
  正常显示。
- 未带令牌、错误令牌、畸形故障 Header 分别返回 `403`、`403`、`400`；无故障
  恢复请求返回 `200`，响应的 `raw_response` 为空对象。
- 候选 JSON/HTML 报告扫描未发现临时令牌、故障正文或测试业务消息；控制头值显示
  为 `[REDACTED]`。报告保存在被忽略的 `reports/m13-candidate-gate.json` 和
  `reports/m13-candidate-gate.html`，后续 PR/Release 使用同类脱敏资产。

## 交付状态与剩余动作

本文件记录的是分支和候选镜像的本地证据，尚不构成发布完成。仍需按仓库交付链：
push 分支、创建并审查 PR、等待 GitHub Actions、合并 `master`、以合并 SHA 重跑
门禁并发布预发布版本、用发布镜像隔离复验、备份后升级本机主服务（故障控制关闭）、
记录部署证据并关闭 Issue #46。真实供应商压测、云端独立服务器和生产鉴权边界仍
不在本机类生产验收范围内。
