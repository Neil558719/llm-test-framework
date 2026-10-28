# P00 / A01 本地运行基线

## A08 当前接续（Issue #80）

隔离codex/a08-async-budget，base4d5a2bc/dev7。原生async预算/适配器/runner/v1入口和可信报告本地收口，64新增、20顶层pytest/20进程、0root/0子pytest。历史528通过，后续6文件273通过；最后close自行取消真实RED1失败后，局部两行修复在3.13/3.9各6守卫通过。3.9原156通过/1失败仅该清理fixture窄修后单node1通过，不拼成新157批。20批错误、Windows时窗和真实缺陷均保留，见[A08证据](../evidence/A08/summary.md)。

20改动Python内存compile/3.9 AST、版本dev7、原106锁条目保留及4必要新增、offline110和diff检查通过。3.13为私有插件overlay只读借用既有依赖，3.9为完全私有frozen dev环境；无共享pip写入/真实服务/Docker。准备commit冻结交k64独审，关闭发现后唯一finalroot；主dev8/PR/CI/合并树/独立wheel/发行与部署另验，不把273当最后局部修复后的重跑。

A07依赖主已交付：PR79同head34CI成功，merge51ca47d与base同产品树，merged1177通过/7排除/2警告；独立wheel65通过/2仓库M13配置排除/5警告、14场景/3资源，dev7三附件回下载hash/tag/source一致、Issue78关闭。此处更新下方A07历史待交付记录，不计A08覆盖。真实provider/async Judge/IdP/HTTPS/持久部署、用户掌握仍未验收。

## A07 当前接续（Issue #78）

最终本地交接：9ac34293独立有限复审关闭R1、无剩余，唯一root1177通过/7排除/2警告/0skip、106.51秒；67新增/13顶层pytest+3消费者=16进程。7排除为5UI/2Windows系统副作用，两警告为原上游。最终仅docs尾注，17Python哈希不变；主继续dev7/当前head CI/合并树/安装Release与Issue，65安装契约+2仓库配置边界保持。下方历史失败、旧计数和审查阶段不覆盖。

首冻结096a8a81独审1Important（混合首内容/TTFT缺测误放行）；按主裁定仅summary/metrics/gates补适用已建立流覆盖完整性，观察p95不变。11新增至67，R1 RED8失败/3守卫通过，修后50窄相关通过/2警告；累计12顶层pytest、0root，待有限复审。旧379/97记录仅归初冻结，不称当前full；详见A07证据。

独占隔离树codex/a07-observability，base a8b3ac223575a05c9c6c08977848b119d6021288/dev6；不改版本/lockdeps/共享环境。实现响应/trace/场景真实单调耗时、HTTP/SSE有效契约、内容/建立状态、goodput/成功延迟/已建立分母及报告门禁接线，A06既有null importer不重复认领。56新增，10顶层pytest，相关379通过、最终配置/新增/报告窄集97通过；旧RED、夹具错误和相关7失败完整保留，见[A07证据](../evidence/A07/summary.md)。仅准备冻结独审，未root/push；独审关闭后唯一finalroot，主后续dev7/CI/合并/安装发行。

A06依赖接续（主提供）：PR77同head34成功，merge fe197042与base同产品树；合并1110通过/7排除/2警告98.41秒，独立wheel74完整性（5警告=3harness+2上游）+14场景/3资源通过；dev6三附件回下载验证、Issue76关闭，hash及缓存边界详见A07证据。历史A06本地root失败/138夹具迁移仍保留；不当A07验证。真实provider/IdP/HTTPS/持久部署、用户练习均未验收。

## A06 当前接续（Issue #76，2026-10-27）

交接尾注：k64已有限确认3135b468两夹具迁移无剩余、原17哈希未变及138日志；最终仅docs尾注提交，19Python冻结不变，不再pytest/root。主接管当前head CI/合并树full/安装发行，唯一root失败边界保持。

最终本地接续：独立有限复审5b17bd1无剩余；唯一root实际exit1/993通过/1失败/116errors/7排除/2警告/0skip/92.99秒。两处漏迁移的旧release正向seed（telemetry_access/retention_clock）仅测试夹具迁移可信v2、不同ID，原时间/TTL/actor/角色/CSRF/阈值保持，两个完整文件138通过/2警告/41.21秒；生产源17hash未变。20顶层pytest+3继承消费者=23进程，86新增，未重复root，不标localfullpassed。两测试diff待有限确认；主CI当前head全绿、合并后唯一mergedfull/独立安装Release另验。

2026-10-28接续：独审5ffde058发现2Important/1Minor，新增14后86项；真实RED9失败/13已绿，定向22通过，11相关文件329通过/2警告/42.06秒，累计18顶层pytest/18进程，0root。仅status中断识别、局部hydration数组校验及统一已有run作用域预检三生产文件窄修；空消息错误可写但不可绿、持久化未知proof三入口404、真正RuntimeError500，app/env用双verified-v2对照。重新冻结待有限复审；下方387/15命令仅归首冻结历史。

分支 codex/a06-report-integrity，base725a413/dev5，版本/锁/依赖/共享环境不变。当前21文件相关387通过/2上游警告；新增70完整性+2隔离守卫，共72项；15顶层pytest/15进程，无finalroot。初始旧入口9失败/3原守卫已绿；接口缺失、夹具/实现错误与旧断言迁移单列，完整命令见[A06证据](../evidence/A06/summary.md)。源码准备冻结给独立k64，收敛后唯一根回归；主CI/合并树/独立安装/发行/部署尚待接续，不把本地绿灯当交付完成。

先冻结独立ScenarioSpec计划，native/import/read核对步骤与quality并重算结论；自报manifest无外部信任只能只读。baseline/candidate不同ID、同应用/环境、完整verified_v2和同控制资产；SUT模型/prompt实验版本不强制相同。schema2保留旧payload/links/验证，不回填证明；readiness动态要求2，合成质量库备份恢复用expected_versions=2，旧reader需配套旧快照。Agent专用部署restore不误改。零真实Judge/provider/SDK/IdP、无Docker/pip/push或用户DB操作。

依赖交付由主报告：A05 merge b16aa0b、34CI、合并树1024通过/7排除/2警告、wheel114质量及14场景/3资源、dev5已发布并核验三附件/hash/tag，Issue73关闭。此处更新下方A05历史待交付状态，不计入A06测试数。真实效果、持久环境及用户掌握未评估，练习待完成；主整合时统一dev6。

## A05 当前接续（Issue #73）

隔离分支 `codex/a05-scenario-quality`，base `2356b1e2d1d80e2266b021e43fb098ce642b5ed4`；本任务版本保持dev4，不改pyproject/uv.lock/共享env，后续dev5由主统一。主最新依赖验收：A04b已合并 `55b22550`，PR74同head34项检查与同树全量910通过/7排除/2警告，独立wheel202鉴权隔离+14场景/3资源通过，dev4已发布并回下载hash/tag/三附件核验，Issue72关闭；不当作本任务覆盖或重复执行，真实IdP/HTTPS/持久部署未验收。

严格五指标/规范化阈值、显式evaluator、required状态聚合、最终回答/问题/sources、缺grounding不委托、callback结果校验、转义报告及程序gate接线已本地验证。纠正测试错误后57初始RED、12边界RED；旧契约冲突117通过/2失败后迁移，相关21文件310通过/2上游警告。新87项、累计7次顶层pytest，无全量；准确失败与命令见[A05证据](../evidence/A05/summary.md)。无真实provider/SDK/模型/Docker/pip/push，AppResponse/底层Judge量纲和A02 gold分母不改。代码冻结后先独立review再唯一finalroot；CI/合并/安装发行/部署与用户复现尚未完成。

下方A01及其他章节保留历史阶段记录。

A05审查接续：初稿源3345ea5/docsf6c42b1发现1Important自定义测量证据边界、1Minor测量前取model。新增27项，26真实RED+1合法空claims兼容通过；仅quality wrapper校验claims/ClaimVerdict/枚举/finite confidence/evidence并读本次测量后的Judge来源，合法[]仍inconclusive/None。定向27、相关6文件226通过/2警告，累计10顶层pytest，现114项；未重复原310/未root，源重新冻结待有限复审，版本依赖与内核不改。当前树不冒称旧310或全量通过。

A05最终接续：冻结源 `be21c8d6b916e3f9b6589db7b1b94df753befdaf` 有限复审无剩余项，随后唯一默认非UI根全量1024通过/7排除/2上游警告、0skip、69.91秒；7排除为5UI+2Windows系统副作用集成。累计11顶层pytest，加3继承消费者=14进程；子进程optional预期skip不冒充根覆盖。结果归属冻结源，之后仅docs提交，无源码/测试更改或重复测试；命令/日志见A05证据。版本仍dev4，主整合统一dev5并负责CI/合并/安装Release/部署，本地检查点不等于交付完成。

- 日期：2026-10-20；源 revision：`cd51114bdd38275c28e5dd527895bcdc65cf904b`。
- Issue：[A01 #61](https://github.com/Neil558719/llm-test-framework/issues/61)；隔离分支：`codex/a01-clock`。
- 环境：Windows x64，Python 3.13.15，uv 0.12.9；新建仓库专用虚拟环境，不复用其他仓库安装。
- 安装：设置 `UV_PROJECT_ENVIRONMENT=<workspace>/work/env-a` 后执行 `uv sync --locked --extra ci`，退出码 0；锁文件未改。
- 基线：`python -m pytest -q`，退出码 1，`18 failed, 516 passed, 5 deselected, 2 warnings in 42.09s`。
- 两项警告来自 Starlette/AnyIO 与 LangGraph 的上游弃用提示；UI 5 项由默认 `not ui` 标记排除，未冒充 UI 验收。
- 日志保存在工作区私有 `work/A01/`：`sync.log`、`baseline.log`、`red.log`、`promotion-counterexample.log`、`api-counterexample.log`、`green-related.log`、`final.log`、`final.xml`。公开仓库仅放本摘要及逐项脱敏结果，不放机主路径和运行时大日志。
- 旧失败集中于 2026-08/09 固定夹具在 2026-10-20 被生产 30 天 TTL 判过期：复核写入失败，离线导入失败，再级联影响关联、发布验证、CLI 与 API。
- Docker daemon 当前未运行，容器、部署与 UI 验收未执行；没有启动或改动用户服务。

## 依赖版本（锁定环境实测）

- `pytest==9.1.1`
- `fastapi==0.141.1`
- `httpx==0.28.1`
- `langgraph==0.6.11`
- `starlette==1.6.0`
- `anyio==4.15.1`
- `pytest-timeout==2.4.0`
- `pytest-rerunfailures==16.6.1`

## 修复后本地结果

`python -m pytest -q --junitxml=<private-log-dir>/final.xml`：退出码 0，`556 passed, 5 deselected, 2 warnings in 87.11s`。原 18 项失败逐项转为 PASS，新增 22 项验收；详见 [证据](../evidence/A01/summary.md)。仅本地完成，远程交付与部署待办。

## A04b 本地接续（Issue #72）

base7bc45e1，可信服务器subject/app和机器allowed apps，SQL先授权过滤后分页/聚合，同app完整关联，生产发布证据持久化创建时scope证明。初始RED30失败/1通过，边界5失败、历史scope3失败；最终相关228通过，根唯一全量890通过/7排除/2上游警告、0skip。9顶层pytest含一次路径错误no tests ran，另3继承消费者子pytest；没有重复全量。见[A04b](../evidence/A04b/summary.md)。版本暂dev3，主整合dev4；review/CI/合并/安装Release/部署及用户复现未完成。旧无scope证据生产404、dev兼容，不回填旧结论；JSON可选字段旧程序回退需配套快照。未扩A06。

## A04a 本地接续（Issue #70）

分支 `codex/a04a-auth-actor` 从 A02 合并 `f7c28b0` 开始，未依赖/改动 A03。生产业务读取补登录与任一现有角色；反馈/复核绑定认证 subject，保留写角色与 CSRF、development 兼容。版本暂保留 dev1。RED 校正后 29 failed/50 passed；相关 157 passed；唯一根全量 773 passed/1 failed/7 deselected/2 warnings、0 skipped。失败来自旧成功夹具伪造 reporter，迁移为服务端填充后定向128通过，再明确保留原冒用400负例后128通过；没有最终全量全绿运行，不重复全量。8次顶层pytest含一次路径错误 no tests ran，原日志完整保留。见 [A04a 证据与角色矩阵](../evidence/A04a/summary.md)。独立审查、PR/CI、合并、发行部署与用户复现仍待主流程；application 对象授权/过滤/机器 allowed application 留待 A04b。
