# A02：评测有效性与真实 Judge 输出契约

Issue [#64](https://github.com/Neil558719/llm-test-framework/issues/64)。分支 `codex/a02-validity`，起点 `4d8ff42ebd043d001a60ca139a6168272b849d10`，开始时工作树干净。当前仅本地实现/验证；独立审查、Push、PR、当前 SHA CI、合并、合并后验证、Release、部署和 Issue 跟踪由主流程完成，不能据本记录标记发布。A01 依赖代码已验证，不把 A01 标为已发布。

## 行为修正

- `HallucinationReport` 新增 `status/reason`，采用 `passed/failed/inconclusive/error/not_applicable`。有事实且完成核对时保留原来的三个比例计算；空 claims 的幻觉率、支持率、矛盾率均为 `None`。测量报告有幻觉则 `failed`，无幻觉则 `passed`；阈值断言根据 `max_rate` 更新最终通过状态。
- 必需的 `assert_hallucination_rate` 遇空 claims 抛 `llmtest.evaluation.EvaluationInconclusiveError`，记录未通过的断言，不把空分母变成 0%。模型/JSON 错误保留 `error` 报告并原样向外抛出，错误摘要只含异常类型。
- 合法非事实回复只能由调用方明确选择 `detect_hallucination(..., no_claims_policy='not_applicable')`，并承担判断回复合法且无事实内容的责任。记录策略原因，三个率值仍为空，排除幻觉统计分母。必需断言没有此豁免参数；发布 manifest 的允许规则留给后续集成，未在 A02 接 YAML。
- OpenAI/Anthropic 共享严格输出解析：`equivalent` 必须是 JSON 布尔，语义 score 在 `[0,1]`，Judge score 在 `[1, spec.scale]`，confidence 在 `[0,1]`，均为有限 JSON 数字且不能用布尔/字符串代替。拒绝 NaN、正负 Infinity、超大整数和越界；不再钳位。verdict 仅接受三个大写枚举。事实提取必须是非空字符串组成的数组，空数组有明确无结论语义；不再把无效提取回退成分句。
- 语义 `equivalent` 与 score 按现有 Mock/默认断言的 0.7 边界一致；提示中明确这一规则，矛盾输出拒绝。断言同时要求肯定结论和调用方 score 阈值；降低阈值不能把 `equivalent=False` 变成通过。无效语义 JSON 不再回退 embedding；Anthropic 的独立 embed 行为属于 A03，未改。
- 汇总 `mean_judge_score` 为所有 Judge 结果的归一化均分，每次结果等权；`evaluated_count` 是已完成 Judge 与幻觉评测次数，不是用例数、正确答案数或金标数。`inconclusive_count/not_applicable_count/evaluation_error_count` 是相应幻觉报告数。三个率值聚合排除无效报告，已有有效事实的逐用例均值口径保持。
- `accuracy` 只从 `tracker.add_gold_result(correct: bool)` 的显式金标判定计算，`gold_count` 是分母，缺金标时为 `None`。名为 accuracy 的 Judge rubric 也不会自动创建金标。旧 `accuracy=Judge均分` 含义已 deprecated，请改读 `mean_judge_score`。
- HTML 分开展示 Judge 均分、金标准确率及金标分母，展示无结论/不适用/错误及原因；空率值不画绿色 0% 条。历史记录新增 `evaluation_schema=2`，旧 history.json 的 accuracy 只在 Judge 均分列展示，金标列为空，原记录不改写。

## 接口取舍与迁移

计划中的 `rate` 对应仓库真实公开属性 `hallucination_rate`，未添加重复别名。`AppResponse(answer, sources)`、真实来源的传递方式及 Mock 用途保持；没有新增真实模型、embedding provider、权限或 YAML 配置。

正确性字段（equivalent/score/verdict/confidence）必须存在。解释字段 reasoning/evidence 延续可省略为空字符串的兼容约定；若出现则必须是字符串，不把非字符串强制转成文本。Judge 分数接受有限整数或小数，保留原有 float API；提示仍请求整数。

迁移采用评测历史 schema v2，不涉及数据库或包版本变化。消费者需按 `status` 和可空率值处理；不要用 `rate or 0`，也不要用 `accuracy` 继续显示 Judge 质量均分。错误输出应捕获 `ValueError`（契约错误为子类 `EvaluationOutputError`）；缺证据可单独捕获 `EvaluationInconclusiveError`。撤销本提交能回退代码，但会恢复已知假绿；历史 v2 记录仍保留可辨别版本，不需要删除历史。

## 本地证据

固定解释器：`C:/Users/ZhuanZ1/Desktop/项目修改/work/env-a/Scripts/python.exe`，实际 Python 3.13。运行器确认 `llmtest.__file__` 来自本工作树，没有 pip/环境指向修改。原始命令、输出和退出码保留在 gitignored `.context/A02/`，不提交机器日志。以下均使用 `--llm-mode=mock --no-report`，运行器清除真实模型与应用配置环境，不输出值；新真实客户端测试替代 `_complete` 模型 I/O，保留 JSON 提取与真实业务逻辑，并禁止 SDK 与 embed 调用。

| 日志 | pytest 参数（除固定离线参数外） | 结果 |
| --- | --- | --- |
| `red.log` | `-q tests/test_evaluation_validity.py` | **84 failed, 2 passed**；旧行为触发空率、默认值、强制转换、越界、回退及新接口缺失 |
| `green.log` | `-q tests/test_evaluation_validity.py tests/test_rag_assistant.py tests/test_chatbot.py` | **96 passed** |
| `boundary-red.log` | `-q tests/test_evaluation_validity.py -k 'partial_claims or oversized or weights or history or malformed or records_error'` | **3 failed, 6 passed, 86 deselected**；None 的 HTML 格式化、两提供商超大整数溢出 |
| `related-green.log` | 上述三个文件，加 `test_m11_observability/test_response_envelope/test_run_reporting/test_quality_loop_reporting/test_loadtest_reporting.py` | **119 passed, 2 warnings** |
| `full-offline.log` | `-q -k 'not windows_startup_task_registration_is_idempotent_and_removable and not windows_watcher_survives_failed_refresh_and_retries_next_env_save'`，默认排除 UI | **658 passed, 7 deselected, 2 warnings**，30.34 秒 |

初次交接前共 **5 次 pytest 调用**，全量只执行一次。最终 A02 文件有 95 个参数化实例，相关集回归另含 24 项现有用例。RED 是分批运行，不声称每项新测试都逐条先红：首批两个合法行为守卫原本通过，补充批次六项已实现路径也直接通过。部分旧路径抛 AttributeError 而非受控 ValueError，同样不满足输出错误契约。补充 RED 的完整日志先落盘，随后控制台 GBK 编码打印失败；已读取原始日志核实真实 pytest 结果并修复运行器 stdout 编码，未覆盖 RED 日志。

另执行一次 `python -m compileall -q llmtest tests/test_evaluation_validity.py`，退出 0；`git diff --check` 通过。自审生产 diff、新测试、状态表和迁移说明，确认新增 prompts 仅明确真实语义契约，judge/evaluator 只纠正“准确率”旧文案。`.context/` 已验证被 Git 忽略；原始 RED/GREEN 和全量日志全部保留。

全量 **0 skipped**，7 deselected 包括 5 项 UI、Windows 系统计划任务注册/卸载用例，以及会启动 PowerShell watcher 的系统集成用例。没有运行 Docker、浏览器、真实模型/API，也没有修改主 checkout、共享解释器、机器任务或其他工作树。上游 Starlette/AnyIO 和 LangGraph 两个弃用警告保留。实际 Linux/3.12/3.14、真实 SDK/模型、UI、CI、Release、部署与用户复现未验证。

## 用户复现练习（待完成，掌握未评估）

用 10–20 分钟完成：让离线真实客户端替代输出依次返回 `[]`、`{"equivalent":"false","score":0.9}`、`{"score":NaN}`，解释为什么它们分别属于证据不足或输出错误；给合法问候显式声明不适用，证明不会增加幻觉分母；记录 helpfulness 90/100 但没有金标，再记录三项金标真/假/真，对照均分与 2/3 正确率。最后说明本地通过为什么还不足以声称完成发布。

## 独立审查补充：Judge 图表副标题

独立 reviewer 在 `51237ff` 发现 Minor：Judge 图表副标题仍写“聚合为准确率”。主代理授权仅修本文案、加强既有 HTML 契约并窄验证。现在统一为“归一化得分（得分/满分），聚合为 Judge 均分”；测试验证旧误导文案不存在及新标签正确。`review-subtitle-red.log` 对应 `-q tests/test_evaluation_validity.py -k html_preserves_empty`，**1 failed, 94 deselected**；`review-subtitle-green.log` 对应 `-q tests/test_evaluation_validity.py -k 'html or history'`，**2 passed, 93 deselected**。`git diff --check` 通过。累计 **7 次 pytest 调用**；此文案修复没有重跑全量，上方全量结果归属原提交 `51237ff`。其余独立审查结果、CI 与交付仍待主流程。