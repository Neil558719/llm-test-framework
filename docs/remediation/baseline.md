# P00 / A01 本地运行基线

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
