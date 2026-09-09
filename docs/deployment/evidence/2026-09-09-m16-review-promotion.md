# Milestone 16 人工复核与回归晋级交付证据

日期：2026-09-09

## 当前检查点

里程碑16交付闭环已完成。Issue [#55](https://github.com/Neil558719/llm-test-framework/issues/55) 已关闭；实现 PR [#56](https://github.com/Neil558719/llm-test-framework/pull/56) 已通过独立审查和全部 GitHub Actions，并以合并提交 `8ce8a5fa85a452e25cb95fbb2601f5836cca4439` 合并到 `master`。

## 已实现模块

- `qe_platform/feedback/review.py`：复核状态、归因、优先级和 HMAC 复核者指纹。
- `qe_platform/feedback/promotion.py`：低质量确认反馈的场景草稿安全校验、YAML round-trip 和晋级产物。
- `qe_platform/storage/telemetry.py`：复核/晋级 SQLite 表、外键级联、30 天保留过滤、幂等和状态边界。
- `qe_platform/telemetry/api.py`：复核创建/查询、状态队列、晋级和产物查询 API。
- `docs/人工复核与回归晋级指南.md` 与 M16 离线 CI contract。

## 本地验证

```powershell
python -m pytest tests/test_feedback_review_models.py tests/test_feedback_promotion.py tests/test_telemetry_review_storage.py tests/test_telemetry_review_api.py tests/test_m16_docs.py tests/test_telemetry_models.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_telemetry_cli.py tests/test_reference_agent_telemetry.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m16-final-focused
```

结果：`65 passed, 5 warnings`。

```powershell
python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m16-final-full
python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\m16-final-ui
python -m compileall -q llmtest qe_platform reference_agent tests
docker compose config --quiet
git diff --check
```

结果：默认 `406 passed, 4 deselected, 177 warnings`；UI `4 passed, 406 deselected, 3 warnings`；编译、Compose 配置和差异检查均返回 0。

## 交付链证据

- PR [#56](https://github.com/Neil558719/llm-test-framework/pull/56) 的 Offline tests、V1 API gate、M16 review and promotion contract、M15 telemetry contract、Dify compatibility contract、Load-test contract、M13 fault/SLA gate、Playwright 和 local-production-drill 全部通过；独立审查没有遗留 Critical、Important 或 Minor 问题。
- 合并后的 `master` 在提交 `8ce8a5fa85a452e25cb95fbb2601f5836cca4439` 上重新验证：默认回归 `406 passed, 4 deselected, 177 warnings`；UI 回归 `4 passed, 406 deselected, 3 warnings`；`compileall`、`docker compose config --quiet` 和 `git diff --check` 均返回 0。
- 预发布 Release [v0.2.0-alpha.22](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0-alpha.22) 已创建，目标为同一合并提交。
- 本机类生产部署已升级到 revision `8ce8a5fa85a452e25cb95fbb2601f5836cca4439`；容器状态为 `healthy`，`PRAGMA integrity_check` 为 `ok`，部署后 smoke 为 `4/4`（health、knowledge、ticket、access）。
- Issue [#55](https://github.com/Neil558719/llm-test-framework/issues/55) 已关闭并完成部署追踪。

## 范围边界与后续

真实公网生产鉴权、独立云服务器、正式供应商凭据和跨重启业务持久化仍需后续环境；M17 趋势、线上离线关联和发布验证保持未开始。FastGPT 未加入任何依赖、适配器、部署步骤、测试或 CI 验收目标。
