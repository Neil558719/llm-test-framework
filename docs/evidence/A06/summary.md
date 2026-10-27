# A06：报告完整性、可信计划与可比较基线

Issue [#76](https://github.com/Neil558719/llm-test-framework/issues/76)，分支 `codex/a06-report-integrity`，base `725a4135f5e6b30e114d3bb56fd3871a750b4f77`。本任务保持 dev5，pyproject/uv.lock/共享环境不改；主整合时统一 dev6。恢复实施日期为 2026-10-27，原阶段日期不改写。

依赖接续由主报告：A05 已合并 `b16aa0b61c2e9a5ee974a105bea2b11ef82be56c`，与本任务 base 测试源码一致；34 项 CI、合并树 1024 通过/7 排除/2 警告、独立 wheel 114 质量测试及 14 场景/3 资源通过。[dev5](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev5) 已发布，三附件回下载逐字节及 tag/source 核验，wheel SHA256=`327ac60cb1ff56994b370eea00212820f1970444d6cce392aa033d93a232ef85`，Issue73 关闭。这些不是本任务重新执行的覆盖；真实供应商、IdP 和持久部署未验收。

## 实现与信任边界

`reporting/integrity.py` 冻结独立选择的 ScenarioSpec，返回内部只保存 canonical JSON 的不可变 RunManifest；as_dict 每次产生独立对象。manifest 包含唯一 scenario_id、scenario_sha256、expected_steps/index/user 摘要、quality_policy_sha256、完整输入/setup/工具/断言/required 阈值及 asset_fingerprint。默认评分资产从实际 JudgeSpec 及提示模板获取，未复制终端中文；自定义评分规则由调用方在 scoring_assets 显式记录。模型/provider/prompt 等实验版本保留在响应和安全投影中，不无差别加入必须相等的受控资产。

v1_gate 在首次 adapter/Judge 调用前冻结选择；空选择保留旧失败报告行为，明确 legacy_unverified/无发布资格。build_run_report 无独立 manifest 时不反造期望集合，保留只读 legacy。v2 原生、导入及持久化读取共用完整性模块：核对 ID/步骤/必需指标覆盖和类型，复算确定性断言、score/status/阈值、complete/passed/counts/gate；合法业务失败可完整但不通过。adapter 初始化失败、中途 error 和质量 inconclusive 保留解释性报告及实际已执行步骤，不伪造后续调用或借前轮回答证明最终质量。

上传自携 manifest 只证明结构一致；没有独立 expected_manifest 或服务端可信 resolver 时，状态为 unverified_manifest，不能比较发布。CLI --manifest 是操作者另行选择的可信文件；HTTP 只能通过 create_telemetry_app/repository 的服务器注入 resolver，body expected_manifest 拒绝。服务器根据独立计划决定 verification/release_eligible，不能由 JSON 自报字段授权。HTML 明确区分 Reported gate、Verification、Release eligible；历史质量 HTML 的通过观察标为 REPORTED PASSED / UNVERIFIED。

比较始终要求不同 run ID、同应用、相同环境、完整 verified_v2 和一致控制资产；未实现额外的环境兼容映射。改变同 ID 的输入、工具/断言、阈值或 rubric 必须选择新 baseline。模型/prompt 版本可变并记录。显式 Mock 可通过既有离线 required 规则，导入后来源仍可见，只证明离线接线，不代表真实质量。无默认模型调用、无签名或审批系统。

导入按完整 canonical report 的 content_sha256 判同 ID 内容，不再把不同执行结果擦成相同汇总。数据库只保留安全投影、内容/响应/资产摘要、合法标签、质量覆盖和聚合；问题、答案、sources、工具原参数和错误原文不入库。不安全来源标签替换 redacted 并保存摘要。HTTP 作用域、同应用完整链、SQL 过滤和 TTL 不放宽；生产未知/无效的持久化 proof 隐藏为 404，HTTP 自报 proof 仍 400，程序错误不当缺记录吞掉。

## 迁移与恢复

quality_loop 从 1 升到 2，使用现有 MigrationRunner；新增独立 verification/content_sha256/complete/asset_fingerprint 列，与新安全 payload 交叉核验。旧 payload、IDs、links、历史 validation 原字节保留，不回填可信结论；旧记录 legacy_unverified 只读。新 validation 保存 report_policy_version=2，原 scope_application/scope_policy_version 证明仍必需。

schema_requirements 动态要求 quality_loop=2，readiness 按该要求检查；合成质量库 backup/restore 显式 expected_versions={quality_loop:2}。原 deploy restore.sh/ps1 只管理 reference_agent 库，并按其 _MIGRATIONS 取版本，未扩大或误改该作用域。迁移失败回滚、重复打开、链接保留、过期及快照恢复均用临时 SQLite。旧 reader 不能读 schema2；回退必须恢复配套迁移前快照，不能降版本号或只回退源码。

## 准确验证记录（冻结前）

既有 Windows/Python3.13 解释器 `work/env-a/Scripts/python.exe -X utf8`。私有 `.context/A06/run_tests.py` 断言 llmtest.__file__ 位于本树，子进程清除真实 LLM_/OPENAI_/ANTHROPIC_/DIFY_/QE_/REFERENCE_AGENT_/OIDC_/AUTH_ 配置，强制 mock/development/UTF8，每批 fresh basetemp。零真实 Judge/provider/SDK/IdP 调用，无 Docker/pip/push/子代理或用户数据库操作。

当前 **15 条顶层 pytest / 15 个 pytest 进程**，尚未 finalroot，无消费者子 pytest。原始完整命令/输出/退出码位于 gitignored `.context/A06/<batch>.log`；[命令清单](commands.md)保留每次实际参数，失败没有覆盖。新文件 70 项及隔离文件新增 2 项，共 72 项；旧 count/duplicate/API-scope 守卫不冒充新缺陷。不是每项都逐条先红。

| batch | pytest exit / 实际结果 | 归因 |
| --- | --- | --- |
| old-entry-red | 1；9 failed / 3 passed / 2 warnings，1.87s | 旧入口实际 9 缺陷，3 原有守卫通过 |
| old-entry-green | 0；12 passed / 2 warnings，1.67s | 最小旧入口修复；不是 v2 验收 |
| v2-interface-red | 1；14 failed / 12 deselected / 2 warnings，1.81s | 缺模块接口 RED，不混入旧 9 缺陷 |
| v2-interface-green | 1；13 failed / 1 passed / 12 deselected / 2 warnings，2.72s | dataclass 可选 None 回读 DSL 的实现错误 |
| migration-red | 1；2 failed / 26 deselected / 2 warnings，1.34s | schema1 与缺 proof 列 |
| v2-migration-green | 0；28 passed / 2 warnings，1.33s | 首轮 v2/迁移通过 |
| semantics-red | 1；8 failed / 47 passed / 2 warnings，3.12s | 4 类型/grounding/HTML 缺口；3 DSL 列表夹具错误、1 未建 telemetry 表错误 |
| entry-regression | 1；2 failed / 299 passed / 2 warnings，32.08s | 旧 release 负例预期与 schema1 断言需迁移 |
| incomplete-visible-red | 1；3 failed / 2 passed / 55 deselected / 2 warnings，1.42s | 初始化失败报告、默认 rubric 摘要、历史 HTML 标签；中途 error/inconclusive 已绿 |
| strict-provenance-red | 1；6 failed / 60 deselected / 2 warnings，2.07s | v2 降级、answer/sources/usage 转换、provider 类型及 Mock 来源丢失 |
| related-green | 0；321 passed / 2 warnings，33.78s | 14 相关文件 |
| manifest-columns-native-red | 1；3 failed / 2 passed / 66 deselected / 2 warnings，3.14s | 显式摘要/独立列缺失、原生空选择兼容回归；14 场景守卫已绿 |
| final-guards | 1；4 failed / 154 passed / 2 deselected / 2 warnings，32.69s | 3 链接夹具占位符错误；生产持久化 proof POST 错回400；本批仅临时未选2项programming-error，下一批完整覆盖 |
| experimental-metadata-red | 1；1 failed / 69 deselected / 2 warnings，1.37s | 安全投影丢失 SUT 模型/prompt 实验记录 |
| pre-review-related | 0；387 passed / 2 warnings，35.31s | 21 文件，含完整 programming-error 守卫、原生14场景、旧位置接口、质量/作用域/迁移/恢复 |

一次不限定范围的只读 rg 盘点因扫描太宽主动停止，无测试/文件修改，不当 pytest 尝试。随后仅检查跟踪的 CI/容器/UI/安装包脚本：UI 无质量导入或 release 种子；容器恢复仍是 Agent 专用。installed-wheel 原有 14 资产检查额外核验原生 qe-run-v2/verified_v2/eligibility，未在本地运行安装脚本或改共享环境。

## 当前检查点与未完成边界

`& $a06Python -X utf8 .context/A06/static_checks.py` exit0：17 个变更 Python 文件内存编译、git diff --check、15 条文档命令与原日志逐项对照通过；llmtest/pyproject/uv.lock 无差异。`.context/A06/source-freeze.json` 保存全部变更 Python SHA256，`.context/A06/static-checks.log` 保存结果；此静态检查不是额外 pytest，也没有写共享环境。

冻结前相关通过，下一步独立 k64 审查，收敛后只跑一次最终根回归。尚不能称交付完成：独立审查/finalroot、当前 SHA CI、主合并树验收、独立 wheel/安装/预发行及部署/Issue 跟踪待主串行接续。真实模型效果、Linux/其他 Python、UI 以及持久环境未在本任务验收；主根台账不由本任务修改。

10–20 分钟练习（待完成，掌握未评估）：执行前冻结一个计划，比较缺步骤、篡改 required、缺 grounding 和合法业务失败；说明自携 manifest 为什么不等于信任。更改模型/prompt 版本与更改同 ID 输入/rubric，解释不同 baseline 处理；导入两份同 ID 不同回答，定位冲突。用临时 schema1 库演示迁移失败回滚及匹配快照恢复；解释 Reported gate、complete、verification、release_eligible 和最终发布门禁的区别。不写收益百分比。

## 2026-10-28 独立审查与窄修（取代上述待首审检查点）

k64 对冻结 `5ffde0589d34460e606d2161c131949687f57cbc` 实际只读 diff 审查并核对17文件哈希，0新pytest/probe。发现0 Critical / 2 Important / 1 Minor，未发现已确认的发布误放行：R1 空消息异常被错误依赖 error 文本非空的 validator 拒绝，无法写失败报告；R2 scenario_ids=null/数字在局部转换外触发TypeError，且import既有ID另有裸get_run，生产部分路径500而非404；R3 app/env测试候选仍legacy，可能由无资格提前阻断而误绿。

只改三个生产文件：integrity 按最后step.status==error识别中断，仍严格要求error是str但允许空消息，完整性及execution assertion剥离使用同一状态，复算仍与现runner一致；storage 在tuple之前局部要求scenario_ids是数组；api 已有run预检共用scoped_record(allow_missing=True)，缺记录允许新建，损坏/越权404，取消先裸读，真正RuntimeError仍500。未改runner、未吞所有校验异常或回填旧proof。

R1 新增空消息 RuntimeError/TimeoutError×adapter/middle四守卫，均保留失败报告、不完整/无资格和伪造通过拒绝；原有带消息/中途/inconclusive保留。R2 null/数字IDs及未知evidence schema×GET validation/POST validation/同IDPOST import共9项，其中旧2项保留，另加3项真正get_run编程错误500守卫。R3先断言两份complete verified_v2在同plan下真实通过release，再只改候选app/env并匹配具体拒绝原因；self同样匹配原因，legacy独立拒绝守卫仍在。新文件现74项、隔离新增12项，共86新增；其中14项为本轮增加，不把原先通过项重新计作缺陷RED。

| batch | pytest exit / 实际结果 |
| --- | --- |
| review-red | 1；9 failed / 13 passed / 150 deselected / 2 warnings，8.14s；R1四个空消息、R2五个500路径真实失败，其余对照已绿 |
| review-green | 0；22 passed / 150 deselected / 2 warnings，6.58s |
| review-related-green | 0；329 passed / 2 warnings，42.06s；11文件，含完整性/作用域/quality/runner/gate/质量API与旧telemetry/auth API |

当前累计18顶层pytest/18进程，仍0 root；旧21文件387归首冻结源，不冒称修后重复全量。原始日志与源码检查点保留；修后哈希 `.context/A06/review-source-freeze.json`，静态结果 `review-static-checks.log`。原15条命令和新3条均可逐项与日志对照。恢复后的本地源/测试修改只限上述发现；版本、依赖、真实调用及发行边界保持。重新冻结交k64有限复审，关闭后才唯一finalroot，无需再请求授权。

## 唯一根回归实际失败与最终窄范围（更新以上待复审/root状态）

k64 对 `5b17bd1a267e3395687f5ae23165cfb1bc7e6b27` 有限复审，R1/R2/R3全部关闭、无剩余finding；只读diff并核对17Python哈希，无新增pytest/probe。确认该HEAD clean且17哈希匹配后执行唯一根回归，**实际不是全绿**：

| batch | pytest exit / 实际结果 |
| --- | --- |
| full-offline | 1；993 passed / 1 failed / 116 errors / 7 deselected / 2 warnings，92.99s，根0skip |
| root-fixture-green | 0；138 passed / 2 warnings，41.21s；仅两个夹具所在完整文件 |

1失败来自 `test_retention_clock.py::test_quality_clock_controls_import_links_and_validation`，116个setup errors来自 `test_telemetry_access.py::access`。实现者漏迁移这两处旧发布正向seed：仍用legacy summary作为release证据，且clock旧正向还将同一run用作baseline/candidate；严格契约正确拒绝，不能把这些结果算通过。此前普通相关选择未包括这两处；CI/UI脚本盘点不等于全仓夹具已全部迁移，此遗漏如实保留。

只改两个测试文件：telemetry_access 在seed执行前独立trusted_plan，dev服务器仅对v2使用此plan，seed以verified_payload导入并显式断言release_eligible；后续测试用legacy做授权写操作的行为保留。retention_clock独立plan、两个不同ID的verified-v2，复用同一report对象保证幂等内容身份；原注入时间、显式now优先级、到期拒绝、严格TTL边界、默认发布阈值及actor/角色/CSRF负例均未放宽。此后未改任何生产代码，也未新增测试计数，仍86新增。两文件138通过覆盖原117个失败/错误及该两文件其他守卫。

累计 **20条顶层pytest**，只有一次root；继承A03三种受控消费者子pytest，共 **23个pytest进程**。optional消费者预期skip是子进程探索结果，不计根通过或根0skip。根7排除为5UI+2Windows计划任务/持久watcher系统副作用集成；两警告为Starlette/AnyIO与LangGraph上游提示。没有重复本任务root；主明确最终当前head CI全回归绿后才可merge，随后主唯一mergedfull作为独立检查点。本地不得标localfullpassed。

原review源17哈希继续保持；两处额外测试文件加入最终19Python冻结哈希 `.context/A06/final-source-freeze.json`，静态结果 `final-static-checks.log` 对照全部20条命令。两文件夹具diff及138结果交k64有限确认，不重审无关源。最终CI/主合并树full、独立安装/Release、真实环境与用户练习仍待主，dev5/依赖/共享环境保持不变。