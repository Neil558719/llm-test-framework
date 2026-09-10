# 2026-09-10 生产加固本地验收证据

本证据仅记录离线契约、静态配置和本机回归，不代表独立服务器或公网生产验收。测试使用临时 SQLite 文件、运行时生成的 RSA 签名密钥、伪 OIDC metadata 与临时 secret 文件；未调用真实 IdP、模型供应商或公共 URL。

| 检查 | 命令 | 2026-09-10 本机结果 |
| --- | --- | --- |
| 生产加固定向回归 | `python -m pytest tests/test_production_settings.py tests/test_auth_oidc.py tests/test_auth_api.py tests/test_storage_migrations.py tests/test_reference_agent_persistence.py tests/test_production_ops.py tests/test_health_readiness.py tests/test_production_deployment.py tests/test_production_hardening_contract.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-task7-focused` | `54 passed, 13 warnings` |
| 完整非 UI 回归 | `python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-task7-full` | `499 passed, 4 deselected, 217 warnings` |
| UI 回归 | `python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-task7-ui` | `4 passed, 499 deselected, 3 warnings` |
| Python 静态编译与空白检查 | `python -m compileall -q llmtest qe_platform reference_agent tests`；`git diff --check master...HEAD`；`git diff --check` | 均以退出码 0 完成 |
| Compose 静态配置 | `docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet`，使用临时空 secret 文件、占位 OIDC 值和占位 image digest | 以退出码 0 完成；未拉取或运行镜像 |
| 范围与兼容性检查 | `git diff --name-only master...HEAD`、`git diff master...HEAD -- ':!docs'`、`git diff master...HEAD -- llmtest` | 没有 FastGPT 命名文件或实现引用；`llmtest/` 无改动，`AppResponse` 兼容面未改动 |
| 迁移、备份、恢复、Smoke 与 rollback | `deploy/migrate.*`、`deploy/backup.*`、`deploy/restore.sh`、`deploy/smoke.*`、`deploy/rollback.ps1` | 未运行。`docker info` 无法连接 `//./pipe/dockerDesktopLinuxEngine`，因此没有可记录的实际 image digest、`schema_meta` 版本、备份 SHA-256、Smoke 或 rollback 报告 |
| 独立服务器 OIDC/HTTPS/公网 Smoke | 需要服务器、域名、正式 secret 与 IdP 配置 | 待服务器提供后执行 |

本轮契约覆盖并修复两项集成风险：Bearer 认证的 API 写操作会跳过 Cookie CSRF 校验；Reference Agent 机器遥测发送器可以读取 Docker secret 文件。报告、备份、secret 文件、OIDC token 和真实业务请求均不得提交。

## 交付生命周期状态

本地实现与回归已具备证据，但 GitHub Issue、push、Pull Request、Actions、独立代码审查、合并 `master`、合并后验证、预发布与服务器部署尚未执行。本分支因此不具备发布或生产就绪声明的条件。
