# 面试素材账本

## A07：计时窗口、首内容与成功分母（Issue #78）

独审首冻结096a8a81发现1Important：混合complete-only缺测被有值流P95掩盖，显式content/TTFT可误绿；k64纯内存确认、主裁定适用已建立SSE流完整测量。新增11项至67，真实RED8失败/3原守卫通过（4误放行、3缺计数字段、1报告字段），summary/metrics/gates最小修后50窄相关通过/2上游警告。覆盖计数追加默认null，分布不补零，429/preconnect不计分母，未配置不新增阻断。累计12顶层pytest、仍无root，待有限复审；下方379/97为首冻结历史。

base a8b3ac2/dev6；响应/trace真实单调耗时、场景对话窗口排除Judge、无测量null；有效协议响应成功和业务期望分开。完成尝试吞吐保留，goodput同wall分母；首非空content、流建立和模型TTFT分开，Reference只能simulated。未知外部流保留合法network首内容别名并标来源；没有分母时null不能当成功。原位置字段、A06完整性/信任/baseline、scope/actor/TTL保持。

实际证据：初RED24失败/1通过，边界9失败；33定向通过，报告3失败/2已有守卫；相关356通过/7失败（6旧正向夹具及1合法展示回归）收口后379通过；数值2失败中1真实Overflow与1NaN夹具错误分开；M13两轮RED保留缺价表历史，显式Mock零价表后仅HTTP错误套流门禁失败，同0/1000ms限定协议后97窄集通过。56新增，10顶层pytest、无root。见[A07证据](../evidence/A07/summary.md)和[口径指南](../耗时与吞吐口径指南.md)。准备独审，不把本地/Mock称真实模型质量或已发行；复现练习待做、掌握未评估。

A06依赖由主验收：PR77全部34同head检查成功，merge fe197042与base同产品树；合并1110通过/7排除/2警告，wheel74完整性+14场景/3资源通过；dev6三附件回下载/hash/tag/source一致、Issue76关闭。依赖证据非A07覆盖；A06旧root失败/138迁移历史继续保留。真实provider/IdP/HTTPS/持久部署未验收，无Docker变动。

## A06：执行完整性与信任来源（Issue #76）

交接尾注：3135b468两处夹具有限复审无剩余，138窄回归/原17哈希已核对；最后仅docs提交且19Python不变，不重复root。主当前head CI和合并树全量/安装发行另验，不能称本地全量全绿。

最终本地边界更新：k64关闭R1/R2/R3后，5b17bd1唯一root实际993通过/1失败/116夹具错误/7排除/2警告/0skip，92.99秒，**没有本地全量全绿**。漏迁移telemetry_access/retention_clock两处legacy正向发布seed；仅改两测试文件为独立可信v2、不同run ID并复用幂等report，原角色/actor/CSRF、时间与TTL及默认阈值保持，两文件138通过/2警告/41.21秒。生产源未变；20顶层pytest+3继承消费者=23进程，仍86新增，不重跑root。主CI当前head全绿后才可merge，再主唯一mergedfull；见A06证据，历史387/329不冒充最终root结果。

2026-10-28最新：首冻结5ffde058独审发现2Important/1Minor，均按实际RED窄修；空消息异常报告、持久化proof三入口404及可信v2 app/env对照。9失败/13守卫已绿后22定向通过，11文件相关329通过/2警告/42.06秒；18顶层pytest/18进程，新增86项，仍无root，重新冻结待有限复审。仅3生产文件，无runner/阈值/TTL放宽；真正RuntimeError仍500，不回填旧信任。下方387/15命令为首冻结历史，准确记录见A06证据。

隔离分支 codex/a06-report-integrity，base725a413/dev5；当前21相关文件387通过/2警告，72新增测试，15顶层pytest/15进程，尚未独立审查或finalroot。初始旧入口9真实RED+3原有守卫通过；缺v2接口、后续实现/夹具错误、旧契约迁移和全部失败分别记录，见[A06证据](../evidence/A06/summary.md)。无默认Judge、真实SDK/模型/Docker/pip/push；主根台账不在本任务修改。

原理：先从独立选择的ScenarioSpec冻结不可变计划，再执行并核对实际步骤、确定性断言、必需质量和汇总。自携manifest不能自授信；没有外部expected_manifest/服务端resolver只能unverified只读。合法业务失败可complete但failed；初始化/中途error及inconclusive可写解释性报告但不可绿。相同ID改输入、工具/断言、rubric或阈值需新baseline；模型/prompt实验版本可变且记录。完整内容摘要防止相同ID不同执行擦成相同汇总；安全投影不存原问题/答案/工具参数，Mock来源可见且只证明离线接线。

迁移：quality_loop1→2保留旧payload/IDs/links/历史验证，不回填信任；readiness按仓库动态schema2，质量库恢复显式expected_versions=2。原Agent专用部署恢复范围不变；旧reader回退需配套迁移前快照。生产未知持久化proof404，HTTP自报proof400；异常只在数据解析范围处理。当前未具备发布完成证据，审查/finalroot、主CI/合并/安装发行及持久部署分开验收。

依赖最新交付：主已完成A05 merge b16aa0b、34CI、合并树1024通过、wheel114质量+14场景/3资源及dev5三附件回下载hash/tag核验，Issue73关闭；不计作本任务覆盖。下方A05段落保留其历史本地阶段。

10–20分钟练习待完成，掌握未评估：解释Reported gate/complete/verification/release_eligible差别；篡改步骤或required应失败，比较改模型版本与改rubric的baseline处理；用临时旧库演示迁移回滚/配套快照。不得以Mock离线通过声称真实质量或收益百分比。

## A05：执行完成、质量通过与证据来源（Issue #73）

base `2356b1e`（已复审A04b接续、dev4），A05最终冻结源 `be21c8d` 经有限复审无剩余项、唯一根全量1024通过/7排除/2上游警告、0skip，主流程交付待接续。主已合并A04b为 `55b22550`，PR74同head34项检查、全量910、wheel202鉴权隔离/14场景/3资源通过；dev4已发布并核验回下载hash/tag/三附件，Issue72关闭。本任务未重复A04b验证，真实IdP/HTTPS/持久部署未验收。见[A05证据](../evidence/A05/summary.md)和[场景质量指南](../场景质量评测指南.md)。用户练习待完成、掌握未评估。

问题：YAML任意quality只是未执行占位，场景passed忽略质量；已有run gate检查complete，不能说旧整轮门禁一直放行。严格五指标声明全部required；无显式Judge继续not_executed并阻断，有合法失败是执行完整但不通过；error/inconclusive/not_executed不完整。只评最终实际回答/问题/sources，执行中断不能借前轮响应证明质量；缺grounding由平台阻断相关检查，callback不能改声明集/required/threshold。

初稿证据：纠正测试错误后初始57真实RED；补12边界真实RED，非法测量先于tracker拒绝，JSON明确rubric。新87项中另18守卫未逐条先红；7条顶层pytest保留两次测试夹具错误与一次117通过/2旧契约失败，不伪装成功。初稿相关21文件310通过，当时无全量记录；无真实模型/SDK/IdP/Docker/环境改写。旧位置字段/AppResponse保持，底层Judge仍1..100、DSL0..1；accuracy是rubric而非gold，A02 mean_judge_score和金标分母保留。Mock来源明确，仅离线接线，不代表真实效果。

审查窄修阶段：0Critical/1Important/1Minor，分别为显式自定义client畸形claims/verdict被误计零幻觉、测量前读取冷默认/陈旧model。UNKNOWN与NaN分别真实负例，26失败/1合法空claims原本通过；仅新wrapper复用A02严格解析并核对ClaimVerdict/claim，本次测量后读取Judge来源，不改内核。新增27后共114项，定向27通过，6文件相关226通过/2警告；当时累计10顶层pytest，没有重复原310或全量，重新冻结待有限复审。合法空claims仍None/inconclusive，不得把缺证据变error或零幻觉通过。两客户端来源测试是本地fakefactory，无SDK/真实调用。

最终检查点：`be21c8d`有限复审关闭两项，无剩余；其冻结源唯一finalroot为1024通过/7排除/2警告、69.91秒、根0skip。累计11顶层pytest，加根继承3个消费者=14进程，optional子进程预期skip不计根覆盖。随后仅docs提交，源码/测试不再变，不重复pytest；Push/CI/合并/独立安装发行部署由主接续，不能把本地全绿称为已发布或真实效果。

10–20分钟练习（待完成）：同一声明比较无Judge、显式Mock、合法failed、缺context、空claims和中断执行；解释80/100映射0.8与hallucination max_rate方向。让callback删指标/改required/返NaN，追到报告error；通过Trace与转义expected/actual找到失败。说明为什么不能把所有用户问题拼成轨迹、为何今天的Mock通过不等于真实模型有效；分清本地、独立审查、CI、wheel、发行和部署各自证据。

## A03：能力不支持与瞬时故障分开，覆盖缺失不能冒充通过

状态：Issue [#68](https://github.com/Neil558719/llm-test-framework/issues/68)，迁移版本 `0.2.0a24.dev2`；分支本地实现与离线验证通过，尚待独立审查/PR/CI/合并/Release/部署。用户掌握未评估，复现练习待完成。

**问题与证据。** 真实Anthropic原本返回确定性伪向量，能力探测吞全部异常永久缓存False，断言再无条件skip。初始RED44失败/2通过；首轮定向53通过；Mock报告来源补RED1失败/3通过/46排除；相关169通过/2警告；根全量一次708通过/7排除/2警告、0skip。5条顶层pytest命令，内含12个受控消费子进程（3种策略×4批），不把它们重复累加为根通过数。原始日志保留，详见 [A03证据](../evidence/A03/summary.md)。

**原理与取舍。** 明确unsupported可负缓存；认证、配置、429/网络等故障保留原异常并允许恢复，HTTP404/501本身也不能证明接口能力缺失。默认required缺能力非零；optional仅探索明确不支持，记录coverage=0与skip原因，不生成伪score。`required=True`强制单项必需，False不能降低默认required。当前无质量manifest接线模型，只提供未来必需评测入口，不扩A05。Anthropic可显式注入真实embedding_client，已知Mock拒绝；Mock指标和HTML仍明确标mock。

**兼容与版本。** AppResponse和A02规则保持；默认行为有意收紧。`EmbeddingUnavailableError`保留原导入路径并从包根公开；dev2三处version结构验证一致，锁依赖未变，不改共享Python。compileall和diff检查通过；metadata动作后未重跑全量。真实SDK/供应商、Linux/3.12/3.14、UI、安装包、CI及发布部署仍待独立验收。

**练习（待作答，10–20分钟）。** 模拟timeout后恢复、明确NotImplemented负缓存与401不skip；解释404配置失败和能力不支持的区别；对照required/optional/optional+required三种退出及覆盖记录；说明为什么Mock余弦1不代表真实embedding质量。

### 主流程依赖验收接续

主代理确认A02已合并 `f7c28b08360e6aa981ea43d677f67cba2065d31c`（与A03 base a764同树），合并后658通过/7排除/2警告；独立dev1安装包14/14场景、三静态资源及隔离A02有效性95通过且无skip。[dev1预发布](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev1) 已完成，回下载wheel SHA256=`0d3096ec94b85b29c5e05a8cbae72fe8ed56715d3911dd6f2a0f235ee5a72d96`、tag指向核对一致，Issue64已关。A01 [dev0](https://github.com/Neil558719/llm-test-framework/releases/tag/v0.2.0a24.dev0) 已发布并验证回下载hash/tag，Issue61/63/65已关闭。下方A02/A01章节保留历史阶段记录；此处是主流程提供的接续证据，本子代理没有重复执行。真实环境与用户掌握仍未验证。

## A02：证据不足、质量分与金标准确率分开

状态：Issue [#64](https://github.com/Neil558719/llm-test-framework/issues/64)，本地实现与离线验证通过；独立审查/PR/CI/合并/Release/部署由主流程验收。用户掌握未评估，复现练习待完成。

**问题与证据。** 空 claims 原本给出 0% 幻觉率；`bool('false')` 为真；真实 Judge 越界分数会被钳位；helpfulness 均分被称为准确率。首批旧行为 `84 failed, 2 passed`，首轮定向 `96 passed`。补充边界 `3 failed, 6 passed, 86 deselected`，修复后相关 `119 passed, 2 warnings`，全量一次 `658 passed, 7 deselected, 2 warnings`（5 UI、2 Windows 系统集成排除，0 skip）。完整命令和迁移见 [A02 证据](../evidence/A02/summary.md)。并非每项测试逐条先红，合法行为兼容守卫原本通过。

**原理与取舍。** 率值需要有效分母；证据不足不代表业务必错，也不能证明质量通过。`inconclusive` 抛明确异常阻断必需断言；合法非事实回复须调用方显式策略标为 `not_applicable`，不混入分母。Judge 输出严格校验布尔、有限范围数字、枚举与语义结论一致性，不通过字符串转换、钳位或 embedding 回退掩盖错误。均分表示 rubric 质量，只有明确金标布尔判定才能生成正确率分母。

**兼容与迁移。** 行为迁移版本为 `0.2.0a24.dev1`，区别于 A01 的 `0.2.0a24.dev0`；本项目 pyproject、uv.lock 节点及 `llmtest.__version__` 三处同步，依赖版本保持。`AppResponse(answer, sources)` 和已有事实计算保持；率值改为可空，旧 accuracy 均分含义 deprecated，改读 `mean_judge_score`，准确率只读显式金标。history schema v2 保留旧记录并在 Judge 列解释旧 accuracy。A03 embedding、A04 权限、A05 YAML 连接未扩展。

**独立审查补充。** Reviewer 发现 Judge 图表副标题遗留“聚合为准确率”，已统一为 Judge 均分，既有 HTML 契约加强后先 `1 failed/94 deselected`，修复后 HTML/历史窄验证 `2 passed/93 deselected`。累计7次pytest，原全量结果归属 `51237ff`，文案修复未重复全量；其余审查和发布仍待主流程。

**独立迁移版本验证。** A02 定为 `0.2.0a24.dev1`，TOML 结构比较证明仅本项目版本改变，依赖未升级；`uv sync --locked --offline --dry-run` 退出0，安装计划可解。后续按授权同步源码版本常量，AST/TOML 窄验证确认三处 version 一致且源码仅常量改变。未实际安装或修改共享解释器，不把 dry-run 当 wheel/安装验收；pytest仍7次，未重复全量。

**练习（待作答，10–20 分钟）。** 离线重现空 claims、字符串 false、NaN 三种输入，解释 inconclusive/error/not_applicable 的区别；证明不适用不增加分母；展示 helpfulness 90% 与三条金标真/假/真得到 2/3 正确率的区别。说清本地、独立审查、CI、合并与发布各自证明什么。

## A01：固定日期夹具与保留期时钟分离

状态：本地修复与验证；PR/CI/合并/发布/部署尚未完成。Issue [#61](https://github.com/Neil558719/llm-test-framework/issues/61)。用户是否已理解或掌握：未评估。

**问题与证据。** 2026-10-20 在源 `cd51114b` 的专用新环境复现 `18 failed, 516 passed`。固定的 8/9 月数据被真实当前日期判过期；测试过去通过不能证明未来日期也通过。问题不是 TTL 太短，生产到期规则仍需生效。

**原理。** 仓储注入 `Clock = Callable[[], datetime]`，默认返回 UTC aware 的 `utc_now`。`now is None` 才读 clock；显式 now 优先。复核与晋级一次操作解析一个时间，用于资格检查与写入时间戳。API 不再传墙上时间覆盖仓储；质量引擎用仓储时间产生 validation 时间戳；CLI 在进程内 main 注入仓储 factory。

**负例红绿。** 原实现新增验收 `13 failed`（无 clock 参数）；撤掉晋级过期保护时，首次晋级与幂等重放两个负例 `2 failed`；恢复 API 的真实时间覆盖时，读 API 负例 `1 failed`。恢复修复后相关回归 `81 passed`，最终完整回归 `556 passed, 5 deselected, 2 warnings`，原 18 项失败全部转绿。测试与脱敏逐项结果见 `../evidence/A01/summary.md`。

**边界与取舍。** 30 天窗口仍按 `timestamp > now - 30 days` 读取，等于 cutoff 就过期。覆盖差 1 微秒、等于、超出、跨月、2024 闰日；共享 wall-clock provider 模拟 2026-09-01、2026-10-20、2028-02-29 时，固定应用时间夹具给出相同结论。UTC 不合法的 clock 返回值拒绝。到期后的晋级幂等重放也拒绝，这是一处有意的行为修正。没有改 TTL、删负例、放宽门禁或新增任意时钟环境变量。

**兼容。** 构造函数只新增可选 keyword-only clock；已有调用继续默认真实 UTC。新增写接口 now 为可选 keyword-only。数据库 schema、迁移版本、持久化 payload 无变化；无数据迁移和历史删除。撤销本修复提交即可回退。

**练习（尚未作答）。** 用三分钟解释：为什么把日期改成“今天”或增大 TTL 会掩盖问题？画出显式 now、注入 clock、默认 utc_now 的优先关系；说明为什么截止点采用严格大于；写出首次晋级和幂等重放过期的负例；说明本地绿灯与完成发布的区别。

## A-container：非 root 应用与备份 helper 的权限边界

状态：PR #62 的远程 Container Readiness 首次运行发现独立阻断；修复已在同一分支本地验证，Issue [#63](https://github.com/Neil558719/llm-test-framework/issues/63)；远程复跑待执行。用户是否已理解或掌握：未评估。

**触发与证据。** Actions run 39444075058/job 118701218642 在 `deploy/backup.sh` 的 SQLite 在线备份阶段报 `PermissionError: [Errno 13] Permission denied`，临时文件路径为挂载的 `/backup/...db.m_*.tmp`。应用服务在 `docker-compose.yml` 中保持 `user: "10001:10001"`，helper 继承该用户，无法写入 runner 的挂载目录。

**修复与取舍。** 仅给短生命周期的备份/恢复 helper 增加 `docker compose run --user "0:0"`；应用容器仍以 10001:10001 运行，保留只读 immutable 完整性检查、恢复校验和清理 trap。没有放宽业务门禁或改变数据库 schema。聚焦守卫旧脚本先失败，修复后 `3 passed, 14 deselected`。

**面试表达。** “容器服务必须非 root，但迁移 helper 需要向宿主挂载目录写临时 SQLite 文件。我先读完整堆栈确认失败在 helper 写入边界，再用最小的 helper-only 用户覆盖修复，避免把应用改回 root。”

**练习（尚未作答）。** 解释为什么修改 compose 的应用 `user` 是更大风险；指出 backup helper 的写入挂载与 integrity checker 的只读挂载差异；说出 CI 远程复跑通过前为什么只能说“本地修复”。

### 2026-10-23 补充：root helper 产物的交接

首轮 root helper 修复后的远程 run `39448584021` 仍因 host runner 无法读取私有 root-owned 备份失败，artifact 上传也 EACCES。根因是 mkstemp 的私有权限与运行身份跨边界，而非 SQLite 备份内容错误。最终补充修复将备份及 manifest 交还调用脚本的 host UID/GID，从镜像可信 appuser 解析应用 UID/GID，在恢复 staging 校验后、原子替换前设置属主，保持应用非 root 与私有文件模式。

新增3项回归先在旧脚本 `3 failed`；独立审查又发现旧 root-owned 目标与替换后 chown 失败两种边界，补负例初稿 `4 failed, 1 passed, 8 deselected`。最终相关回归 `58 passed, 2 deselected, 2 warnings`；限定复审无剩余阻断项。测试运行真实 SQLite/payload；Windows 仅替代 chown/pwd 边界，真实 Linux 容器演练待验证。完整证据见 `../evidence/A01/container-ownership.md`。当前 SHA CI、合并、Release 与部署仍单独记录。

**取舍与练习（待作答）。** 仅能写成功不等于能完成交付；按 runner→helper→应用三种身份逐一验证文件读取和替换。说明为什么把备份 chmod 成全员可读写会增加风险，以及原子替换为什么可能改变文件属主。用户掌握未评估。

### 恢复快照的只读检查边界

`762da56` 的远程容器演练已越过属主错误，但在停写恢复文件的只读挂载检查中触发SQLite unable to open database file。普通连接会因WAL模式依赖sidecar；改用与备份一致的immutable只读URI检查已关闭恢复主文件，保留marker正反断言。新增2项旧payload失败，最终相关60通过/2系统项排除/2警告，限定复审无阻断。当前提交真实Linux CI仍单独验收，不把受控挂载模拟当环境通过。

练习（待完成）：说明SQLite主文件、WAL、SHM分别承担什么；为什么immutable适合这里的恢复快照，却不能用于需要读取最新活动WAL的查询？不要用“只读就绝对没有写操作”概括普通SQLite连接。

### 2026-10-23：源码绿灯与安装包可用性

A01 PR #62 已合并为 `3bfc43a`，当前代码树与 CI 全绿的 `4d8ff42` 相同；合并后显式 Mock 回归 563 通过、7 排除、2 上游警告。发行前把 wheel 安装进独立环境时，14 个业务场景全部在应用启动处失败：setuptools 没有包含 `reference_agent/web`，源码和 editable 环境掩盖了资源缺失。Issue #65 独立修复只补 package-data，并将同样的非 editable 安装检查加入 CI。

新检查先在旧 wheel 上真实失败，再在修复 wheel 上验证三个静态路由字节一致、14/14 Mock 场景通过。见 `../evidence/A01/installed-wheel.md`。取舍是检查用户实际安装的包及其内置场景，而不是只检查源文件存在；不会把离线安装验证等同真实模型效果或持久部署。Release 与 CI 尚待主流程验收。

练习（未完成，掌握未评估）：解释 editable install 为什么会漏检 package-data；从源码目录外导入 wheel，指出 `__file__` 应来自哪里；删掉一个已打包静态资源后说明哪个检查应失败。可讲的工程故事是用独立消费者验证抓到源码测试覆盖不到的交付缺陷，未测量收益百分比。

独立审查又抓到验证器自己的边界错误：checkout内`.venv`也在源码根下面，不能只用“不是源码根的后代”判断安装来源。已复现旧验证器错误拒绝，改查解释器自己的site-packages目录；同CI布局14/14通过。受控少一场景实验原本13/13也绿，现用完整14个ID与数量契约拒绝部分资产。练习补充（待完成）：说明“没测到失败”与“承诺的全部场景都执行了”为什么不同。

## A04b：应用归属、查询隔离与历史证据（Issue #72）

本地实现/验证完成，独立review及后续交付由主流程；用户练习待完成，掌握未评估。见[A04b证据](../evidence/A04b/summary.md)和[应用授权指南](../应用范围授权指南.md)。

根因：登录/角色不保证对象属于可访问的应用，application筛选不是权限；先分页再过滤会泄露/打乱授权结果。服务器维护subject→app映射，admin无隐式豁免；反馈→审核→晋级从Trace推导owner，run/关联/发布gate也核对同app。SQL在LIMIT/GROUP之前过滤；机器token有独立allowed apps，过期ID也不能换owner。None的本地兼容通道与空集合零授权明确区分。

进一步发现：旧发布快照的计数可能已混入跨app数据，当前links不证明历史。选择新gate完成单app计算后由server持久化scope_application/version，HTTP不能自证；旧无证明生产404，dev保留，不能重算旧快照冒充旧结果。两可选JSON字段None不输出，无表迁移；回退旧严格读取器要配套快照，不能删标记或关闭鉴权。没有扩A06完整性方案。

证据：初始RED30失败/1通过；畸形app/过期ID RED5失败；历史scope RED3失败。审查前相关228通过，根默认非UI唯一全量890通过/7排除/2上游警告、0skip，归属 `e00c361`。原9顶层pytest含一次错误路径no tests ran，另继承3消费者子pytest；本轮审查修复新增2次，累计11顶层/14进程。探索预期skip不当根覆盖成功。原66项新测试分批验证，其余27守卫未逐项先红。无真实IdP/provider/模型/Docker/UI、部署或收益百分比。

独立审查Minor：持久化proof类型错误在hydration阶段先失败，GET原400、POST复用ID原500，未满足保守404契约。14个真实持久化GET/POST负例先红，6个HTTP自报400/程序异常500守卫原本通过；修复仅在两处持久化读取捕获ValueError/TypeError/KeyError，生产404，development及意外RuntimeError原行为保留，storage/models未动。新增20项后隔离测试86项，相关248通过/2上游警告，详见证据中的准确命令及review-proof日志。没有重复全量，890通过不冒充修复后全量；独立复审、合并树全量和后续交付由主流程接续，A05暂停。

10–20分钟练习（待完成）：同角色A/B身份复现200/404，显式外app403、匿名401；admin只给A和给A/B作对比，仍拒绝A promotion→B run。页大小1看offset0/1/2，解释SQL先过滤的重要性；说明actor绑定与app授权、空集合与None、当前关系与历史scope证明的差异。指出从本地通过到发行部署还缺哪些证据。

## A04a：读取门禁与可信操作者（Issue #70）

状态：本地实现与定向验证完成，主流程尚待独立审查及交付；用户复现待完成，掌握未评估。证据见 [A04a](../evidence/A04a/summary.md)。

问题与原因：写接口已有登录/角色/CSRF，但读取遗漏门禁，且客户端传来的 reporter_id/reviewer_id 被当作真实身份。角色授权回答“允许做什么”，subject 绑定回答“这次是谁做的”，两者都需在访问数据前执行。新增只读 helper 允许四个现有角色；写角色独立、admin 覆盖及 Cookie CSRF 保持。生产 actor 省略由服务端填，显式不同值 400；开发保留本地旧行为。对象的 application 授权和查询隔离是 A04b，未实现。

验证与取舍：修正夹具后旧代码 29 failed/50 passed，相关 157 passed。唯一根全量 773 passed/1 failed/7 deselected/2 warnings，失败是旧成功夹具跨 subject 指定 actor；改为省略并断言认证身份指纹后定向 128 passed，再将原 reviewer 冒用请求保留为400负例后同一窄集128通过。未重复全量，不能说最终树全量全绿。8 次顶层 pytest 含一次不存在测试路径导致 no tests ran；不把它算通过。新测试共116项，补充守卫没有逐项 RED。没有真实 IdP/模型、UI、部署或效益百分比证据。

复现练习（10–20 分钟，待完成）：比较匿名/无角色/viewer 的 401/403/200；比较缺 CSRF、错误 CSRF 与正确 CSRF；比较省略/同值/伪造 actor 的生产结果和 HMAC 指纹。解释 reviewer 为什么可读却不能写反馈，说明登录/CSRF/可信身份/application 授权分别保护什么。复述一次全量发现旧契约冲突后为何只需定向验证且应保留原失败记录。

主流程补充：`5d2cfe0` 独立审查无剩余项；spy 仓储确认匿名/无角色等拒绝路径在访问数据前结束，伪 actor 不产生存储副作用，Cookie/Bearer/CSRF 和独立写角色保留。已整合 A03 master `6993aa6` 并将项目/lock/runtime统一dev3，依赖不变；整合后的CI、合并、发行另行验收，不把旧根失败隐藏或把A03全绿算A04a全绿。用户掌握仍未评估。

2026-10-24主流程实际交付检查点：A04a PR #71最终7bc45e1的34项同head检查通过，合并0cdc713同树，合并根824通过/7排除/2警告；独立wheel116鉴权契约、14场景与三资源通过。`v0.2.0a24.dev3`已发布并回下载hash/tag/三附件核验，Issue #70关闭。真实IdP/HTTPS/持久部署仍未验收，用户练习仍未完成。

A04b `3b68332`独立窄复审关闭畸形持久化proof Minor，无剩余Critical/Important/Minor；实际RED14失败/6已有守卫通过，修复相关248通过。初稿890不冒充修复后全量；主无冲突整合master0cdc713，版本统一dev4且依赖不变，当前SHA CI/合并后验证/安装发行将分别登记。练习补充（待完成）：说明为什么不可信旧schema应404、HTTP自报字段仍400、运行异常仍500，为什么仅捕获读取范围的数据解析错误。
