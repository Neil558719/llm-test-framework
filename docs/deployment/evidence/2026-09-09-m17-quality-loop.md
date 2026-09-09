# Milestone 17 趋势、线上离线关联与发布验证交付证据

日期：2026-09-09

Issue [#58](https://github.com/Neil558719/llm-test-framework/issues/58)

## 当前检查点

M17 功能已在隔离分支 `codex/m17-quality-loop` 完成，正在进入 PR、Actions、审查、合并、预发布和本机部署交付链。当前文档只记录已验证的本地证据，尚未宣称 Release 或部署完成。

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

结果：`28 passed, 1 warning`。

```powershell
python -m pytest tests/test_m17_docs.py tests/test_m16_docs.py tests/test_quality_loop_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-docs
```

结果：`8 passed, 1 warning`。

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-branch-full
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m17-branch-ui
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

结果：默认回归 `437 passed, 4 deselected, 177 warnings`；UI `4 passed, 437 deselected, 3 warnings`；compileall、Compose 配置和 diff 检查均返回 0。`python -m qe_platform.quality_loop.cli --help` 列出 `import-run`、`link`、`trends` 和 `validate-release` 四个子命令。

## 尚未完成的交付动作

当前仍待：Push、PR、GitHub Actions、独立审查、合并到 `master`、预发布 Release、本机类生产部署、部署后 smoke、SQLite integrity 和 Issue #58 关闭。完成前不得将状态表改为已完成。真实公网鉴权、正式供应商凭据、云服务器和跨重启业务持久化仍是后续环境边界；FastGPT 不在范围内。
