# 面试素材账本

## A03：能力不支持与瞬时故障分开，覆盖缺失不能冒充通过

状态：Issue [#68](https://github.com/Neil558719/llm-test-framework/issues/68)，迁移版本 `0.2.0a24.dev2`；分支本地实现与离线验证通过，尚待独立审查/PR/CI/合并/Release/部署。用户掌握未评估，复现练习待完成。

**问题与证据。** 真实Anthropic原本返回确定性伪向量，能力探测吞全部异常永久缓存False，断言再无条件skip。初始RED44失败/2通过；首轮定向53通过；Mock报告来源补RED1失败/3通过/46排除；相关169通过/2警告；根全量一次708通过/7排除/2警告、0skip。5条顶层pytest命令，内含12个受控消费子进程（3种策略×4批），不把它们重复累加为根通过数。原始日志保留，详见 [A03证据](../evidence/A03/summary.md)。

**原理与取舍。** 明确unsupported可负缓存；认证、配置、429/网络等故障保留原异常并允许恢复，HTTP404/501本身也不能证明接口能力缺失。默认required缺能力非零；optional仅探索明确不支持，记录coverage=0与skip原因，不生成伪score。`required=True`强制单项必需，False不能降低默认required。当前无质量manifest接线模型，只提供未来必需评测入口，不扩A05。Anthropic可显式注入真实embedding_client，已知Mock拒绝；Mock指标和HTML仍明确标mock。

**兼容与版本。** AppResponse和A02规则保持；默认行为有意收紧。`EmbeddingUnavailableError`保留原导入路径并从包根公开；dev2三处version结构验证一致，锁依赖未变，不改共享Python。compileall和diff检查通过；metadata动作后未重跑全量。真实SDK/供应商、Linux/3.12/3.14、UI、安装包、CI及发布部署仍待独立验收。

**练习（待作答，10–20分钟）。** 模拟timeout后恢复、明确NotImplemented负缓存与401不skip；解释404配置失败和能力不支持的区别；对照required/optional/optional+required三种退出及覆盖记录；说明为什么Mock余弦1不代表真实embedding质量。

### 主流程依赖验收接续

主代理确认A02已合并 `f7c28b08360e6aa981ea43d677f67cba2065d31c`（与A03 base a764同树），合并后658通过/7排除/2警告；独立dev1安装包14/14场景、三静态资源及隔离A02有效性95通过且无skip。dev1预发布由主流程推进。A01 dev0已发布并验证回下载hash/tag，Issue61/63/65已关闭。下方A02/A01章节保留历史阶段记录；此处是主流程提供的接续证据，本子代理没有重复执行或标记用户掌握。

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
