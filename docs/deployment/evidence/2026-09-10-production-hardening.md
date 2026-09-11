# 2026-09-10 生产加固本地验收证据

本证据仅记录离线契约、静态配置和本机回归，不代表独立服务器或公网生产验收。测试使用临时 SQLite 文件、运行时生成的 RSA 签名密钥、伪 OIDC metadata 与临时 secret 文件；未调用真实 IdP、模型供应商或公共 URL。

| 检查 | 命令 | 2026-09-10 本机结果 |
| --- | --- | --- |
| 生产加固定向回归 | `python -m pytest tests/test_production_settings.py tests/test_auth_oidc.py tests/test_auth_api.py tests/test_storage_migrations.py tests/test_reference_agent_persistence.py tests/test_production_ops.py tests/test_health_readiness.py tests/test_production_deployment.py tests/test_production_hardening_contract.py tests/test_final_hardening_fixes.py tests/test_final_deploy_args.py --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-final-focused` | `74 passed, 49 warnings` |
| 完整非 UI 回归 | `python -m pytest --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-final-20260911` | `531 passed, 5 deselected, 261 warnings` |
| UI 回归 | `python -m pytest -m ui --no-report --no-history -p no:cacheprovider --basetemp C:\Temp\production-hardening-final-ui-20260911` | `5 passed, 531 deselected, 5 warnings` |
| Python 静态编译与空白检查 | `python -m compileall -q llmtest qe_platform reference_agent tests`；`git diff --check master...HEAD`；`git diff --check` | 均以退出码 0 完成 |
| Compose 静态配置 | 设置临时占位 OIDC、数据库路径、`*_FILE` 和 image digest 后运行 `docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet` | 以退出码 0 完成；未拉取或运行镜像 |
| 范围与兼容性检查 | `git diff --name-only master...HEAD`、`git diff master...HEAD -- ':!docs'`、`git diff master...HEAD -- llmtest` | 没有 FastGPT 命名文件或实现引用；`llmtest/` 无改动，`AppResponse` 兼容面未改动 |
| 迁移、备份、恢复、Smoke 与 rollback | `deploy/migrate.*`、`deploy/backup.*`、`deploy/restore.sh`、`deploy/smoke.*`、`deploy/rollback.ps1` | 未运行。`docker info` 无法连接 `//./pipe/dockerDesktopLinuxEngine`，因此没有可记录的实际 image digest、`schema_meta` 版本、备份 SHA-256、Smoke 或 rollback 报告 |
| 独立服务器 OIDC/HTTPS/公网 Smoke | 需要服务器、域名、正式 secret 与 IdP 配置 | 待服务器提供后执行 |

2026-09-11 最终修复波次补充了生产业务路由角色门禁、跨浏览器 OIDC 事务绑定、审批与草稿隐私迁移、会话数据库共享迁移运行时、深度 readiness、生产 Compose 参数一致性、模型密钥 `*_FILE`、生产浏览器 CSRF、操作指标和部署脚本回归。最终定向回归 `74 passed`，全量非 UI `531 passed`，UI `5 passed`；Docker 容器迁移/备份恢复/Smoke/rollback 仍未运行，因为本机 Docker Linux daemon 不可连接。报告、备份、secret 文件、OIDC token 和真实业务请求均不得提交。

## 交付生命周期状态

本地实现与回归已具备证据，但 GitHub Issue、push、Pull Request、Actions、独立代码审查、合并 `master`、合并后验证、预发布与服务器部署尚未执行。本分支因此不具备发布或生产就绪声明的条件。
