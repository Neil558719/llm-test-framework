# A01 脱敏验证摘要

日期：2026-10-20；源基线 `cd51114bdd38275c28e5dd527895bcdc65cf904b`；分支 `codex/a01-clock`；Issue [#61](https://github.com/Neil558719/llm-test-framework/issues/61)。

## 命令与结果

所有 Python 命令均使用 `uv sync --locked --extra ci` 创建的仓库专用新环境（详见 [基线](../../remediation/baseline.md)）。

| 阶段 | 命令 | 退出码 | 结果 |
| --- | --- | --- | --- |
| 基线 RED | `python -m pytest -q` | 1 | 18 failed, 516 passed, 5 deselected, 2 warnings，42.09s |
| 新接口 RED | `python -m pytest -q tests/test_retention_clock.py`（最初 13 项，未改生产代码） | 1 | 13 failed；旧构造函数不支持 clock |
| 晋级负例 RED | `python -m pytest -q tests/test_retention_clock.py -k expired_review_cannot_create_or_replay_promotion`（暂撤过期保护） | 1 | 2 failed, 20 deselected；首次及幂等重放均可绕过 TTL |
| API 负例 RED | `python -m pytest -q tests/test_retention_clock.py -k api_uses_repository_clocks`（暂恢复 API 墙上时钟覆盖） | 1 | 1 failed, 21 deselected；固定时间 Trace 错误返回 404 |
| 相关 GREEN | 下列相关模块命令 | 0 | 81 passed, 2 warnings，18.26s |
| 最终完整 GREEN | `python -m pytest -q --junitxml=<private-log-dir>/final.xml` | 0 | 556 passed, 5 deselected, 2 warnings，87.11s |
| 差异检查 | `git diff --check` | 0 | 无空白错误 |

```text
python -m pytest -q tests/test_retention_clock.py tests/test_telemetry_review_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_api.py tests/test_quality_loop_cli.py tests/test_quality_loop_contract.py tests/test_quality_loop_storage.py tests/test_telemetry_storage.py tests/test_telemetry_api.py tests/test_final_hardening_fixes.py
```

完整 GREEN 在两个反证变更均已恢复修复后运行，仅执行一次最终全量；最终增加 22 项验收，原 534 项全部通过。首轮新测试曾因列表查询缺少必填 filter 有 6 项测试夹具错误，已补 trace_id 后重新验证，未放宽生产查询校验。

## 原 18 项逐项结果

下表从原失败日志与最终 JUnit 的真实 testcase 对照生成。

| 用例 | 修复前 | 修复后 |
| --- | --- | --- |
| `tests/test_final_hardening_fixes.py::test_quality_gate_denial_is_counted_as_an_outcome` | FAIL | PASS |
| `tests/test_quality_loop_api.py::test_quality_api_completes_online_offline_link_and_validation` | FAIL | PASS |
| `tests/test_quality_loop_cli.py::test_quality_loop_cli_runs_import_link_trends_and_validation` | FAIL | PASS |
| `tests/test_quality_loop_contract.py::test_complete_trace_feedback_review_promotion_offline_release_contract` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_build_trends_aggregates_online_and_offline_metrics` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_build_quality_links_returns_only_explicit_relationships` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_validate_release_passes_when_policy_allows_linked_quality_delta` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_validate_release_fails_failure_rate_and_missing_scenario` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_validate_release_rejects_unknown_runs` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_validate_release_enforces_optional_application_and_release_identity` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_trend_p95_does_not_merge_offline_summary_with_online_samples` | FAIL | PASS |
| `tests/test_quality_loop_engine.py::test_quality_summary_returns_validation_and_safe_associations` | FAIL | PASS |
| `tests/test_quality_loop_storage.py::test_offline_run_import_is_idempotent_and_filters_sensitive_payload` | FAIL | PASS |
| `tests/test_quality_loop_storage.py::test_link_requires_matching_unexpired_promotion_and_scenario` | FAIL | PASS |
| `tests/test_quality_loop_storage.py::test_link_hides_expired_online_chain_but_keeps_offline_run` | FAIL | PASS |
| `tests/test_telemetry_review_storage.py::test_review_upsert_hydrates_and_updates_one_record_per_feedback` | FAIL | PASS |
| `tests/test_telemetry_review_storage.py::test_promotion_is_idempotent_and_cascades_with_expired_trace` | FAIL | PASS |
| `tests/test_telemetry_review_storage.py::test_storage_rejects_promotion_that_bypasses_review_or_scenario_validation` | FAIL | PASS |

## 验收覆盖与边界

- 同一固定基准夹具，在共享 wall-clock provider 模拟三个宿主日期时结论一致；未修改系统时钟。
- Trace、反馈、复核、晋级读取、清理覆盖 30 天内、等于 cutoff、超出 cutoff；跨月与闰日均按 30 个 24 小时处理。
- 过期复核写入、首次晋级和幂等重放均拒绝；正常晋级及正常幂等行为继续通过。
- 离线导入 cutoff 与持久化查询/关联/聚合按仓储时钟运行；显式 now 覆盖复核、晋级、导入、关联和验证时间戳。
- 注入非 UTC/naive clock 返回值拒绝。没有改 TTL、删除用例或增加任意时钟环境变量。
- 数据库迁移版本未变，已有 URI 仓储、默认时钟和原公共调用在全量回归中验证。

本地验证通过不代表发布完成。Push、PR、GitHub Actions、独立审查、合并及合并后验证、Release、部署与 Issue 关闭均待主流程执行。Docker 未运行，未执行容器/UI/部署验收，未干预用户服务。
