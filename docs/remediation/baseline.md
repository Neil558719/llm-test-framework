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
