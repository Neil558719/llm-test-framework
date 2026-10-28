# A08：原生异步场景预算

Issue [#80](https://github.com/Neil558719/llm-test-framework/issues/80)，独占树 `codex/a08-async-budget`，base `4d5a2bc789b688273acf7e6c9688c4705114dc6d`。版本保持dev7；本地实现/相关验证收口，准备冻结交k64独审，**尚未root/push/CI/合并/安装/发行**。独审关闭后才唯一finalroot；主整合时再做dev8。实现边界见[异步场景预算指南](../../异步场景预算指南.md)。

## 实现与兼容

新增原生async协议、Dify HTTPX和Reference ASGI适配器、ExecutionBudget及有界AsyncScenarioRunner；实际v1工厂/CLI/JSON/HTML已接通。一个排队前单调deadline涵盖queue/rate/init/request/backoff/required eval；默认一次，重试需显式幂等和可重试，保留effect_unknown。owned/borrowed客户端/adapter分别清理，有限cleanup宽限、外部取消继续传播；不使用to_thread或3.11-only timeout API。

同步入口语义不变，追加字段/旧JSON省略可选execution。显式async evaluator复用A05的required/grounding/provenance/结果校验，拒绝同步回调而不是省略required。全对话后的评测/清理失败保留真实步骤；A06原始证明、持久安全投影/reader认识执行状态并拒绝release。policy在执行前冻结入scoring_assets，预算变化不能沿用旧baseline。A07对话耗时继续排除init/初始队列/Judge，stage不冒充SUT延迟。

3.9实际入口RED后，仅修必要链路：三模块8个slots条件化（>=3.10原形状保留，3.9 frozen字段保留）；application_scope/auth.access延迟注解；LangGraph AgentState.fault一处Optional；新增Python<3.10的eval-type-backport。UTC测试助手仅将Z等价规范为+00:00，原TTL/断言不改。原106锁定包版本和非project条目保持，锁新增四条必要package记录：pytest-asyncio1.2.0/1.4.1、backports-asyncio-runner1.2.0、eval-type-backport0.4.0，共110；ci/dev声明pytest-asyncio，版本仍dev7。

## 环境与实际尝试

Windows。初两批用既有 `work/env-a/Scripts/python.exe` 只读；它缺pytest-asyncio。随后3.13.15用本树 `.context/A08/test-env` 私有overlay，仅插件装在私有环境，其余依赖通过私有pth只读引用env-a，**不称完整依赖隔离**。首次venv未继承env-a导致pytest元数据导入失败，记录 `private-import-first.log` 后修正私有pth，未改共享环境。3.9.25解释器和完整frozen dev环境均在 `.context/A08/python` / `py39-env`，必要下载/构建仅私有缓存；3.9使用pytest8.4.2/asyncio1.2.0，3.13使用pytest9.1.1/asyncio1.4.1。

运行器每次清LLM_/OPENAI_/ANTHROPIC_/DIFY_/QE_/REFERENCE_AGENT_/OIDC_/AUTH_配置、强制mock/development/UTF8、断言产品从本树导入、独立新basetemp且不覆盖日志。无真实Judge/provider/SDK/IdP调用、用户容器操作、共享pip写入或新代理。pytest日志UTF8，PowerShell依赖日志UTF16；首次统计误按UTF8读取所有log失败，后来按 `command=` 字节前缀仅识别pytest，不影响任何测试结果。

**64新增；20条顶层pytest/20进程，0root、0消费者子pytest。** 原始命令/source/exit/stdout/stderr为 `.context/A08/<batch>.log`，可复现命令见[清单](commands.md)。不是每一项都逐条先红；接口缺失、旧能力局限、实际实现缺陷、已有守卫与夹具问题分别列出。

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

3.13两警告是Starlette/AnyIO弃用与LangGraph上游；3.9为LangGraph上游1项。收集失败批次不能算已执行定向通过，没有人为skip。64新增均有当前逻辑的实际定向/相关覆盖，但没有修后一次完整全仓或3.9整批全绿重跑；准确结果按上表保留。未执行准备中的纯内存self-cancel probe，未计额外测试。

## 冻结、安装消费与下一步

`.context/A08/source-freeze.json` 记录20改变Python逐文件SHA256；`static-checks.log` 核对内存compile/3.9语法、版本与原106锁条目无无关升级、diffcheck及20条pytest日志；`lock-check.log` 离线uv lock --check解析110包通过。这些是静态证据，不替代实际测试或真实环境验收。独审将先读源码、证据和必要离线probe，不重复常规pytest/root；关闭发现后才唯一finalroot。

安装消费四根文件精确为 `tests/test_async_scenario_budget.py`、`tests/test_workflow_runner.py`、`tests/test_dify_adapter.py`、`tests/test_release_report_integrity.py`。其中只前者新增，另有 `tests/test_telemetry_storage.py` 的UTC helper修改，不能称四个新增文件。可原字节复制这四根及递归助手 `tests/test_quality_loop_engine.py`、`tests/test_quality_loop_models.py`、`tests/test_run_reporting.py`、`tests/test_telemetry_storage.py`、`tests/report_integrity_fixtures.py`、`tests/conftest.py`；本树无tests/__init__.py，消费者必要的空package marker属于harness。精确闭包SHA256为 `.context/A08/consumer-tests.json`。

上述四文件无子pytest、仓库源码/配置读取；新增v1用产品scenarios.__file__定位包内资产，其他文件均temp fixtures，预计可原字节installed运行。只要求实际wheel含 `qe_platform/scenarios/assets/reference_agent` 的14场景（原package-data），不可从仓库复制伪称安装通过；不需要根configs/M13资产。本任务无安装实测，不把该静态判断当验证。消费者须装锁定ci/dev async插件且所有产品导入来自site-packages，使用显式mock/配置清理；不借源码sys.path。

主提供A07依赖交付：PR79同head34CI成功，merge `51ca47dff46eab26737e602cdf6f8cf5e214529c` 与本base同产品树；merged1177pass/7desel/2上游warn、97.86s。独立新env wheel65pass/2仓库M13配置desel/5warn（3harness+2上游）、2.73s，14场景3资源/6测试原字节及installed-only。dev7公开3附件回下载hash/tag/source一致，wheel221156bytes、SHA256=`c9b88a20b264218b3bbd05df8a39b9631343f972ccc074821cab5d990ab308da`，Issue78关闭/master clean。这是依赖结果，不计A08验证；2仓库M13配置不称wheel资产。

当前待k64独审、唯一root，之后主dev8/同SHA CI/PR/合并树验收、独立wheel/Release/Issue跟踪。真实provider/async Judge/IdP/HTTPS/持久部署未验收，用户练习与掌握未评估。练习：解释queue消耗同一预算、为何max_attempts3仍不能重试chat、超时与外部副作用未知的区别；比较对话/评测/cleanup时间，复现完整步骤但required评测未完成的不可发布报告。