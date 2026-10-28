# A07：真实耗时、首内容与成功吞吐

Issue [#78](https://github.com/Neil558719/llm-test-framework/issues/78)，分支 `codex/a07-observability`，base `a8b3ac223575a05c9c6c08977848b119d6021288`。版本保持dev6，主整合时统一dev7；pyproject/lock/内核版本不变。实现说明见[耗时与吞吐口径指南](../../耗时与吞吐口径指南.md)。

## 实现与兼容

Reference响应与trace在emit前写同一个单调耗时；场景对话窗口单独测量且排除Judge，无测量为null。新base A06 importer已经跳过null latency，本轮不重复认领该修复；在线storage保留缺值null，trend兼容并保持线上样本/离线p95不混算及旧零值不追认规则。

HTTP/SSE共用最小有效响应契约；200空对象失败，错误保留状态。goodput仅按有效协议完成的SampleResult.success，用与完成尝试吞吐相同wall time；业务期望仍独立决定门禁。新增成功延迟、首内容分布、已建立流分母/来源。Reference流显式simulated，首内容不伪造model TTFT；未知外部流保留旧network首内容别名并清楚标来源，complete与空chunk不能创建该时间。建立前失败不算中断，建立后异常保留已知status/content。无流分母为null，配置门禁仍拒绝缺测。

新增字段全部追加，旧位置参数不移动；A06 manifest/trust/baseline、required质量、应用scope/actor、TTL不改。新增min_goodput与max_content_first_event_p95门禁，配置白名单由现有GateThresholds生成。M13模拟流首内容阈值仍1000ms；中断阈值仍0，仅从全局移到SSE场景，HTTP null分母不代表成功。错误消息使用受控类型名，不把原异常文本送进负载报告。

## 环境与准确尝试

Windows/Python3.13既有 `work/env-a/Scripts/python.exe -B -X utf8`，未pip/改共享env。gitignored `.context/A07/run_tests.py` 每批清LLM_/OPENAI_/ANTHROPIC_/DIFY_/QE_/REFERENCE_AGENT_/OIDC_/AUTH_真实配置，强制mock/development/UTF8、独立全新basetemp，断言llmtest导入来自本树。所有模型均Mock或本地替身，HTTPX ASGI、TestClient、临时SQLite；无真实provider/SDK/IdP/网络/Docker。无子代理。本轮 **10次顶层pytest**；不含A03消费者子pytest，未执行root或push。

原始完整命令、stdout/stderr、源码路径及exit均在 `.context/A07/<batch>.log`，不覆盖失败。

| batch | 实际结果 | 归因 |
| --- | --- | --- |
| red | exit1；24 failed、1 passed、2 warnings | 旧入口：默认零、空响应误成功、complete假TTFT、异常状态丢失等；goodput/场景字段/来源字段缺失属于接口扩展RED，不称旧业务绕过 |
| boundary-red | exit1；9 failed、24 deselected、2 warnings | 7新增门禁接口缺失；null在线trend实际报错；分母用例由4改5样本后实际旧0.6对目标0.5。原4样本旧错计碰巧同为0.5，首次仅在缺计数字段失败，不作分母证明 |
| focused-green | exit0；33 passed、2 warnings | 首轮最小实现定向 |
| reporting-red | exit1；3 failed、2 passed、33 deselected、2 warnings | null率格式化崩溃、门禁报告新指标缺失、场景HTML缺延迟；两项trace→trend/null集成守卫已有通过 |
| related-first | exit1；356 passed、7 failed、2 warnings | 6旧正向夹具缺合法响应字段/SSE headers/显式建立状态；另1报告删掉合法TTFT P50展示的兼容问题。补夹具且保留原断言，恢复展示，不改阈值 |
| numeric-boundary-red | exit1；2 failed、7 passed、38 deselected、2 warnings | 巨大cost整数OverflowError为实际边界失败；NaN在httpx json构造阶段提前失败是夹具问题，改原始响应content后验证，不当功能RED |
| related-green | exit0；379 passed、2 warnings，39.50秒 | 23文件相关；此时54新增，所有Python生产逻辑为最终逻辑。此后仅加2资产测试及M13配置限定，不重复379 |
| packaged-gate-red | exit1；2 failed、54 deselected、2 warnings | 包内M13全局流门禁对HTTP null分母失败；本地正向夹具还缺显式价表造成成本缺测，保留历史 |
| packaged-gate-red-corrected | exit1；2 failed、54 deselected、2 warnings | 补显式Mock零价表、成本阈值不动，实际只剩HTTP错误套用流门禁 |
| packaged-gate-green | exit0；97 passed、2 warnings，2.91秒 | 全56新增+配置/门禁/两类报告窄集；真实本地7故障/恢复场景全部通过。固定0/1000ms，只限定流阈值适用协议 |

56新增并非逐项先红：表内明确区分实际旧失败、新接口缺失、已有通过守卫、后加直接验证及夹具错误。原红日志全部保留。两警告是Starlette/AnyIO弃用及LangGraph上游；无skip，均不代表真实模型效果。

准确命令如下，均在本树；运行器展开后的绝对解释器/源码路径/basetemp也在各日志首行：

```powershell
$a07Python = 'C:/Users/ZhuanZ1/Desktop/项目修改/work/env-a/Scripts/python.exe'
& $a07Python -B -X utf8 .context/A07/run_tests.py red -q tests/test_observability_semantics.py --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py boundary-red -q tests/test_observability_semantics.py -k 'stream_rate_denominator or goodput_threshold or new_thresholds or missing_content_metric or null_online' --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py focused-green -q tests/test_observability_semantics.py --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py reporting-red -q tests/test_observability_semantics.py -k 'load_report or gate_report or measured_scenario_report or server_latency_correlates or null_online_latency_is' --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py related-first -q tests/test_observability_semantics.py tests/test_loadtest_runner.py tests/test_loadtest_metrics.py tests/test_loadtest_gates.py tests/test_loadtest_gate_config.py tests/test_loadtest_reporting.py tests/test_loadtest_gate_reporting.py tests/test_loadtest_gate_runner.py tests/test_loadtest_cli.py tests/test_loadtest_gate_cli.py tests/test_loadtest_config.py tests/test_reference_agent_telemetry.py tests/test_reference_agent_fault_matrix.py tests/test_workflow_runner.py tests/test_run_reporting.py tests/test_quality_loop_models.py tests/test_quality_loop_engine.py tests/test_quality_loop_storage.py tests/test_quality_loop_api.py tests/test_quality_loop_contract.py tests/test_release_report_integrity.py tests/test_application_isolation.py tests/test_auth_api.py --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py numeric-boundary-red -q tests/test_observability_semantics.py -k 'malformed_optional or first_content_clock or simulated_mode_learned or new_gate_config or warmup_does or judge_time' --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py related-green -q tests/test_observability_semantics.py tests/test_loadtest_runner.py tests/test_loadtest_metrics.py tests/test_loadtest_gates.py tests/test_loadtest_gate_config.py tests/test_loadtest_reporting.py tests/test_loadtest_gate_reporting.py tests/test_loadtest_gate_runner.py tests/test_loadtest_cli.py tests/test_loadtest_gate_cli.py tests/test_loadtest_config.py tests/test_reference_agent_telemetry.py tests/test_reference_agent_fault_matrix.py tests/test_workflow_runner.py tests/test_run_reporting.py tests/test_quality_loop_models.py tests/test_quality_loop_engine.py tests/test_quality_loop_storage.py tests/test_quality_loop_api.py tests/test_quality_loop_contract.py tests/test_release_report_integrity.py tests/test_application_isolation.py tests/test_auth_api.py --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py packaged-gate-red -q tests/test_observability_semantics.py -k 'packaged_gate or packaged_m13' --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py packaged-gate-red-corrected -q tests/test_observability_semantics.py -k 'packaged_gate or packaged_m13' --tb=short
& $a07Python -B -X utf8 .context/A07/run_tests.py packaged-gate-green -q tests/test_observability_semantics.py tests/test_loadtest_gate_config.py tests/test_loadtest_gates.py tests/test_loadtest_reporting.py tests/test_loadtest_gate_reporting.py --tb=short
```

## 依赖与待验收

### 独审R1限定收口（尚待有限复审）

首冻结 `096a8a81ea041c87e6879a135774fb63e8fbdbfa`，tree `527c090043ca76fb7ba4fabe3e46bc5d17558ad4`；k64核对16Python哈希、版本无diff及379/97日志，0pytest、1次纯内存合成，发现1 Important、0 Critical/Minor：混合有值流与合法complete-only时仅计算非null P95，两个显式内容/TTFT阈值错误通过；全测量/全缺测对照分别通过/拒绝。主裁定显式门禁要求已建立SSE适用流测量完整，观察分布不变、不补零。

追加11项到67新增，累计 **12次顶层pytest**，仍无root。`review-r1-red` 实际8 failed/3 passed/56 deselected/2上游warnings、2.60秒：两项mixed complete-only、simulated借用unknown TTFT、旧summary无覆盖证据共4项真实误放行；3项缺新增计数接口、1项报告缺字段分别列出；全缺/零分母与未配置守卫3项已有通过。仅summary追加两个默认null覆盖计数、metrics按已建立流计数、gates对显式两项阈值核对正分母与完整覆盖；报告已有as_dict接线不改。旧正向手工summary补显式4/4证据，旧边界/阈值断言不动；配置正例显式SSE已建立，legacy负例显式去掉覆盖证据。

`review-r1-related` 实际50 passed/2上游warnings、2.23秒：全部11新边界、3旧相关守卫、统计/门禁/门禁运行器/两报告完整文件。未重复379/97、未root、无provider/网络。准确命令与完整输出保留 `.context/A07/review-r1-red.log`、`review-r1-related.log`；命令前缀和清环境规则同上，RED的选择为 `-q tests/test_observability_semantics.py -k 'partial_stream_measurement or simulated_stream_cannot or complete_stream_coverage or empty_content_coverage or partial_content_coverage or legacy_summary_cannot or stream_coverage_counts' --tb=short`。相关命令选择这7个测试函数（参数化11项）及 `test_new_gate_config_loads_and_enforces_same_boundaries`、`test_missing_content_metric_fails_configured_gate`、`test_zero_stream_denominator_blocks_configured_interruption_gate`，再加 `tests/test_loadtest_gates.py tests/test_loadtest_metrics.py tests/test_loadtest_gate_runner.py tests/test_loadtest_reporting.py tests/test_loadtest_gate_reporting.py --tb=short`，展开后的完整argv见原日志第一行。初冻结源哈希文件保留，新静态与全量改变Python哈希另记 `review-r1-static-checks.log`、`review-r1-source-freeze.json`。R1尚未关闭，不将旧379/97称当前修订后的全套结果。

主流程提供A06依赖验收：PR77同head34检查成功，merge `fe197042abd06ff86d625ad74ba8c67a749c26a6` 与本base同产品树；合并根1110 passed/7 deselected/2上游警告、98.41秒。独立wheel74完整性测试/5警告（3harness预导入rewrite+2上游）、14场景/3资源通过，7夹具逐字节一致且产品仅installed导入。dev6三附件已发布并回下载逐字节/大小/hash/tag/source一致，wheel SHA256=`e468fc52b55e3765ff6b5eb9bb99b9e651a49b71d7889b04b4ae07dd17b8934f`，Issue76关闭。首次offline安装缺缓存后只在隔离env按locked下载crypto/pydanticcore/pygments，旧env未改。A06历史root失败及138迁移通过仍保留，不用其成功覆盖本任务。

当前为A07本地定向/相关完成、准备冻结交独立审查；静态编译、diff及源SHA256记录在 `.context/A07/static-checks.log` / `source-freeze.json`。首次静态脚本将CRLF签出字节直接与LF blob相比失败；确认core.autocrlf=true且三文件无diff后，改用 `git cat-file --filters HEAD:path` 比较签出字节，保留 `static-checks-first.log`，未改产品/版本文件。独立审查关闭后才执行唯一finalroot。本任务当前无root、当前SHA CI、PR/合并、独立安装/Release/部署证据，尚不满足交付完成条件。真实Judge/provider/IdP/HTTPS/持久部署未验收；不扩E01真实streaming、E02队列、A08预算。用户练习待完成，掌握未评估。

10–20分钟练习：比较全500与一半成功时相同wall分母的attempt/goodput；用start/空chunk/complete解释为什么没有首内容；比较模拟流与未知外部流兼容TTFT来源；在HTTP配置流门禁观察null拒绝，给SSE同阈值后验证恢复。将固定单调差值沿响应/trace/trend和场景/manifest/import关联，说明哪些不包含Judge时间。不编造性能收益数字。