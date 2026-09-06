# Issue #41 SQLite 并发存储修复计划

目标：修复 Reference Agent 并发聊天请求共享 SQLite 连接引发的事务错误和会话丢失。
依据：Issue #41 与 `docs/AI应用全链路质量平台开发流程.md`。

设计：保留单连接以兼容 `:memory:`，用实例级线程锁串行化连接操作。
锁覆盖写入和提交/回滚整个事务、读取和关闭；不锁住模型调用或整个 API 请求。
不修改 AppResponse、压测错误指标、业务流程或数据库结构。

1. 在 `tests/test_reference_agent_storage_concurrency.py` 写真实 SQLite 的
   内存/文件并发读写、失败事务隔离以及 HTTP/SSE 会话回归测试。
2. 执行定向测试，记录旧实现的失败；生产代码位于 `reference_agent/storage.py`。
3. 最小修复：`threading.Lock` 保护连接，写入使用连接事务上下文以提交或回滚。
4. 运行定向测试、默认全量回归、V1 gate、UI 验收、compileall 和 diff check。
5. 使用独立 Docker 端口和卷执行 HTTP/SSE 并发压测，核对错误数、会话与数据库完整性。
6. 更新进度表；独立代码审查，提交、Push、PR、Actions，验收后合并 master。
7. 验证合并状态，发布修订预发布版本，部署本地服务并在 Issue #41 留存证据。

基线：master `dc4a789`；本轮前默认回归 `191 passed, 4 deselected`。
Windows 默认 pytest 临时目录清理存在权限问题，验证使用新建唯一 `--basetemp`，
并禁用 cacheprovider 避免旧缓存目录告警。
