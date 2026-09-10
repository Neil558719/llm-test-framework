# 生产就绪运行手册

本手册用于把已验证的本机构建迁移到独立 Linux 服务器。每次操作都在受控窗口中执行，并将 JSON 报告、Compose 状态、镜像 digest、数据库 schema 版本和备份 SHA-256 归档到部署工单。不要把 Cookie、Bearer token、OIDC 返回内容、模型密钥或业务请求写入工单和版本库。

## 当前验收边界

2026-09-10 已完成离线生产加固契约、完整非 UI 回归、UI 回归、Python 静态编译、diff 空白检查和带临时占位值的 Compose 静态配置。Docker Desktop Linux daemon 当前不可连接，因此本机尚无容器启动、迁移、备份、恢复、Smoke、rollback、镜像 digest、`schema_meta` 版本或备份 SHA-256 的实际报告。GitHub Issue、push、Pull Request、Actions、独立审查、合并、Release 与服务器部署同样仍待执行；详细本地证据见 `docs/deployment/evidence/2026-09-10-production-hardening.md`。

## 前置条件

- 固定候选镜像和 registry digest，准备 `REFERENCE_AGENT_IMAGE` 与 `REFERENCE_AGENT_IMAGE_DIGEST`。
- 为 `auth_session_secret`、`qe_telemetry_hash_key`、`qe_telemetry_ingest_token`、`reference_agent_model_api_key` 各创建一个权限受限的 secret 文件；文件内容不进入 shell 历史或版本库。
- 配置 HTTPS OIDC issuer、audience、client ID、回调 URL、JWKS URL 和允许的回调地址。生产配置会因缺少任一项失败关闭。
- 准备 `/data` 的持久卷、部署报告目录和可恢复的备份存储。部署机必须有 Docker Compose v2。

## Windows 本机演练

在 PowerShell 中使用临时 secret 文件、生成的测试 OIDC 密钥和本地镜像。不要连接真实 IdP、模型或公网 URL。

```powershell
python -m pytest tests/test_production_hardening_contract.py -q --no-report --no-history -p no:cacheprovider
docker compose build
.\deploy\migrate.ps1 -ComposeFile docker-compose.yml -ReportPath reports/migrate.json
docker compose up -d --wait
.\deploy\smoke.ps1 -ReportPath reports/smoke.json
.\deploy\backup.ps1 -ReportPath reports/backup.json
docker compose ps
```

恢复演练使用刚生成的备份数据库及其相邻 manifest。恢复完成后重新 Smoke，并保留恢复报告。

```powershell
docker compose down
docker compose up -d --wait
.\deploy\restore.sh <backup-db> # 在 Git Bash/WSL 运行 Linux 恢复脚本
.\deploy\smoke.ps1 -ReportPath reports/smoke-after-restore.json
```

Windows 当前没有 PowerShell 恢复脚本；服务器恢复以 Linux 命令为准。若需要撤回镜像，使用已验证的候选 tag/digest：

```powershell
.\deploy\rollback.ps1 -ImageTag <verified-tag> -ImageDigest <verified-digest> -ReportPath reports/rollback.json
.\deploy\smoke.ps1 -ReportPath reports/smoke-after-rollback.json
```

## Linux 服务器部署

在服务器的受限部署账户中设置非敏感环境变量，并让 `*_FILE` 变量指向 secret 文件。通过两个 Compose 文件启动，生产覆盖层会固定 UID 10001、只读根文件系统、`/data` 卷、健康检查、资源限制和 restart policy。

```sh
export COMPOSE_FILE=docker-compose.yml
export REFERENCE_AGENT_IMAGE='<registry/repository>'
export REFERENCE_AGENT_IMAGE_DIGEST='<sha256 digest>'
export AUTH_SESSION_SECRET_FILE='<secret file path>'
export QE_TELEMETRY_HASH_KEY_FILE='<secret file path>'
export QE_TELEMETRY_INGEST_TOKEN_FILE='<secret file path>'
export REFERENCE_AGENT_MODEL_API_KEY_FILE='<secret file path>'
export OIDC_ISSUER='<https issuer>'
export OIDC_AUDIENCE='<audience>'
export OIDC_CLIENT_ID='<client id>'
export OIDC_REDIRECT_URI='<https callback>'
export OIDC_JWKS_URL='<https jwks>'
docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet
REPORT_PATH=reports/migrate.json deploy/migrate.sh
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --wait
REPORT_PATH=reports/smoke.json deploy/smoke.sh
REPORT_PATH=reports/backup.json BACKUP_DIR=deploy/backups deploy/backup.sh
```

Run the readiness endpoint after startup. It checks configuration and local repositories; liveness alone is insufficient.

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/api/health/ready
```

## Restore and rollback

Stop writes before any restore. `deploy/restore.sh` validates the backup SHA-256 manifest, integrity and schema versions before atomically replacing the database, then restarts the service. It returns nonzero if the target is not quiescent or the backup is incompatible.

```sh
REPORT_PATH=reports/restore.json deploy/restore.sh deploy/backups/<backup-db>
REPORT_PATH=reports/smoke-after-restore.json deploy/smoke.sh
```

To roll back, select a pre-verified compatible image/digest, start it with the production Compose overlay, then run readiness and Smoke. The data schema check remains mandatory; do not use rollback to bypass an incompatible restore.

## Evidence and server-dependent completion

Record the exact command, exit status, image digest, `schema_meta` versions, backup SHA-256, readiness response, Smoke report and rollback report. The local contract and drill do not prove public DNS, TLS termination, real IdP reachability, monitoring delivery or live provider behavior. Those checks remain pending until an independent server and approved production credentials are supplied.

Do not create a Release or mark this hardening work production-ready until the branch has an Issue, push, Pull Request, passing Actions, independent review, merge to `master`, merged-master verification, and the server drill evidence described above.
