# A04b：可信应用授权与完整归属链

Issue [#72](https://github.com/Neil558719/llm-test-framework/issues/72)，分支 `codex/a04b-application-scope`，干净起点 `7bc45e1b1987311ee3377f992c376804875f1d16`（A04a + 已发布A03 + dev3）。仅本地实现/验证完成，独立审查、Push/PR、当前SHA CI、合并后验证、安装/Release、部署与Issue跟踪由主流程接续；未写主checkout或A04a/A03工作树。

## 实现与审计

新增 `ApplicationAccessPolicy(mapping)`，提供 `allowed_applications(principal)`、`require_application(principal, application)`；由可信服务器经 `create_telemetry_app(..., access_policy=...)` 注入，或从 `QE_APPLICATION_ACCESS` JSON对象加载。生产缺配置/缺subject默认拒绝。机器token由 `TelemetrySettings.allowed_applications` 或 `QE_TELEMETRY_ALLOWED_APPLICATIONS` JSON数组限定，缺省拒绝。拒绝字符串逐字授权、空/非字符串/空白/控制标识、重复JSON key和 `*`；复制为不可变grants，请求不能自报权限。共享的标识校验/参数化SQL辅助在 `qe_platform/application_scope.py`，避免存储初始化反向导入auth/session的循环。

保留A04a认证/写角色/CSRF/actor。任一现有角色可读获授应用，admin没有隐式应用豁免，可明确授予多个应用。匿名401；无角色/无映射/显式非法application筛选403；外应用对象及关联ID404；两个都授权应用之间建立Link或baseline/candidate关系仍400。机器token不能读业务数据或写人类反馈。

| 链路 | 实施规则 |
| --- | --- |
| Trace/feedback/review列表 | SQL按允许应用过滤后LIMIT/OFFSET；保留必需过滤、页大小和排序 |
| Trace详情/反馈写、review详情/复核写、晋级/promotion | 通过已保存trace_id/feedback/review推导真实owner，不能靠body覆盖 |
| 机器Trace写入 | server allowed apps；事务内检查同ID历史owner，含过期行，未授权原owner404，换owner400 |
| run导入 | 声明app须获授，持久化ID内容不可变；事务内查历史真实owner，过期外app ID重用也404 |
| 趋势/links/业务计数 | online_rows/list_runs/list_links在SQL中先过滤再GROUP/聚合；links同时要求Trace/run同app；显式趋势app同步限定返回links |
| 创建Link/发布gate | promotion→Trace与run同app；baseline/candidate同app；低质量率/linked_count只采用同app链路 |
| 发布证据GET | 同时核对创建时scope证明、真实两个run归属及当前principal权限 |
| Reference profile/session、health/auth、metrics | 保留A04a和原session所有权；metrics仍admin全局技术指标，没有扩租户后台 |

无独立run列表/详情、feedback单条或evidence GET；相应数据走现有趋势/links/发布证据。没有独立总数端点；Trace反馈计数及趋势计数限定真实归属。仓储/CLI是受信任本地入口，新增范围参数None保持兼容，空集合明确零行；HTTP生产路径不会把缺授权变成None。

## 旧快照的必要收口

旧validation可能在创建时已把跨app关联计入linked_count/低质量检查，今天的links不能证明历史正确。主流程明确保守规则：新单应用scoped gate完成计算后，由服务端保存可选 `scope_application`、`scope_policy_version=1`，拒绝HTTP自报marker。生产读取旧无marker/未知marker/缺失或过期run/归属不一致统一404，admin也不豁免；development可读旧记录。不重算或改写旧快照冒充旧结论，需要时用当前production gate和新ID创建证据。旧cross Link保留，生产查询/计算排除；无归属旧数据不自动认领或授予默认app。

两个字段None时不输出，旧JSON形状不变，无表/schema迁移。旧程序严格hydration可能不接受新增字段，回退需配套数据库快照或已验证兼容读取器，不能删证明或关闭production鉴权。原CLI无范围validation不自动取得生产证据资格。未扩A06资产摘要/报告完整性或可比baseline。配置/迁移详见[应用范围授权指南](../../应用范围授权指南.md)。

## 验证

解释器为既有 `work/env-a/Scripts/python.exe`（Python3.13）。运行器 `.context/A04b/run_tests.py` 断言llmtest来自该树，清真实配置，仅子进程mock/development默认及PYTHONUTF8=1/UTF8输出；生产fixture显式构造production runtime。每批独立 `.context/A04b/<batch>-temp` 避免全局Temp竞态。固定UTC、临时SQLite、本地会话/测试签名、进程内TestClient，无真实IdP/API/SDK/provider/模型/Docker/UI/外部服务，无共享pip或环境改写。

全部原始命令/输出/退出码在gitignored `.context/A04b/`，共 **9次顶层pytest**：

| 日志 | 范围及真实结果 |
| --- | --- |
| red.log | 初始31项旧A04a行为：**30 failed、1 passed、2 warnings**；外app旧200、显式筛选/聚合/关联/机器越权、缺策略/接口；显式app-A Trace过滤分页原本通过 |
| green.log | 初始31项：**31 passed、2 warnings** |
| boundary-red.log | 畸形application/过期ID5项：**5 failed、31 deselected、2 warnings**；list/dict抛TypeError、null/number错误403、过期外app run ID错误400 |
| related-green.log | 误写不存在test_feedback_review_storage.py，**exit4、no tests ran**；不算通过，日志保留 |
| related-corrected.log | 36项新tests+A04a/auth/遥测API与存储/quality API存储引擎/生产契约/settings/health/TTL等16文件：**264 passed、2 warnings** |
| boundary-green.log | 补至63项+A04a/auth/生产契约/quality API引擎存储：**208 passed、2 warnings** |
| snapshot-red.log | 旧无marker同app/cross快照、新proof3项：**3 failed、63 deselected、2 warnings**；旧证据仍200/new proof缺失 |
| snapshot-related-green.log | 最终66项+A04a/auth/生产契约/quality模型API引擎存储报告CLI闭环：**228 passed、2 warnings** |
| full-offline.log | 根默认非UI唯一全量：**890 passed、7 deselected、2 warnings、0 skipped，60.87秒** |

根全量包含最终代码/测试。根回归继承A03的3个消费者子pytest（required失败、optional探索预期1skip、显式required失败，外层均成功断言），所以共 **12个pytest进程**。消费者禁止_get_client实际SDK，配置名real不代表provider调用；其探索skip不计入根0skip，不当覆盖成功。7排除=5UI+2Windows计划任务/持久watcher系统集成，两个warning来自Starlette/AnyIO与LangGraph。没有rerun挑绿。

初始31项跑过旧RED，另5边界和3快照分批先红，其余27守卫直接验证，不宣称66项逐项先红。合法生产fixture显式配置映射/机器范围，并新建Trace/run归属一致的样本；初始合法快照由真实scoped gate新建，旧无marker/cross样本单列负例，不改旧业务记录掩盖失败。A04a认证/角色/CSRF/actor伪造400负例保留。

`static-checks.log` 确认12个变更Python文件compileall通过，AST/TOML三处版本仍dev3、pyproject/uv.lock及依赖未改、`.context`已忽略、全部业务GET/POST路由清单和git diff --check通过。最终提交状态见交接记录。主整合后统一dev4。真实OIDC/HTTPS、Linux/其他Python、UI、当前SHA CI、安装/部署待对应条件，本地通过不代表交付完成。

## 用户复现（10–20分钟，待完成/掌握未评估）

同为viewer的alice/bob分别授予A/B，复现自身200、外对象404、显式外app筛选403、匿名401；admin先只授予A，再明确授予A/B，说明为何仍不能把A promotion关联B run。用页大小1与offset0/1/2解释过滤须先于分页，比较空集合/None。比较旧无scope快照与新server证明，解释为何不能拿当前links证明旧聚合；复现客户端自报marker400。最后区分本地测试、review、CI、发行和部署能证明什么。