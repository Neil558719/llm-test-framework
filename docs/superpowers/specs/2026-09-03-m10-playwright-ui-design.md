# 里程碑 10：Playwright UI 自动化设计

## 目标

为 Reference Agent 提供可运行的最小 Web UI，并建立独立的 Playwright 验收层，覆盖登录、会话、发送消息、流式回复、业务结果、错误提示和转人工，同时保持测试平台与被测 Agent 分离。

## 边界

- UI 是零构建静态资源，由 FastAPI 提供；不引入 Node 前端工程。
- 登录是本地演示身份选择，不实现生产认证、权限系统或真实用户数据。
- `/api/chat` 保持现有响应协议；新增 `/api/chat/stream`、会话查询和演示登录接口。
- SSE 完成事件携带完整 `ResponseEnvelope`，页面显示 `trace_id`。
- Playwright 测试独立于 pytest API 测试，通过 `ui` 标记和可选依赖运行。

## 组件与数据流

`reference_agent/web/` 提供 HTML/CSS/JS；`reference_agent/app.py` 挂载静态页面及 UI 所需接口。页面登录后创建或恢复 session，发送消息到 SSE 接口，逐步渲染回答，完成后依据 `metadata` 渲染知识、工单、审批和转人工状态，并展示 trace ID。

`qe_platform/browser/` 保存页面对象和场景读取辅助；`tests/ui/` 只验证用户可见行为和网络协议。测试复用 `qe_platform/scenarios/assets/reference_agent/` 中的业务消息与 setup 数据。

## 验收标准

1. `GET /` 返回 UI，登录控件可选择 `U1001` 并进入会话界面。
2. 页面可以新建/恢复 session，发送知识问题并显示流式回答、引用和 trace ID。
3. 工单成功结果显示工单已创建；权限受限结果显示转人工；后端错误显示稳定错误提示。
4. `/api/chat/stream` 返回合法 SSE，完成事件包含 `ResponseEnvelope` 字段和 trace ID。
5. Playwright 页面对象覆盖登录、会话、发送、流式回复、业务结果、错误和转人工。
6. UI 测试默认不影响 `pytest tests/`；安装 UI 依赖后 `pytest -m ui` 可运行。

## 风险与取舍

演示登录不代表生产鉴权；SSE 流式接口当前基于同步 Agent 图执行，先保证协议和用户体验，真正 token 级模型流式能力留给后续模型接入。内存中的工单/审批状态仍是既有 Reference Agent 限制，不在本里程碑扩展持久化边界。
