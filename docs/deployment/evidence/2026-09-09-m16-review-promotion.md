# Milestone 16 人工复核与回归晋级交付证据

日期：2026-09-09

## 当前检查点

Issue [#55](https://github.com/Neil558719/llm-test-framework/issues/55) 已创建；实现分支为 `codex/m16-review-promotion`。当前记录的是本地实现验收，交付链尚未完成，不能视为已发布里程碑。

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

## 仍待完成的交付动作

Push、PR、GitHub Actions、独立代码审查、合并到 `master`、预发布 Release、本机类生产部署、部署后 smoke、SQLite integrity 和 Issue 关闭尚未完成。M17 趋势、线上离线关联和发布验证保持未开始。
