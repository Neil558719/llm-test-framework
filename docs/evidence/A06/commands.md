# A06 实际 pytest 命令

工作目录为 `codex/a06-report-integrity` 工作树；`$a06Python` 为根项目既有 `work/env-a/Scripts/python.exe`。每行运行器均保存展开后的绝对解释器、源码 __file__、pytest 参数、fresh basetemp、stdout/stderr 与 pytest exit。运行器位于私有 `.context/A06/run_tests.py`；不把后续 PowerShell 只读命令的退出码代替日志中的 pytest exit。

```powershell
& $a06Python -X utf8 .context/A06/run_tests.py old-entry-red -q tests/test_release_report_integrity.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py old-entry-green -q tests/test_release_report_integrity.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py v2-interface-red -q tests/test_release_report_integrity.py -k v2_interface --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py v2-interface-green -q tests/test_release_report_integrity.py -k v2_interface --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py migration-red -q tests/test_release_report_integrity.py -k migration_v2 --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py v2-migration-green -q tests/test_release_report_integrity.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py semantics-red -q tests/test_release_report_integrity.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py entry-regression -q tests/test_release_report_integrity.py tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_api.py tests/test_quality_loop_cli.py tests/test_quality_loop_contract.py tests/test_quality_loop_reporting.py tests/test_run_reporting.py tests/test_application_isolation.py tests/test_storage_migrations.py tests/test_health_readiness.py tests/test_scenario_quality.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py incomplete-visible-red -q tests/test_release_report_integrity.py -k 'native_v2_preserves or default_scoring or quality_html' --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py strict-provenance-red -q tests/test_release_report_integrity.py -k 'cannot_downgrade or mock_provenance' --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py related-green -q tests/test_release_report_integrity.py tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_api.py tests/test_quality_loop_cli.py tests/test_quality_loop_contract.py tests/test_quality_loop_reporting.py tests/test_run_reporting.py tests/test_application_isolation.py tests/test_storage_migrations.py tests/test_health_readiness.py tests/test_scenario_quality.py tests/test_production_ops.py --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py manifest-columns-native-red -q tests/test_release_report_integrity.py tests/test_v1_gate.py -k 'case_and_quality or completion_and_asset or v1_gate' --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py final-guards -q tests/test_release_report_integrity.py tests/test_v1_gate.py tests/test_application_isolation.py -k 'not programming_error' --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py experimental-metadata-red -q tests/test_release_report_integrity.py -k safe_projection_records --tb=short
& $a06Python -X utf8 .context/A06/run_tests.py pre-review-related -q tests/test_release_report_integrity.py tests/test_quality_loop_models.py tests/test_quality_loop_storage.py tests/test_quality_loop_engine.py tests/test_quality_loop_api.py tests/test_quality_loop_cli.py tests/test_quality_loop_contract.py tests/test_quality_loop_reporting.py tests/test_run_reporting.py tests/test_application_isolation.py tests/test_storage_migrations.py tests/test_health_readiness.py tests/test_scenario_quality.py tests/test_production_ops.py tests/test_v1_gate.py tests/test_workflow_runner.py tests/test_builtin_scenarios.py tests/test_scenario_loader.py tests/test_response_envelope.py tests/test_tool_contracts.py tests/test_business_assertions.py --tb=short
```