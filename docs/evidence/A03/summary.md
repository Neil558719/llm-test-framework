# A03：真实 Embedding 能力与必需评测策略

Issue [#68](https://github.com/Neil558719/llm-test-framework/issues/68)。分支 `codex/a03-embedding`，起点 `a764f4e8f8d3847aba5b0d05b4659dd6ceea9d37`，开始时干净。迁移版本 **`0.2.0a24.dev2`**。当前是本地实现/验证；独立审查、Push/PR、当前 SHA CI、合并与合并后验证、Release、部署及 Issue 跟踪由主流程继续，不能把本地结果标成发布完成。

## 问题与实现

旧真实 Anthropic 在没有 Embedding API 时返回确定性伪向量；通用能力探测吞掉所有异常并永久缓存 False；相似度断言对任何能力缺失无条件 skip。这会把认证/配置错误或瞬时故障转换为覆盖缺失，甚至让必需项以跳过结束。

- `EmbeddingUnavailableError` 定义在 clients.base，原 `llmtest.assertions.similarity` 导入路径继续有效，同时新增包根公开导出。它只表示明确不支持；认证、配置、限流与传输故障保留原异常类型和因果。
- Anthropic 删除伪向量退路。没有显式真实 provider 时 `embed()` 抛上述异常，`embedding_available()` 返回 False。构造函数新增 keyword-only `embedding_client`，可传显式真实 `LLMClient`；拒绝已知 `is_mock` 或 provider=mock 客户端，防止真实指标混入 Mock 向量。没有新增 provider 的配置/YAML/注册系统或真实调用。
- 通用探测缓存成功和明确不支持；仅 `EmbeddingUnavailableError` / `NotImplementedError` 产生负缓存。后者在公开 embed 入口转换为统一缺能力异常。原始 400/401/403/404/429/500/501/503、超时、断连、OSError、配置 ValueError 和未知 RuntimeError 均传播，不改成 False 或 skip。HTTP 状态码本身不能证明接口不支持，例如404也可能是错模型/错URL，501也可能是网关错误。
- 未知能力的首次瞬时故障后仍可重探并恢复；已成功探测后真实 embed 请求依旧执行，其故障不会被伪成功缓存覆盖。能力缓存按客户端实例，明确不支持后如改变 provider/config 应创建新客户端。
- `Config.embedding_policy` 默认为 required，可通过 `LLM_EMBEDDING_POLICY` 或 pytest `--embedding-policy` 显式选择 optional；命令行优先，非法值作为配置错误。`similarity()` 测量函数从不 skip，缺能力始终抛异常。
- `assert_similarity(..., required=None)` 默认遵从 Config；True 强制单项必需，False 也不能降低全局 required。optional 仅在明确不支持时探索性 skip，记录 `embedding_coverage=0`、策略和 skip 原因；成功时 coverage=1。缺能力不产生 similarity_score，也不补成0或1。
- Mock 继续使用确定性向量，`is_mock` 和 similarity/coverage 指标来源标为 mock；HTML 展示这些指标的来源及覆盖策略。真实显式 provider 指标来源来自其 embedding_source。仅这两类指标展示 meta，没有扩展其他 A02 评分行为。

## 必需项优先与迁移

| Config 策略 | 单项 required | 明确缺能力 | pytest 消费方结果 |
| --- | --- | --- | --- |
| required（默认） | None / False / True | 抛 EmbeddingUnavailableError | 非零 |
| optional | None / False | 记录覆盖缺失并 skip | 探索可为0，不能证明发布质量通过 |
| optional | True | 抛 EmbeddingUnavailableError | 非零 |

本仓库当前没有质量 manifest 的 embedding 必需项模型，不能声称已接 manifest。主代理明确接受 `required=True` 作为未来 manifest/必需评测的调用入口；将来接入必须由调用方传递这一要求，optional 不能替代它。本次没有扩 A04 权限或 A05 YAML/质量执行连接。

已有 `AppResponse(answer, sources)`、有事实的幻觉计算、A02 严格 Judge 输出和 Mock 场景保持。升级到 dev2 后，依赖旧自动 skip 或 Anthropic 伪向量的真实评测会明确失败；探索需显式 optional，严肃评测应提供真实 embedding 客户端。例：`AnthropicClient(config, embedding_client=OpenAIClient(embedding_config))`，这里只说明接口，未调用真实 provider。撤销本提交可回退行为，但会恢复已知假绿；不建议通过恢复伪向量规避失败。

## 离线验证证据

固定解释器 `C:/Users/ZhuanZ1/Desktop/项目修改/work/env-a/Scripts/python.exe`，实际 Python 3.13.15。运行器断言 llmtest 导入本工作树，不安装/更改共享环境；清除真实模型与应用配置环境且不打印值。测试替代 `_embed` 外部向量 I/O，并对 `_get_client` 设置禁止调用守卫；嵌套消费 pytest 仅构造无 native embedding 的 Anthropic，亦有 SDK 禁止守卫，没有真实模型/Embedding/API/Docker请求。

| 原始日志（gitignored `.context/A03/`） | 顶层 pytest 参数（固定带 `--llm-mode=mock --no-report`） | 实际结果 |
| --- | --- | --- |
| red.log | `-q tests/test_embedding_policy.py` | **44 failed, 2 passed** |
| green.log | `-q tests/test_embedding_policy.py tests/test_chatbot.py` | **53 passed** |
| provenance-red.log | `-q tests/test_embedding_policy.py -k 'visible_in_html or pseudo_similarity or after_success or client_probe_can_recover'` | **1 failed, 3 passed, 46 deselected** |
| related-green.log | `-q tests/test_embedding_policy.py tests/test_chatbot.py tests/test_rag_assistant.py tests/test_evaluation_validity.py tests/test_response_envelope.py tests/test_m11_observability.py tests/test_run_reporting.py tests/test_quality_loop_reporting.py tests/test_loadtest_reporting.py` | **169 passed, 2 warnings** |
| full-offline.log | `-q -k 'not windows_startup_task_registration_is_idempotent_and_removable and not windows_watcher_survives_failed_refresh_and_retries_next_env_save'` | **708 passed, 7 deselected, 2 warnings**，25.80秒；根级0 skipped |

**计数说明：** 5条顶层 pytest 命令，默认非 UI 根全量只跑一次。三种消费子进程测试分别验证：默认required退出1；optional缺能力退出0且1 skipped、HTML覆盖缺失可见；optional下required=True退出1。这三个子进程在 red/green/related/full 四批中各执行，合计12个嵌套pytest进程，因此共有17个pytest进程启动。根测试最终包含50个A03参数化实例和119个相关现有实例；708是根级实际收集实例通过数，不把子进程结果再叠加成“通过数量”。嵌套探索skip是预期策略证据，不表示根全量跳过。

不是每项新测试逐条先红：首批两项明确unsupported缓存守卫原本通过；补充批三项恢复/无伪指标守卫也直接通过。首批部分新入口不存在而出现TypeError/ImportError已如实保留。补充RED发现 metric.meta 已标mock但HTML不展示，修复后才满足“报告标mock”。根全量的7项排除为5 UI、Windows系统任务注册/卸载和PowerShell watcher系统集成两项；两警告来自既有Starlette/AnyIO及LangGraph依赖。没有删除负例或降低阈值。

根全量结束后仅执行小版本元数据动作：pyproject、uv.lock本项目节点、源码 `__version__` 同步dev2。AST/TOML窄结构验证三处一致，将旧项目version替换后整个pyproject/lock结构与base相同，依赖节点完全不变。`version-metadata.log`保留。没有重解锁、依赖升级、pip或真实环境安装。`python -m compileall -q llmtest tests/test_embedding_policy.py`及`git diff --check`通过；版本动作后不重复根全量。

## 依赖交付接续与未验证边界

主代理报告 A02 已合并为 `f7c28b08360e6aa981ea43d677f67cba2065d31c`，代码树与本分支base a764同；合并后显式Mock658通过/7排除/2警告，独立dev1安装包14/14场景与三静态资源通过，隔离运行A02有效性95通过且无skip；dev1预发布由主流程推进。A01 dev0已发布并回下载校验hash/tag，Issue61/63/65已关闭。这些是主流程提供的验收记录，本子代理未重复执行。

A03尚未验证：真实SDK/模型/embedding provider、实际HTTP错误体与供应商配置、Linux/Python3.12/3.14、UI、安装wheel、当前SHA CI、独立审查、合并后验证、Release/部署，以及未来manifest接线。测试用受控异常证明错误分类与缓存决策，不把它等同真实API兼容验收。

## 用户复现练习（待完成，掌握未评估）

10–20分钟离线完成：用一次TimeoutError后恢复向量的替身证明能力可重探；再返回明确NotImplementedError观察负缓存；列出404为什么可能是配置错误；对照默认required、optional、optional+required=True三种pytest退出码及HTML coverage；解释为何Mock cosine=1不能当真实模型质量证据。最后说清本地通过、独立审查、CI与已发布的区别。