# A08 实际命令与原始记录

以下为已执行的23批命令的参数清单，结果见[summary](summary.md)。前20批为首冻结历史，后3批为R1/R2审查修复。各次测试针对当时源码/测试集合，不能用最终树重跑来冒充旧RED。原日志首行保留完整解释器、pytest argv及独立basetemp，随后记录实际llmtest来源、exit/stdout/stderr。运行器拒绝覆盖同名日志/临时目录；复现时使用新的batch名称。

工作目录为 `.worktrees/a08-async-budget`。调用形式为 `& $python -X utf8 .context/A08/run_tests.py <batch> <args>`。运行器清真实配置、设mock/development/UTF8、核对本树导入，并展开为 `python -B -X utf8 -m pytest --llm-mode=mock --no-report --basetemp=<本树>/.context/A08/<batch>-temp <args>`；没有增加root或子pytest。

解释器：E为既有 `C:/Users/ZhuanZ1/Desktop/项目修改/work/env-a/Scripts/python.exe`（只读）；P为本树 `.context/A08/test-env/Scripts/python.exe`（3.13私有插件overlay）；N为本树 `.context/A08/py39-env/Scripts/python.exe`（3.9私有frozen dev环境）。

下表S为 `tests/test_async_scenario_budget.py`，R为下方四文件清单，B为18文件清单，F为6文件清单。它们是参数文本缩写，不是实际shell变量；原日志是完整展开命令的权威记录。

| 次序 / batch | 解释器 | 实际参数（所有批次末尾均有 `--tb=short`） |
| --- | --- | --- |
| 1 legacy-entry-red | E | `-q .context/A08/test_legacy_budget_red.py` |
| 2 missing-interface-red | E | `-q S` |
| 3 focused-first | P | `-q S` |
| 4 cleanup-proof-red | P | `-q S -k 'oversized_budget or cleanup_timeout_drains or execution_evidence_rejects'` |
| 5 focused-second | P | `-q S` |
| 6 late-cancellation-red | P | `-q S -k 'returning_after or cleanup_timeout_drains'` |
| 7 focused-third | P | `-q S` |
| 8 py39-import-red | N | `-q tests/test_async_scenario_budget.py::test_v1_async_reference_factory_report_and_policy_identity` |
| 9 py39-related | N | `-q R` |
| 10 py39-related-second | N | `-q R` |
| 11 py39-related-third | N | `-q R` |
| 12 related-py313 | P | `-q B` |
| 13 py39-related-fourth | N | `-q R` |
| 14 py39-dispatch-factory-red | N | `-q tests/test_async_scenario_budget.py::test_inline_factory_expiring_budget_cannot_dispatch_after_return tests/test_async_scenario_budget.py::test_native_reference_factory_owns_and_closes_local_resources` |
| 15 py39-related-fifth | N | `-q R` |
| 16 py39-cleanup-fixture-green | N | `-q tests/test_async_scenario_budget.py::test_cleanup_timeout_drains_cooperative_close_finalizer` |
| 17 final-related-py313 | P | `-q F` |
| 18 close-self-cancel-red | P | `-q tests/test_async_scenario_budget.py::test_self_cancelled_close_is_cleanup_failure_not_external_case_cancellation` |
| 19 close-self-cancel-green-py313 | P | `-q S -k 'self_cancelled_close or hanging_close or cleanup_timeout_drains or cancel_event_and_external or second_external or borrowed_adapter'` |
| 20 close-self-cancel-green-py39 | N | 与19同参数 |
| 21 review-r1-r2-red | P | `-q S -k 'test_review_ or backoff_consumes or queue_wait_is_inside or initialization_and_limiter or incomplete_execution_roundtrips or required_async_evaluation_timeout'` |
| 22 review-r1-r2-related-green | P | `-q R` |
| 23 review-r1-r2-py39-green | N | 与21同参数 |

R（4个根文件，也是后续installed消费者入口）：

```text
tests/test_async_scenario_budget.py
tests/test_workflow_runner.py
tests/test_dify_adapter.py
tests/test_release_report_integrity.py
```

B（18个相关文件，528通过归属当时树）：

```text
tests/test_async_scenario_budget.py
tests/test_workflow_runner.py
tests/test_dify_adapter.py
tests/test_dify_adapter_config.py
tests/test_reference_agent_adapter.py
tests/test_v1_gate.py
tests/test_scenario_quality.py
tests/test_run_reporting.py
tests/test_release_report_integrity.py
tests/test_quality_loop_models.py
tests/test_quality_loop_storage.py
tests/test_quality_loop_engine.py
tests/test_quality_loop_api.py
tests/test_quality_loop_contract.py
tests/test_application_isolation.py
tests/test_observability_semantics.py
tests/test_telemetry_models.py
tests/test_telemetry_storage.py
```

F（6个相关文件，273通过发生在最后close局部修复前）：

```text
tests/test_async_scenario_budget.py
tests/test_reference_agent_adapter.py
tests/test_v1_gate.py
tests/test_release_report_integrity.py
tests/test_application_isolation.py
tests/test_telemetry_models.py
```

静态命令：`& .context/A08/test-env/Scripts/python.exe -X utf8 .context/A08/freeze_checks.py` 进行内存compile、3.9语法、版本/锁差异、diff、原日志统计和consumer闭包SHA256清单；`uv lock --check --offline` 使用本树私有缓存，解析110条通过。两者不运行pytest；3.9语法检查不等于全运行时验收。私有环境建立/依赖安装日志也保留于.context/A08，PowerShell部分为UTF16，不混入23个UTF8 pytest日志计数。