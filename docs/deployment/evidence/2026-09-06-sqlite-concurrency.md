# Issue #41 SQLite 并发存储修复验收

## 修复与审查

- Issue：[#41](https://github.com/Neil558719/llm-test-framework/issues/41)。
- 修复 PR：[#44](https://github.com/Neil558719/llm-test-framework/pull/44)，
  修复提交 `4dd9a5f`，合并提交 `1529bcda5bdfb591b6312adb1d021692f4e31d8b`。
- `reference_agent/storage.py` 为每个共享连接增加线程锁，覆盖写事务的
  提交/回滚、读取和关闭；保留单连接内存库及原有 API。
- `tests/test_reference_agent_storage_concurrency.py` 的 5 项回归先全部失败：
  内存库 InterfaceError、文件库会话丢失、失败事务污染、HTTP/SSE 500。
  修复后 5 项通过，独立审查另行复跑也为 5 passed，无阻断项。
- PR 的 Python 3.12/3.14 离线回归、V1 gate、压测契约、Playwright、
  Container Readiness 全部通过；审查与候选容器验收记录见 PR 评论。

## 本地与合并后验证

使用项目 `.venv/Scripts/python.exe`。Windows pytest 默认临时目录存在清理
权限问题，因此每次传入新的唯一临时目录，并禁用旧缓存目录。

```powershell
$caseTemp = Join-Path $env:TEMP ('sqlite-check-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q --no-report --no-history -p no:cacheprovider --basetemp "$caseTemp"
.\.venv\Scripts\python.exe -m qe_platform.v1_gate --json reports/issue41-master-v1.json --html reports/issue41-master-v1.html
.\.venv\Scripts\python.exe -m compileall -q reference_agent qe_platform llmtest
git diff --check
```

- 分支与合并后 master 默认回归均为 `196 passed, 4 deselected`。
- 分支单独运行 `pytest -m ui`：`4 passed, 196 deselected`。
- V1 gate 分支与合并后均为 `14/14`；编译与 diff check 通过。
- 上游 LangGraph 弃用警告仍存在，未作为此次缺陷修复内容。

## Docker 候选验收

独立 Compose 项目 `issue41-validation`、端口 `127.0.0.1:18041`、数据卷
`issue41-validation-data`，Mock 模型模式。使用独立 `LoadTestRunner`，
HTTP/SSE 各 200 请求、8 并发、无预热；不在 pytest 中发压。

| 协议 | 成功 | 错误 | SSE 中断率 | P95 总延迟 |
| --- | --- | --- | --- | --- |
| HTTP | 200/200 | 0 | 0 | 240.170 ms |
| SSE | 200/200 | 0 | 0 | 359.942 ms |

400 个会话 ID 均唯一，逐个 GET 会话接口核对成功；数据库会话数 400，
`PRAGMA integrity_check` 为 `ok`，`deploy/smoke.ps1` 的 4 项业务检查通过。
数值只描述本机这一轮采样，不代表 SLA/SLO 承诺。

## Release 与部署追踪

修订预发布版本
[v0.2.0-alpha.18](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.18)
指向合并提交 `1529bcd`，附候选 HTTP/SSE 的脱敏 JSON 和 HTML 报告。
升级前已使用 SQLite online backup 保存现有本地服务数据库，备份完整性为 `ok`；
备份仅保存在被忽略的本地 reports 目录，不上传数据库。

本地 `llmbackup-reference-agent-1`（127.0.0.1:8000）已通过
`docker compose up -d --no-build --wait --wait-timeout 120` 升级并 healthy；
镜像标签 `org.opencontainers.image.revision` 与合并提交完整 SHA 一致。
主服务 health 返回 ok，数据库完整性 ok，保留现有模型配置。

同一发布镜像 `llmtest-reference-agent:v0.2.0-alpha.18` 在独立 Mock 容器复验：
HTTP 200/200、SSE 200/200，8 并发，错误和中断均为 0，400 会话逐条查询通过。
HTTP P95=114.992 ms，SSE P95=112.823 ms；业务 smoke 4/4，数据库完整性 ok。
发布镜像的四份 JSON/HTML 报告以 `issue41-release-*` 文件名附在 Release。
本地服务与 Mock 验收容器均验证镜像 revision=1529bcd；未对真实供应商发起压测。

Issue #41 记录完整交付证据后关闭；本项满足本地类生产修复交付条件。

## 范围边界

本项仅修复被测 Agent 的 SQLite 共享连接并发缺陷，不更改压测错误分类或隐藏
500。工单/审批仍为进程内 Mock；跨重启业务持久化、生产鉴权和云端部署仍按
原计划追踪。里程碑 13 故障注入与 SLA/SLO 门禁、14 Dify 扩展、V3 闭环均未开始。
