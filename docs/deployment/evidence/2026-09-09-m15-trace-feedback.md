# Milestone 15 Trace/Feedback 发布与部署证据

日期：2026-09-09

## 交付链

- Issue [#52](https://github.com/Neil558719/llm-test-framework/issues/52)：已关闭。
- 实现 PR [#53](https://github.com/Neil558719/llm-test-framework/pull/53)：已合并到 `master`，合并提交 `13df65e7f9eeccc3587e4ece0ca8af6266b2b3d2`。
- GitHub Actions：PR #53 的 Offline tests、V1 API gate、M15 telemetry contract、Dify compatibility、Load-test contract、M13 gate、Playwright 和 Container Readiness 全部成功。
- Release [v0.2.0-alpha.21](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.21)：目标提交为 `13df65e7f9eeccc3587e4ece0ca8af6266b2b3d2`。

## 合并后验证

在合并提交的工作树中执行：

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-final-release-full
```

结果：`385 passed, 4 deselected, 177 warnings`。

```powershell
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m15-final-release-ui
```

结果：`4 passed, 385 deselected, 3 warnings`。

`python -m compileall -q llmtest qe_platform reference_agent tests`、`docker compose config --quiet` 和 `git diff --check` 均返回 0。

## 本机类生产部署

部署前将现有卷 `local-production-drill_reference-agent-data` 中的 SQLite 复制为 `C:\Temp\m15-reference-agent-before-alpha21.db`。

```powershell
docker compose -p llmbackup build --build-arg BUILD_REV=13df65e7f9eeccc3587e4ece0ca8af6266b2b3d2
docker compose -p llmbackup up -d --no-build --wait --wait-timeout 120
docker inspect llmbackup-reference-agent-1 --format '{{.Config.Image}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
docker exec llmbackup-reference-agent-1 python -c "import sqlite3; print(sqlite3.connect('/data/reference_agent.db').execute('PRAGMA integrity_check').fetchone()[0])"
pwsh -NoProfile -ExecutionPolicy Bypass -File ./deploy/smoke.ps1 -BaseUrl http://127.0.0.1:8000 -ReportPath C:/Temp/m15-postdeploy-smoke.json
```

结果：镜像 `llmtest-reference-agent:v0.2.0-alpha.21`，revision 为合并提交 `13df65e7f9eeccc3587e4ece0ca8af6266b2b3d2`；容器 `healthy`；SQLite 完整性 `ok`；Smoke `4 checks` 通过。`QE_TELEMETRY_ENDPOINT`、`QE_TELEMETRY_INGEST_TOKEN` 和 `QE_TELEMETRY_HASH_KEY` 未配置，Reference Agent 遥测保持 no-op。

## 仍然存在的边界

本证据覆盖本机类生产部署，不宣称公网生产部署。共享环境的读接口和反馈写入鉴权仍需网关或后续里程碑补齐；真实供应商凭据、独立云服务器和线上反馈闭环不属于里程碑 15。
