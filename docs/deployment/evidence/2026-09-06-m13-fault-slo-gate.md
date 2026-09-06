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
- 两轮独立审查先后定位并修复部分成本漏记、空 YAML 列表绕过、阶段异常中断、
  报告脱敏、响应消息回显、重复恢复会话、失败样本成本完整性和恢复查询传输错误
  分类；相应的红绿回归纳入当前测试集。最终重复复查因代理额度耗尽未产生额外
  报告，以下 GitHub Actions 作为合并前的自动化验证证据。

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

## GitHub 合并与 CI

- PR [#47](https://github.com/Neil558719/llm-test-framework/pull/47) 已合并到
  `master`，合并提交为
  `29ee1c42f5e963d0bb92cb38f0255ce34bd4dfdf`。
- 分支 push 和 PR 的 GitHub Actions 均通过：Offline tests（Python 3.12、3.14）、
  V1 API gate（Python 3.12、3.14）、Load-test contract（Python 3.12、3.14）、
  **M13 fault and SLA/SLO gate**、Playwright 与 local-production-drill。
- 合并后的 `master` 复验默认非 UI 回归为 `293 passed, 4 deselected, 171 warnings`；
  V1 API gate 为 `14/14`，并生成 `reports/m13-master-v1.json/html`。代码未在合并后
  改动，分支同一源代码的 Playwright 验收为 `4 passed`。

## 发布镜像与本机主服务交付

- 已发布预发布版本 [v0.2.0-alpha.19](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.19)，
  标签指向合并提交 `29ee1c42f5e963d0bb92cb38f0255ce34bd4dfdf`，并附带脱敏的
  M13 门禁和 V1 报告资产。
- 使用该精确提交构建 `llmtest-reference-agent:v0.2.0-alpha.19`，在独立容器、独立
  命名卷和 `127.0.0.1:18046` 复验：七个故障/恢复场景 `7/7` 通过，`0` 个失败检查、
  `0` 个执行错误，所有恢复样本 `cost_complete=true`，报告与 SQLite
  `PRAGMA integrity_check` 均通过。
- 部署前已为本机主服务 SQLite 数据库创建备份，备份完整性为 `ok`。主服务已升级到
  该发布镜像，运行镜像 revision 与上述合并 SHA 一致且容器 `healthy`；部署后
  `deploy/smoke.ps1` 的 4 项检查全部通过，SQLite 完整性为 `ok`。主服务故障控制保持
  关闭，对携带任意故障控制 Header 的请求返回 `403`。

## 验收结论与范围

里程碑 13 已达到本机类生产交付条件：分支、PR、CI、合并、预发布、发布镜像隔离
复验和主服务部署均有证据。Issue #46 的关闭随本次交付记录合并后的最终主分支核验
执行。真实供应商压测、云端独立服务器和生产鉴权边界仍不在本机类生产验收范围内。
