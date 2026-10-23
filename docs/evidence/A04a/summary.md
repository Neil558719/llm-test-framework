# A04a：生产业务读取与可信操作者

Issue [#70](https://github.com/Neil558719/llm-test-framework/issues/70)，分支 `codex/a04a-auth-actor`，起点 `f7c28b08360e6aa981ea43d677f67cba2065d31c`（A02 合并提交），开始时干净。本记录只证明工作树本地实现与离线验证；独立审查、Push/PR、当前 SHA CI、合并、合并后验证、Release 和部署由主流程接续。没有修改主 checkout、A02/A03 工作树、共享环境或依赖。

## 行为与角色矩阵

production 业务读取先认证，再检查是否具有任一现有有效角色。匿名、无效/撤销会话和关闭的 production runtime 返回 401；已认证但没有有效业务角色返回 403。读取不要求 CSRF。development 继续使用既有显式本地模式，不更改认证配置来让生产测试通过。

| 操作 | viewer | reviewer | releaser | admin |
| --- | --- | --- | --- | --- |
| 业务 GET | 允许 | 允许 | 允许 | 允许 |
| 指标 GET | 403 | 403 | 403 | 允许 |
| 反馈 POST | 允许 | 403 | 403 | 允许 |
| 复核 POST | 403 | 允许 | 403 | 允许 |
| 晋级、run 导入、关联、发布校验 POST | 403 | 403 | 允许 | 允许 |

写角色保持独立，admin 继续覆盖；Cookie 写入保留 CSRF，缺少/错误 token 返回 403。已验证 Bearer 写入沿用免 Cookie CSRF 的现有行为。机器 token 继续只用于既有机器写入，不能充当人类读取或反馈凭据。

production 反馈 `reporter_id`、复核 `reviewer_id` 从已认证 principal.subject 填入；省略可成功，显式同值兼容，不同值、null、非字符串返回 400。认证和写角色/CSRF 检查在解析 JSON、验证 actor 与仓储访问之前。返回与数据库仍只保存既有 HMAC 指纹，不增加身份明文。development 保留调用者自选 actor 且字段必填的旧行为。HTTP 边界负责可信身份，仓储/CLI 的显式 actor 接口不变。

## 路由审计

| 路由 | A04a 结果 |
| --- | --- |
| GET `/api/traces`、`/api/traces/{trace_id}` | 新增登录与任一有效角色检查，先于过滤参数解析及对象查询 |
| GET `/api/feedback` | 同上，保留必需查询过滤与分页约束 |
| GET `/api/reviews`、`/api/reviews/{review_id}` | 同上，详情中的晋级关联也在门禁之后读取 |
| GET `/api/promotions/{promotion_id}` | 同上，包含 YAML 读取 |
| GET `/api/quality/trends`、`/api/quality/links` | 同上，先门禁再读取 run/关联/聚合数据 |
| GET `/api/quality/release-validations/{validation_id}` | 同上，发布证据详情先门禁 |
| Reference GET `/api/model-profiles` | 补登录与有效角色检查；旧匿名 200 已在 RED 复现 |
| Reference GET `/api/sessions/{session_id}` | 原本要求登录，现在还要求有效角色；保留原有 subject 所有权检查 |
| 两个服务 GET `/api/metrics` | 保持 admin，补匿名/普通角色/admin 成对验证 |
| health/live/ready | 保持公开；ready 按实际依赖状态返回 200/503，不强制改绿 |
| `/auth/login`、`/auth/callback`、`/auth/session` | 保持协议入口；会话探测可匿名，伪造 callback 继续 401 |
| 静态页面、静态资源、框架 API 文档 | 保留登录页面和非业务文档入口 |
| POST `/api/traces` | 原机器 ingest token 校验保持 |
| POST feedback/review | 角色与 CSRF 保持，新增 subject 绑定 |
| POST promote、quality/offline-runs、quality/links、quality/release-validations | 保持既有角色/CSRF/机器路径；并无 actor 字段，未发明新字段 |

仓库没有独立 feedback 单条/trace 下反馈 GET、promotions 列表 GET、offline run 列表/详情 GET 或独立 evidence GET。run 数据经趋势、关联和发布验证查询，已审计相应入口。认证 routes 原本安装在 Reference Agent；未向 telemetry 增加新的登录协议端点。

**A04b 边界。** subject/application 授权关系、对象级访问控制、授权后查询过滤与分页、聚合前隔离、机器 ingest 的 allowed application 校验均未实现。当前有效角色仍可读取各 application 数据；不可把登录门禁当应用隔离已完成。

## 可复核测试证据

固定解释器为既有 `work/env-a/Scripts/python.exe`（Python 3.13）。运行器断言 `llmtest.__file__` 来自本工作树；使用 `--llm-mode=mock --no-report`，清除真实模型/应用/OIDC 环境配置，仅为子进程设置 development 默认值。新测试显式构造 production runtime，不依赖该默认值；使用固定 UTC 时钟、临时 SQLite、局部测试会话/签名与进程内 TestClient。没有安装依赖、真实 IdP、供应商 SDK 调用、真实模型/API、Docker、浏览器或外部服务。

原始命令、输出、退出码保留在 gitignored `.context/A04a/`，下表是 **8 次顶层 pytest 调用**的全部记录：

| 日志 | 范围 | 真实结果 |
| --- | --- | --- |
| `red.log` | 新 `test_telemetry_access.py` 初始 79 项 | 33 failed、46 passed；其中 Trace 列表夹具漏了必需过滤，5 个失败受此影响，不能全部算产品缺陷 |
| `red-corrected.log` | 只修 Trace 列表夹具为 `?trace_id=trace-1`，仍是旧生产代码 | **29 failed、50 passed**；9 个匿名业务读取旧 200、9 个无角色读取旧 200、6 个查找/参数错误先于认证、2 个省略 actor 被拒、2 个伪造 actor 被接受、1 个 Reference profiles 旧匿名 200 |
| `green-related.log` | 新测试 + auth_api、telemetry_api、telemetry_review_api、quality_loop_api | **97 passed、2 warnings** |
| `boundary-related.log` | 补充矩阵后相关集 | 参数路径误写 `test_auth_session.py`，退出 4，**no tests ran**；不算成功验证 |
| `boundary-related-corrected.log` | 新测试 + auth_api/auth_oidc、telemetry API/review、quality API、production settings/ops | **157 passed、2 warnings** |
| `full-offline.log` | 根目录默认非 UI 全量，仅显式排除两项 Windows 系统集成 | **1 failed、773 passed、7 deselected、2 warnings，0 skipped**；41.79 秒 |
| `production-contract-green.log` | hardening contract + 全部新测试 + auth_api | **128 passed、2 warnings**；迁移旧成功夹具后的定向复核 |
| `production-contract-final.log` | 同上，旧 hardening 用例再明确保留原 reviewer 冒用请求为 400 负例 | **128 passed、2 warnings**；最终代码/测试树的定向复核 |

全量唯一失败是原 `test_production_hardening_contract` 用 viewer 登录，却指定 reporter_id=reviewer 并要求 201，与新可信 actor 契约冲突。成功场景改为省略 actor，增加持久化响应指纹属于 viewer 的断言；生产代码未再改。定向 128 项全部通过，覆盖该测试后续备份/恢复与指标检查；没有重复全量，**不能称最终树已有一次全量全绿运行**。`test_auth_api` 的同类旧成功夹具也改为与认证 subject 相同；所有匿名、越权、CSRF 与伪造负例保留。

新文件最终 **116 项**（其中最初 79 项跑过 RED）；补充 admin actor、完整写角色/CSRF、机器 token、Bearer、无效/撤销/缺失会话和 Reference metrics 守卫没有逐项先红。7 deselected 为 5 UI、2 Windows 系统集成（计划任务注册/卸载与持久 watcher），不属于 skip。两个 warning 来自上游 Starlette/AnyIO 与 LangGraph。`static-checks.log` 记录全部六个变更 Python 文件 compileall 通过、三个版本位置仍为 dev1、`.context` 忽略规则通过、所有 GET 路由 AST 清单与 `git diff --check` 通过；这些静态检查不代替动态认证验证。

## 迁移与交付限制

生产读取客户端必须带现有 Cookie 会话或已验证 Bearer，并具备上述角色。反馈/审核客户端优先移除 actor 字段；保留字段时使用与认证 subject 完全一致的值，不做别名或空白规范化。Cookie 写入继续附 CSRF；ingest token 不能替代人类会话。开发脚本仍须显式提供 actor。数据库 schema 和历史指纹不变，不回写旧记录。

版本暂保留基线 `0.2.0a24.dev1`，待主流程与 A03 串行整合后统一版本。撤回代码提交可恢复旧 API 行为，但也恢复匿名读取/身份冒用漏洞；数据库无需迁移。真实 OIDC/Bearer 联调、Linux/其他 Python、UI、CI、发行安装与部署仍待对应环境；本地离线通过不等于生产验收。

## 用户复现练习（待完成，掌握未评估）

10–20 分钟：同一条 Trace 分别匿名、用无角色会话、用 viewer 读取，记录 401/403/200；用 viewer 写反馈，比较缺 CSRF、错误 CSRF、正确 CSRF，再比较 actor 省略/同值/伪造的结果和服务端指纹。用 reviewer 解释为何可读却不能写反馈，admin 为何可写；说明开发自选 actor 为什么不能照搬到生产。最后指出本次全量唯一失败为何应迁移成功夹具，以及为什么登录门禁尚不证明 application 隔离。