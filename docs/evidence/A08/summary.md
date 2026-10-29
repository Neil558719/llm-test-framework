# A08：原生异步场景预算

Issue [#80](https://github.com/Neil558719/llm-test-framework/issues/80)，独占树 `codex/a08-async-budget`，base `4d5a2bc789b688273acf7e6c9688c4705114dc6d`。版本保持dev7。首冻结 `4cee7f3` 的2 Important已在 `602a371e84c5aa2820f7ab186d78cf594fab5188` 经k64有限复审关闭，剩余0 Critical/0 Important/0 Minor。第一次root漏系统集成排除，实际1267通过/1失败；主明确要求补齐既定范围后，`final-root-scoped` 实际 **1266 passed / 7 deselected / 2 warnings / 根0skip，110.78秒，exit0**。两次尝试分列保留，不能称只跑过一次root。此后仅docs收尾，20 Python哈希不变；主接续dev8/当前SHA CI/合并树/安装发行。实现边界见[异步场景预算指南](../../异步场景预算指南.md)。

## 实现与兼容

新增原生async协议、Dify HTTPX和Reference ASGI适配器、ExecutionBudget及有界AsyncScenarioRunner；实际v1工厂/CLI/JSON/HTML已接通。一个排队前单调deadline涵盖queue/rate/init/request/backoff/required eval；默认一次，重试需显式幂等和可重试，保留effect_unknown。owned/borrowed客户端/adapter分别清理，有限cleanup宽限、外部取消继续传播；不使用to_thread或3.11-only timeout API。

同步入口语义不变，追加字段/旧JSON省略可选execution。显式async evaluator复用A05的required/grounding/provenance/结果校验，拒绝同步回调而不是省略required。全对话后的评测/清理失败保留真实步骤；A06原始证明、持久安全投影/reader认识执行状态并拒绝release。policy在执行前冻结入scoring_assets，预算变化不能沿用旧baseline。A07对话耗时继续排除init/初始队列/Judge，stage不冒充SUT延迟。

3.9实际入口RED后，仅修必要链路：三模块8个slots条件化（>=3.10原形状保留，3.9 frozen字段保留）；application_scope/auth.access延迟注解；LangGraph AgentState.fault一处Optional；新增Python<3.10的eval-type-backport。UTC测试助手仅将Z等价规范为+00:00，原TTL/断言不改。原106锁定包版本和非project条目保持，锁新增四条必要package记录：pytest-asyncio1.2.0/1.4.1、backports-asyncio-runner1.2.0、eval-type-backport0.4.0，共110；ci/dev声明pytest-asyncio，版本仍dev7。

## 环境与实际尝试

Windows。初两批用既有 `work/env-a/Scripts/python.exe` 只读；它缺pytest-asyncio。随后3.13.15用本树 `.context/A08/test-env` 私有overlay，仅插件装在私有环境，其余依赖通过私有pth只读引用env-a，**不称完整依赖隔离**。首次venv未继承env-a导致pytest元数据导入失败，记录 `private-import-first.log` 后修正私有pth，未改共享环境。3.9.25解释器和完整frozen dev环境均在 `.context/A08/python` / `py39-env`，必要下载/构建仅私有缓存；3.9使用pytest8.4.2/asyncio1.2.0，3.13使用pytest9.1.1/asyncio1.4.1。

运行器每次清LLM_/OPENAI_/ANTHROPIC_/DIFY_/QE_/REFERENCE_AGENT_/OIDC_/AUTH_配置、强制mock/development/UTF8、断言产品从本树导入、独立新basetemp且不覆盖日志。无真实Judge/provider/SDK/IdP调用、用户容器操作、共享pip写入或新代理。pytest日志UTF8，PowerShell依赖日志UTF16；首次统计误按UTF8读取所有log失败，后来按 `command=` 字节前缀仅识别pytest，不影响任何测试结果。

**当前89新增；25条顶层pytest、两次root各继承A03消费者子pytest3次，共31进程。** 首冻结为64新增/20批，下面20行保留原阶段结果；审查修复另3批及两次root见后段。原始命令/source/exit/stdout/stderr为 `.context/A08/<batch>.log`，可复现命令见[清单](commands.md)。不是每一项都逐条先红；接口缺失、旧能力局限、实际实现缺陷、已有守卫与夹具问题分别列出。消费者optional预期skip不计根覆盖或根skip。

| batch | 实际结果 | 归因 |
| --- | --- | --- |
| legacy-entry-red | exit1；1 failed/2 warnings，1.29s | 受控urlopen阻塞loop，取消heartbeat不执行。旧同步API未承诺取消，此为新能力负实验，不称旧业务漏洞；原probe保留.context |
| missing-interface-red | exit1；3 failed/2 warnings，1.41s | budget/async runner/Dify入口不存在，仅接口RED |
| focused-first | exit1；34 passed/6 failed/2 warnings，2.67s | 5项同一个execution_complete函数被旧局部bool遮蔽；1项报告导入夹具缺application等元数据。修别名/补元数据，不改门禁 |
| cleanup-proof-red | exit1；6 failed/40 deselected/2 warnings，1.68s | 3巨整数Overflow、close取消finalizer未排空、2执行元数据未知字段可进安全投影，均实际边界失败 |
| focused-second | exit1；45 passed/1 failed/2 warnings，3.08s | Windows finalizer fixture .03s余量不足；改.15s，保留timeout/closed/无遗留任务断言 |
| late-cancellation-red | exit1；2 failed/1 passed/45 deselected/2 warnings，2.01s | request吞取消后可重写deadline为completed、factory晚返回可继续dispatch；cleanup守卫已有通过。加异步边界checkpoint |
| focused-third | exit0；59 passed/2 warnings，2.78s | 当时全部定向；之后补两项生命周期/计时守卫，再补两个实际factory/inline边界与1清理自取消，共64 |
| py39-import-red | exit1；1 failed，1.39s | 真实3.9首先命中旧VersionFingerprint slots，早于预计manifest；不是假定静态RED |
| py39-related | exit2；3 collection errors，1.78s | application_scope旧运行期PEP604注解；仅future修复，不改SQL/授权 |
| py39-related-second | exit2；3 collection errors/1 warning，2.85s | Pydantic不能求值旧ChatRequest str\|None；必要条件backport依赖 |
| py39-related-third | exit2；1 collection error/1 warning，2.76s | 旧UTC测试助手直接fromisoformat(Z)；等价规范化夹具，不是产品计时缺陷 |
| related-py313 | exit0；528 passed/2 warnings，54.24s | 18文件相关/当时61新增。不是后续新改动的重复验证 |
| py39-related-fourth | exit1；151 passed/4 failed/1 warning，13.41s | 1预算夹具init实际47ms、request尚未开始，原>0断言的时间窗过窄；1实际Reference工厂TypeError；2strict HTTP旧auth.access注解。保留失败；预算fixture等比例扩大余量 |
| py39-dispatch-factory-red | exit1；2 failed/1 warning，2.52s | 新探针证明inline factory耗尽预算后仍dispatch（实际实现缺陷），直接factory定位LangGraph get_type_hints的AgentState.fault旧PEP604（必要兼容），两者分开修 |
| py39-related-fifth | exit1；156 passed/1 failed/1 warning，13.04s | 上述边界均过，仅finalizer .15s仍不足Windows3.9 timer调度余量；只将fixture改.5，生产清理预算不动 |
| py39-cleanup-fixture-green | exit0；1 passed/1 warning，2.17s | 仅上一批唯一失败；其余156未重跑，不能拼成新整批157pass |
| final-related-py313 | exit0；273 passed/2 warnings，54.85s | 后续checkpoint/graph/auth注解及当前63新增的6文件窄相关；不重复528 |
| close-self-cancel-red | exit1；1 failed/2 warnings，2.51s | 新64项中的最后一项：owned close自行抛CancelledError会误传为外部用例取消；实际局部边界 |
| close-self-cancel-green-py313 | exit0；6 passed/58 deselected/2 warnings，1.57s | 两行closing.cancelled检查后，同根cleanup/borrowed/外部及二次取消守卫 |
| close-self-cancel-green-py39 | exit0；6 passed/58 deselected/1 warning，2.19s | 同6项真实3.9验证。273之后仅该局部生产修复，不冒称273覆盖它 |

3.13两警告是Starlette/AnyIO弃用与LangGraph上游；3.9为LangGraph上游1项。收集失败批次不能算已执行定向通过，没有人为skip。首冻结64新增均有当时逻辑的实际定向/相关覆盖，当时没有修后一次完整全仓或3.9整批全绿重跑；后续修复覆盖见下段，不把旧528/273换成新提交结果。未执行准备中的纯内存self-cancel probe，未计额外测试。

## 首轮独审R1/R2：未知结果与attempt完整性

k64对 `4cee7f3` 独审为0 Critical/2 Important/0 Minor，主裁定两项均修。R1：`retry_safe=True` 只能说明幂等资格，不能证明已经dispatch的请求是否完成；旧abort据此将deadline/cancel/未知异常标成effect_unknown=False。仅将仍有active attempt的中断按未知记录；typed明确已知失败在进入backoff前已清active，不误改其false，已完成请求后的评测/清理亦不改历史。

R2：旧execution仅校验字段/次数，未同可信步骤覆盖和结果关联；正常成功记录可被删attempt、改deadline或越界index后继续绿。`validate_execution` 接收独立manifest计划长度和已校验steps；stored reader复用原安全投影中由manifest得出的expected_step_count与安全steps。同一step只能在已知error后继续retry，step索引必须按受控顺序覆盖，完成步骤必须有终结completed attempt；completed overall不得伴随缺步骤/错误步骤。没有使用返回者自报expected_step_count，也不引入签名证明或补虚构attempt。旧无execution同步路径保持，未dispatch的queue/init中断允许无attempt。

新增25项至89：R1四类retry_safe请求中断（deadline/cancel_event/未知异常/坏响应）；R2六类篡改×build/strict parse/stored reader共18项（删光、末次deadline、越界、缺中间、倒序、完成后重试）；3项正向known error→completed/init中断/eval中断。stored负例真实导入临时内存SQLite，篡改payload并重算普通证据digest，确保命中新语义检查而非原摘要拒绝。加上8个旧正向守卫，4cee生产行为实际22失败/11通过；没有把原有守卫说成新RED。

| 新增batch | 真实结果 |
| --- | --- |
| review-r1-r2-red | **22 failed、11 passed、56 deselected、2 warnings，11.66s**；R1四类及R2十八路径均真实失败 |
| review-r1-r2-related-green | **183 passed、2 warnings，12.81s**；4个直接消费者文件，含89新增及同步/完整性相关，不重复528/273 |
| review-r1-r2-py39-green | **33 passed、56 deselected、1 warning，3.41s**；与RED同一集合，私有3.9环境，无全量 |

仅三个生产文件窄修（async_runner/execution/integrity）和一个测试文件；版本、依赖、同步接口、A05 required/grounding/provenance、A06信任/基线及授权/TTL保持。k64已有限复审 `602a371` 并核对20个源码SHA256，R1/R2关闭、无剩余finding，随后才执行下方root验收。

## 两次root尝试与最终本地边界

已执行命令：

```powershell
& .context/A08/test-env/Scripts/python.exe -X utf8 .context/A08/run_tests.py final-root -q --tb=short
```

原session121因配额中断后只poll读取既有结果，未重启测试。`final-root.log` 完整保留command/source/exit/stdout/stderr：**exit1；1267 passed、1 failed、5 deselected、3 warnings，122.96秒，根0skip**。89新增均随根执行通过，但这不等于整批成功。

执行者漏带既定两项Windows系统副作用集成的 `-k` 排除参数（A07证据已有正确排除命令），实际仅排除5项UI，因而运行了计划任务注册/卸载和临时watcher测试。watcher通过；`tests/test_deploy_scripts.py::test_windows_startup_task_registration_is_idempotent_and_removable` 在读取PowerShell导出的中文计划任务XML时，子进程reader按UTF8解码字节0xcf失败，导致inspect.stdout为None，再触发lstrip AttributeError。第三warning即该reader线程UnicodeDecodeError，另两项仍Starlette/AnyIO和LangGraph上游。测试确实创建/更新了随机命名计划任务，finally调用unregister但未记录返回码，不能仅据此证明卸载成功；未将此称作真实部署验收。

首次basetemp创建于2026-10-28T22:48:19.5209166+08:00，日志写于22:50:22.2514831+08:00。固定任务名前缀为 `LLMTest startup test ` 加uuid4，Action实际指向本A08工作树 `deploy/start-reference-agent.ps1`、WorkingDirectory为本树根，并非basetemp；首次delay1后更新为2。主授权仅此前缀只读查遗留，2026-10-29T09:17:56.0465359+08:00查询结果MatchCount=0、ErrorCount=0，检查时无该前缀任务；无候选需要认领，未注册/执行/卸载任何任务。该检查不补造原finally返回码，也不代表没有触及过系统。

主裁定首次命令未达到既定验收范围，明确授权在同一审源补一次正确范围全量。启动前静态assert A07原始两项排除完全一致、pyproject原 `-m 'not ui'` 不变、20源码hash一致；原日志不覆盖，新名执行：

```powershell
& .context/A08/test-env/Scripts/python.exe -X utf8 .context/A08/run_tests.py final-root-scoped -q -k 'not windows_startup_task_registration_is_idempotent_and_removable and not windows_watcher_survives_failed_refresh_and_retries_next_env_save' --tb=short
```

`final-root-scoped.log` 实际 **exit0；1266 passed、7 deselected、2 warnings、根0skip，110.78秒**，89新增全部随根通过。7排除=5UI+原两项Windows计划任务/持久watcher系统集成；两warning仍原上游。此批不执行或修复两系统测试；`.context/A08/scoped-preflight.log` 保存静态参数核对。两次root各继承三个受控消费者子pytest（required失败、optional探索预期skip、显式required失败，外层成功断言），不是真实SDK/provider调用，不把子skip当根覆盖。

第一次参数遗漏及真实失败保留，第二次正确范围成功不能覆盖它。此后仅文档收口，产品/测试/依赖与审查源相同；主流程仍须当前SHA CI和合并树/独立安装发行验收，本地通过不等于可发布。

## 冻结、安装消费与下一步

`.context/A08/source-freeze.json` 记录20改变Python逐文件SHA256，清单SHA256=`50c1c58027417ecbc04c841b4870e6ed560e2d8a27d06df3d701557f3ac86d06`；`static-checks.log` 核对内存compile/3.9语法、版本与原106锁条目无无关升级、diffcheck及当前25条pytest日志；`lock-check.log` 离线uv lock --check解析110包通过，审查修复未改依赖。这些是静态证据，不替代实际测试或真实环境验收。最终仅docs交k64确认差异、20哈希与两次真实root日志，不重复pytest/root。

安装消费四根文件精确为 `tests/test_async_scenario_budget.py`、`tests/test_workflow_runner.py`、`tests/test_dify_adapter.py`、`tests/test_release_report_integrity.py`。其中只前者新增，另有 `tests/test_telemetry_storage.py` 的UTC helper修改，不能称四个新增文件。可原字节复制这四根及递归助手 `tests/test_quality_loop_engine.py`、`tests/test_quality_loop_models.py`、`tests/test_run_reporting.py`、`tests/test_telemetry_storage.py`、`tests/report_integrity_fixtures.py`、`tests/conftest.py`；本树无tests/__init__.py，消费者必要的空package marker属于harness。精确闭包SHA256为 `.context/A08/consumer-tests.json`。

上述四文件无子pytest、仓库源码/配置读取；新增v1用产品scenarios.__file__定位包内资产，其他文件均temp fixtures，预计可原字节installed运行。只要求实际wheel含 `qe_platform/scenarios/assets/reference_agent` 的14场景（原package-data），不可从仓库复制伪称安装通过；不需要根configs/M13资产。本任务无安装实测，不把该静态判断当验证。消费者须装锁定ci/dev async插件且所有产品导入来自site-packages，使用显式mock/配置清理；不借源码sys.path。

主提供A07依赖交付：PR79同head34CI成功，merge `51ca47dff46eab26737e602cdf6f8cf5e214529c` 与本base同产品树；merged1177pass/7desel/2上游warn、97.86s。独立新env wheel65pass/2仓库M13配置desel/5warn（3harness+2上游）、2.73s，14场景3资源/6测试原字节及installed-only。dev7公开3附件回下载hash/tag/source一致，wheel221156bytes、SHA256=`c9b88a20b264218b3bbd05df8a39b9631343f972ccc074821cab5d990ab308da`，Issue78关闭/master clean。这是依赖结果，不计A08验证；2仓库M13配置不称wheel资产。

当前源码独审关闭，正确范围root通过、首次误范围失败如实保留；最终docs-only/20哈希/两日志确认后交主dev8/同SHA CI/PR/合并树验收、独立wheel/Release/Issue跟踪。真实provider/async Judge/IdP/HTTPS/持久部署未验收，用户练习与掌握未评估。练习：解释queue消耗同一预算、为何max_attempts3仍不能重试chat、超时与外部副作用未知的区别；比较对话/评测/cleanup时间，复现完整步骤但required评测未完成的不可发布报告。