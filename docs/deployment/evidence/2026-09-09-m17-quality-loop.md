# Milestone 17 趋势、线上离线关联与发布验证交付证据

日期：2026-09-09

Issue [#58](https://github.com/Neil558719/llm-test-framework/issues/58)

## 当前检查点

M17 已完成完整交付链：PR、Actions、独立审查、合并、预发布、本机类生产部署、部署后 smoke 和 SQLite integrity 均有证据。合并 revision 为 `0fba6aa5ef8469c84e7eaa54b4713aa078b8e943`。

## 已实现能力

- `qe_platform/quality_loop/models.py`：脱敏离线运行、趋势点、显式关联、发布策略、检查和验证结果模型。
- `qe_platform/quality_loop/storage.py`：共享 SQLite 的离线运行、线上/离线关联和发布验证表；30 天过滤、幂等、外键和安全聚合读取。
- `qe_platform/quality_loop/engine.py`：按 UTC 日桶聚合线上/离线指标，计算 P95/通过率/低质量率，执行 baseline/candidate 发布门禁。
- `qe_platform/quality_loop/reporting.py`、`cli.py`：确定性 JSON/HTML 证据和 `quality-loop` 的导入、关联、趋势、发布验证命令。
- `qe_platform/telemetry/api.py`：`/api/quality/trends`、`links`、`offline-runs`、`release-validations` 查询和写入接口。
- 文档和 CI contract：`docs/趋势、线上离线关联与发布验证指南.md`、M17 temporary SQLite contract。

## 本地验证

```powershell
python -m pytest tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_reporting.py tests/test_quality_loop_cli.py tests/test_quality_loop_api.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-focused
```

结果：实现修复后的 M17 定向回归 `37 passed, 1 warning`；包含模型、存储、趋势、HTML/JSON、CLI、API、契约和文档。

```powershell
python -m pytest tests/test_m17_docs.py tests/test_m16_docs.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-docs
```

结果：文档与契约回归 `8 passed, 1 warning`。

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-branch-full
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-branch-ui
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

结果：M17 分支完整回归 `444 passed, 4 deselected, 205 warnings`；UI 回归在 PR Actions 通过；compileall、Compose 配置和 diff 检查均返回 0。合并后 master 定向回归 `37 passed, 1 warning`；`python -m qe_platform.quality_loop.cli --help` 列出 `import-run`、`link`、`trends` 和 `validate-release` 四个子命令。

## 远程交付与独立审查

- Issue [#58](https://github.com/Neil558719/llm-test-framework/issues/58) 创建并用于 M17 交付追踪。
- PR [#59](https://github.com/Neil558719/llm-test-framework/pull/59) 已通过两组 GitHub Actions：Python 3.12/3.14 离线回归、V1 API gate、Load-test contract、M13/M15/M16/M17 contract、Dify compatibility、Playwright 和 local-production-drill。
- 独立代码复审已批准最终基线 `063991c`；过期导入、敏感标签、富 RunReport、P95 混算和 HTML 结构化报告均有修复与回归。
- PR #59 已合并到 `master`，merge commit 为 `0fba6aa5ef8469c84e7eaa54b4713aa078b8e943`。

## Release 与部署

- 预发布 [v0.2.0-alpha.23](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.23) 已指向合并 revision `0fba6aa5ef8469c84e7eaa54b4713aa078b8e943`。
- 使用 `docker compose -p llmbackup build --build-arg BUILD_REV=0fba6aa5ef8469c84e7eaa54b4713aa078b8e943` 构建并重启本机类生产服务；容器 label `org.opencontainers.image.revision` 与该 revision 一致，容器状态为 `healthy`。
- 容器内 SQLite `PRAGMA integrity_check` 结果为 `ok`。
- `deploy/smoke.ps1 -BaseUrl http://127.0.0.1:8000 -ReportPath C:/Temp/m17-postdeploy-smoke.json` 结果为 `Smoke passed: 4 checks`。

Issue #58 在本次证据提交后关闭；真实公网鉴权、正式供应商凭据、云服务器和跨重启业务持久化仍是后续环境边界；FastGPT 不在范围内。
