# 生产就绪加固设计

日期：2026-09-10

## 目标

在不依赖独立服务器、真实身份提供商或正式供应商凭据的前提下，把当前本机类生产交付加固为可迁移的生产候选版本。服务器到位后，只需注入 OIDC、域名、密钥和部署参数，即可执行迁移、Smoke、回滚和问题追踪，不需要修改业务代码。

本阶段属于 M17 之后的生产就绪阶段，不新增原有 0～17 里程碑，也不改变 Reference Agent 与质量平台的职责边界。

## 已确认的决策

- 认证使用通用 OIDC/OAuth2，不绑定具体身份提供商。
- 浏览器使用 Authorization Code + PKCE，后端建立 HttpOnly、Secure、SameSite 会话 Cookie。
- API 支持经过校验的 Bearer access token；机器遥测继续使用现有 ingest token。
- 角色固定为 `viewer`、`reviewer`、`releaser`、`admin`；角色 claim 支持可配置的 `roles` 或 `groups`，未映射角色默认拒绝写操作。
- 本阶段继续使用 SQLite，补齐生产可靠性；保留仓储接口，PostgreSQL 作为后续替换实现。
- 敏感配置只来自环境变量或 Docker secrets 文件；密钥不写入代码、SQLite、报告、镜像层或日志。
- 生产加固拆成认证授权、数据可靠性、配置部署、生产验证四个可独立审查的交付单元。

## 范围与边界

### 包含

1. OIDC Discovery、JWKS 校验、PKCE 会话、Bearer API、角色映射、CSRF 和统一 401/403 行为。
2. Reference Agent 业务数据与质量平台 telemetry 数据的 SQLite Schema 版本、幂等迁移、WAL、外键、事务和启动检查。
3. 工单和审批从当前进程内状态迁移到 SQLite，使容器重建和进程重启可恢复。
4. 一致性备份、恢复前检查、恢复后完整性验证、迁移和回滚脚本。
5. 生产配置校验、Docker secrets、非 root 容器、只读代码层、持久化卷、健康/就绪检查、资源限制和重启策略。
6. Windows 与 Linux 参数一致的部署、Smoke、备份、恢复检查和回滚资产。
7. 不含用户原文和凭据的结构化日志、认证/数据库/迁移/质量门禁指标。
8. 本机集成验证、跨重启验证、备份恢复演练、部署证据和后续服务器迁移清单。

### 不包含

- 本阶段不创建云资源，不执行真实 IdP 联调，不要求正式模型或 Dify 凭据。
- 本阶段不实现 PostgreSQL 驱动；仓储边界和迁移文档必须为后续替换保留稳定接口。
- 不新增 FastGPT 依赖、适配器、部署、测试或 CI。
- 不把测试断言、趋势计算或发布门禁放入 Reference Agent 实现。
- 不把机器 ingest token 当作人工用户身份，也不把长期 access token 存入浏览器 localStorage。

## 设计

### 1. 认证与授权

新增 `qe_platform/auth/`，提供以下边界接口：

- `OidcSettings.from_environment()`：读取 issuer、audience、client_id、redirect_uri、JWKS URL、claim 名称、会话密钥和 cookie 配置；生产模式缺少必需项时抛出配置错误。
- `OidcVerifier.verify_access_token(token)`：从缓存 JWKS 取得签名密钥，校验签名算法、issuer、audience、过期时间和必要 subject；不记录 token 或上游正文。
- `RoleMapper.map_claims(claims)`：从配置的 `roles` 或 `groups` claim 映射到四个内部角色；没有映射结果时只授予匿名只读之外的拒绝结果，不隐式提升权限。
- `SessionStore`：使用独立的 `QE_AUTH_DATABASE`，只保存随机会话 ID、用户 subject、角色、过期时间和 CSRF token 的哈希；不保存原始 access token、refresh token、用户原文或 IdP 返回正文。
- FastAPI 依赖 `require_user()`、`require_role(role)` 和 `require_csrf()`；所有写操作明确声明需要的角色。

浏览器流程为 `/auth/login` → IdP → `/auth/callback` → 会话 Cookie；服务端保存并校验 state、nonce 和 PKCE verifier。注销使会话失效并清除 Cookie。人工 API 使用 `Authorization: Bearer`，机器遥测仍使用 `X-QE-Telemetry-Token`。Cookie 写操作要求 CSRF token，Bearer 请求不要求 CSRF。

### 2. 数据与迁移

Reference Agent、telemetry/quality 和 auth 会话数据库继续物理隔离。每个数据库新增版本表：

```sql
CREATE TABLE IF NOT EXISTS schema_meta (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
```

迁移由组件注册表按整数版本顺序执行，每个版本在单独事务中完成；重复启动不会重复写入。数据库版本高于当前代码时启动失败并提示回滚或升级代码。连接初始化统一设置 `PRAGMA foreign_keys=ON`、`journal_mode=WAL`、`synchronous=NORMAL`、`busy_timeout`，并保留显式事务边界。

业务状态表保存用户、资产、工单、审批和会话所需的最小脱敏字段；状态迁移必须保留既有幂等键。API 的 `AppResponse`、Reference Agent 业务结果和 M17 质量闭环 API 保持兼容。

### 3. 配置、部署与运维

配置分为公开运行参数、敏感参数和部署参数。生产配置校验覆盖 OIDC、会话、数据库、外部 URL、保留天数、遥测和运行模式。`.env.example` 只包含变量名、类型、默认安全值和说明；Docker secrets 从 `/run/secrets/<name>` 读取并覆盖同名环境变量，但日志只显示配置是否存在，不显示值。

Compose 生产覆盖配置使用固定镜像 tag 或 digest、非 root UID 10001、代码层只读、数据卷、健康检查、就绪检查、资源限制和 `restart: unless-stopped`。Linux 脚本与 PowerShell 脚本共享参数语义：`migrate`、`backup`、`restore-check`、`deploy`、`smoke`、`rollback`。部署记录保存镜像 digest、Schema 版本、备份文件摘要、Smoke 报告和回滚目标。

健康端点区分 liveness 与 readiness：进程存活不代表数据库可写；readiness 必须确认数据库版本、必需表、完整性和配置已通过。指标只输出计数、耗时和状态标签，不输出请求、回答、Cookie、Authorization header、token 或第三方错误正文。

### 4. 验证与交付

每个交付单元先写失败测试，再实现最小行为。最终验收矩阵为：

- Auth：JWT/JWKS、issuer/audience/过期、角色映射、401/403、PKCE state/nonce、Cookie 属性、CSRF、机器 token 兼容。
- Data：跨重启状态、迁移幂等、高版本拒绝、并发写入、WAL、备份恢复、完整性和 30 天保留策略。
- Config：生产缺配置快速失败、secret 文件、脱敏日志/报告和环境隔离。
- Deploy：Windows/Linux 参数一致、非 root、健康/就绪、固定镜像、回滚和 Smoke。
- Regression：M17 闭环、V1 API、UI、压测契约、M13 故障/SLO、M14 Dify、全量 pytest、compileall、Compose config 和 diff check。

本阶段完成后仍必须遵循仓库交付生命周期：Issue → 隔离分支 → 本地测试 → Push → PR → Actions → 独立审查 → 合并 master → 预发布 → 本机加固验证 → 更新证据。服务器到位后另建迁移验收 Issue，使用同一镜像 digest 执行 OIDC、HTTPS、备份恢复、跨重启、API/UI Smoke 和回滚验证。

## 风险和处理

- JWKS 不可用：使用短时缓存，但过期密钥不延长信任；readiness 报告身份提供商不可用。
- Cookie 会话存储不可用：拒绝新登录，不回退到演示账号。
- SQLite 锁竞争：使用 WAL、busy timeout 和事务重试边界；超过边界返回稳定 503 并记录计数。
- Schema 不兼容：高版本数据库拒绝启动，先备份再执行明确迁移，不自动覆盖。
- 配置泄露：启动检查、日志过滤、报告脱敏和 CI secret 扫描共同阻断。
- 服务器环境差异：部署包固定镜像 digest、Schema 版本和脚本参数，并提供迁移前检查清单。

## 完成定义

本阶段只有在四个交付单元各自验收、合并 master、Actions 和独立审查通过，且本机生产加固演练包含迁移、备份恢复、跨重启、Smoke、回滚证据后，才能标记为“生产就绪（待独立服务器迁移）”。真实服务器、正式 OIDC、域名 HTTPS 和公网试运行属于后续迁移验收，不提前宣称完成。
