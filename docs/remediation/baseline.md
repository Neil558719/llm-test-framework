# P00 / A01 本地运行基线

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
