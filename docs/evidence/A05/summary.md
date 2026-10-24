# A05：执行 YAML 质量声明与聚合证据

Issue [#73](https://github.com/Neil558719/llm-test-framework/issues/73)，分支 `codex/a05-scenario-quality`，base `2356b1e2d1d80e2266b021e43fb098ce642b5ed4`。保留dev4，不改pyproject/uv.lock/共享环境。根台账由主维护。主流程最新依赖检查点：PR74 head2356b1e的34项checks全SUCCESS，A04b无剩余审查项并合并 `55b22550e9beb35693a19f8a50135cb08f7d7f25`，同树全量910通过/7排除/2警告、独立wheel202鉴权隔离+14场景/3静态资源通过。[dev4](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev4) 已发布并回下载hash/tag/三附件验证，wheel SHA256=`1dae6182a3fd8c64059aec759eb4905539da1e9be2e886e06ac672b919cea946`，Issue72已关闭。这些是主流程提供的证据，本任务未重复执行，也不计入A05覆盖；真实IdP/HTTPS/持久部署未验收。

## 实现边界

DSL仅五种声明及规范化阈值；严格拒绝未知、布尔、字符串、非有限、越界及optional字段。runner显式接收quality_evaluator，无配置不选registry/Mock/real；声明全部required。完整对话只评最终实际回答、对应最后用户问题、实际sources；中断不取前轮回答。缺grounding由平台判inconclusive且不委托相关检查，混合声明只交付可评子集，原声明集保持。空claims仍None/inconclusive。

helper显式复用llm_judge/detect_hallucination，保留Judge1..100量纲；非法测量在进入tracker前拒绝，不钳位。回调必须按冻结声明返回完整且唯一的合法结果，不能改required/threshold；受控error阻断，异常原文不进质量报告。旧5个位置字段与AppResponse保持；accuracy=Judge rubric，JSON score_kind及HTML明确不是金标准确率，不add_gold_result，A02 mean_judge_score/gold分母不变。Mock来源可见，只证明离线接线，可按现有离线required门禁通过，不新增live资格系统。

报告保留旧rich JSON形状，HTML展开工具参数/业务expected actual、质量原因/阈值/来源/Trace并转义。工具差异沿用failed_assertions，不加会破坏quality-loop脱敏导入的新顶层字段。既有14场景仍默认离线，无DSL资产改写。说明与显式注入例子见[场景质量评测指南](../../场景质量评测指南.md)。

## 验证环境与准确尝试

Windows x64/Python3.13既有 `work/env-a/Scripts/python.exe -X utf8`；私有运行器 `.context/A05/run_tests.py` 断言llmtest.__file__属于本树，清LLM_/OPENAI_/ANTHROPIC_/DIFY_/QE_/REFERENCE_AGENT_/OIDC_/AUTH_真实配置，子进程强制mock/development/UTF8。每批新basetemp。本地固定/临时SQLite、TestClient、确定性替身；A02真实客户端解析测试替换model I/O并禁止SDK。零真实Judge/provider/SDK/IdP调用，未Docker/pip/push或创建子代理。没有用全局Temp复用结果。

原始完整命令、stdout/stderr、退出码均保存在gitignored `.context/A05/<batch>.log`。初稿7次、审查修复3次、最终唯一全量1次，累计 **11次顶层pytest**；前10批没有消费者子pytest，最后全量继承A03的3个受控子pytest，共 **14个pytest进程**。

| batch | 退出码与结果 | 解释 |
| --- | --- | --- |
| red | 1；57 failed、2 warnings | 初次旧行为；其中12项tracker monkeypatch路径错误，不当功能RED |
| red-corrected | 1；57 failed、2 warnings | 修正导入后旧生产代码真实RED：缺入口/任意DSL/忽略质量/helper未存在/门禁及报告缺失 |
| green | 0；57 passed、2 warnings | 初始最小实现 |
| boundary-red | 1；12 failed、75 deselected、2 warnings | 3项真实边界失败，9项测试误用不存在tracker.current，不当功能RED |
| boundary-red-corrected | 1；12 failed、75 deselected、2 warnings | 改为spy add_judge后真实RED：缺grounding callback绕过2、JSON语义1、非法测量污染tracker9 |
| boundary-related | 1；117 passed、2 failed、2 warnings | 新87项全绿；旧日期元数据/未执行质量passed两个成功契约冲突，已迁移并保留负例 |
| related-green | 0；310 passed、2 warnings，11.41秒 | 21文件A05/DSL/runner/gate/report/A02/旧AppResponse/工具业务/Dify/quality-loop消费者 |

新文件87项，其中首57和后12边界分别真实先红；另18项阈值端点、max-rate方向、异常、falsey显式client、最终轮/来源等守卫直接验证，不宣称每项逐条先红。两次测试错误及两条旧契约失败不隐藏、不计通过。旧日期归一化用合法setup.knowledge.document_id继续验证，同时保留quality.release_date拒绝；未配置质量改为passedFalse并继续断言not_executed/incomplete。

以下命令均在本工作树运行；运行器展开后的pytest绝对解释器、源码路径与basetemp见各日志首行：

```powershell
$a05Python = 'C:/Users/ZhuanZ1/Desktop/项目修改/work/env-a/Scripts/python.exe'
& $a05Python -X utf8 .context/A05/run_tests.py red -q tests/test_scenario_quality.py
& $a05Python -X utf8 .context/A05/run_tests.py red-corrected -q tests/test_scenario_quality.py --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py green -q tests/test_scenario_quality.py --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py boundary-red -q tests/test_scenario_quality.py -k 'runner_cannot_delegate or json_rubric or malformed_judge' --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py boundary-red-corrected -q tests/test_scenario_quality.py -k 'runner_cannot_delegate or json_rubric or malformed_judge' --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py boundary-related -q tests/test_scenario_quality.py tests/test_scenario_loader.py tests/test_workflow_runner.py tests/test_v1_gate.py tests/test_run_reporting.py --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py related-green -q tests/test_scenario_quality.py tests/test_scenario_loader.py tests/test_workflow_runner.py tests/test_v1_gate.py tests/test_run_reporting.py tests/test_evaluation_validity.py tests/test_response_envelope.py tests/test_tool_contracts.py tests/test_business_assertions.py tests/test_contract_integration.py tests/test_dify_adapter.py tests/test_dify_adapter_config.py tests/test_dify_gate.py tests/test_m14_dify_assets.py tests/test_quality_loop_models.py tests/test_quality_loop_engine.py tests/test_quality_loop_api.py tests/test_quality_loop_storage.py tests/test_quality_loop_cli.py tests/test_quality_loop_reporting.py tests/test_quality_loop_contract.py --tb=short
```

## 独立审查修复：自定义测量证据与本次Judge来源

独立审查源 `3345ea5`、文档接续 `f6c42b1`，结果0 Critical / 1 Important / 1 Minor。Important：wrapper的claims/verdict原本直通自定义client，UNKNOWN枚举或NaN confidence会被底层视为非幻觉而产出0率；Minor：测量前读取model会把冷默认OpenAI/Anthropic报成client名称，也可能复用前次来源。

仅窄改 `workflow_runner/quality.py`：复用A02 `parse_claims`、`parse_verdict`，强制claims为list且每项为非空字符串，合法空list仍no_factual_claims/inconclusive/None；核对ClaimVerdict类型和claim匹配，允许三枚举，confidence严格有限0..1数值非bool，evidence为字符串，非法保留error/None。测量实际返回后读取本次Judge metadata，未完成测量不借前次model。版本仍指llmtest接线版本，未使用SUT元数据；未改llmtest内核/依赖/版本。

新增27项，现114项：21种claims/verdict畸形、2类客户端×2种测量的冷默认/后续模型及失败前旧model共26项真实先红；合法空claims兼容守卫原本通过。UNKNOWN枚举与SUPPORTED+NaNconfidence分别独立负例，未混归因。模型来源测试替换整个_get_client工厂，以本地SimpleNamespace驱动真实客户端格式路径，不导SDK或访问供应商。

| batch | 退出码与结果 |
| --- | --- |
| review-red | 1；26 failed、1 passed、87 deselected、2 warnings |
| review-green | 0；27 passed、87 deselected、2 warnings |
| review-related-green | 0；226 passed、2 warnings，3.15秒；A05/A02/runner/gate/report/AppResponse共6文件 |

```powershell
& $a05Python -X utf8 .context/A05/run_tests.py review-red -q tests/test_scenario_quality.py -k 'explicit_client_rejects or explicit_client_legal_empty or evaluator_records_model_after or failed_measurement_does_not' --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py review-green -q tests/test_scenario_quality.py -k 'explicit_client_rejects or explicit_client_legal_empty or evaluator_records_model_after or failed_measurement_does_not' --tb=short
& $a05Python -X utf8 .context/A05/run_tests.py review-related-green -q tests/test_scenario_quality.py tests/test_evaluation_validity.py tests/test_workflow_runner.py tests/test_v1_gate.py tests/test_run_reporting.py tests/test_response_envelope.py --tb=short
```

修复阶段没有重复原21文件310或全量；310仅归属初稿，修后相关226。静态核对记录 `review-static-checks.log`，新冻结哈希 `review-source-freeze.json`；旧源哈希保留供审查追溯。

## 有限复审与唯一 final root

独立有限复审确认 `be21c8d6b916e3f9b6589db7b1b94df753befdaf` / tree `cad29914ef5ada2c64abca413f4539a6ec684ade` 的原Important/Minor均关闭，无剩余Critical/Important/Minor；审查未重跑pytest/full/probe。确认源/测试哈希后，在该冻结源上执行唯一默认非UI全量：

```powershell
& $a05Python -X utf8 .context/A05/run_tests.py full-offline -q -k 'not windows_startup_task_registration_is_idempotent_and_removable and not windows_watcher_survives_failed_refresh_and_retries_next_env_save' --tb=short
```

`full-offline.log`：**exit0；1024 passed、7 deselected、2 warnings、0 skipped，69.91秒**。7排除为5UI和2项Windows计划任务/持久watcher系统副作用集成；两警告来自Starlette/AnyIO与LangGraph。根回归继承3种A03消费者（required缺能力失败、optional探索预期1skip、显式required失败，外层均成功断言且禁止SDK）；子进程探索skip不计作根覆盖或根0skip。没有真实Judge/provider/SDK/IdP调用，没有重复finalroot。此后仅docs收口，不变更冻结源/测试，不把最终docs提交说成另跑一次全量。

## 当前检查点与未完成项

本地相关/窄修、独立复审、最终冻结源唯一全量通过，分支源码继续冻结。初稿 `& $a05Python -X utf8 .context/A05/static_checks.py` 退出0，12个变更Python文件compileall、git diff --check通过；修复阶段同脚本加review参数核对两个窄修Python文件。三处版本dev4，llmtest内核/依赖/原场景资产不变，scratch已忽略。A04b结果不计作A05覆盖。Push/PR/当前SHA CI、合并及合并树验证、wheel/安装/Release、部署与Issue追踪由主流程接续，尚不满足交付完成条件。主后续统一dev5；本地或显式Mock通过不代表真实质量，真实provider、其他Python/Linux、UI及持久生产部署未验收，用户练习待完成、掌握未评估。

## 10–20分钟复现练习（待完成）

用相同多轮场景先不注入Judge，观察not_executed/incomplete/失败门禁；再显式注入Mock解释其来源和证据边界。用80/100与0.8、幻觉率0.5与max_rate0.49/0.5对照阈值方向；删除实际sources观察inconclusive且零相关模型调用。第二轮抛错说明为何前轮成功不是最终质量证据。自定义回调删一个指标/改required/返回NaN，找到error原因。比较failed completeTrue与error completeFalse，指出accuracy rubric、mean_judge_score和显式金标分母的区别；查看HTML转义差异和Trace，区分本地接线、独立review、CI与发行证据。不记录收益百分比。