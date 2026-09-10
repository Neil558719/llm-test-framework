# 2026-09-10 生产加固本地验收证据

本证据记录离线契约和本机可执行验收，不代表独立服务器或公网生产验收。所有测试输入均为临时 SQLite 文件、运行时生成的 RSA 测试签名密钥、伪 OIDC metadata 与临时 secret 文件；没有调用真实 IdP、模型供应商或公共 URL。

| 检查 | 命令 | 当前结果 |
| --- | --- | --- |
| 生产加固端到端契约 | `python -m pytest tests/test_production_hardening_contract.py -q --no-report --no-history -p no:cacheprovider` | 2 passed（3 个上游弃用警告）；包含 OIDC Bearer/API 写保护、机器遥测 token、持久工单/审批、备份/恢复、就绪和指标脱敏 |
| 相关生产回归 | `python -m pytest tests/test_production_hardening_contract.py tests/test_auth_api.py tests/test_reference_agent_deployment_config.py tests/test_telemetry_api.py tests/test_production_deployment.py tests/test_deployment_assets.py tests/test_health_readiness.py -q --no-report --no-history -p no:cacheprovider` | 37 passed（11 个上游弃用警告） |
| 全量与 UI 回归 | `python -m pytest --no-report --no-history -p no:cacheprovider -q`；`python -m pytest -m ui --no-report --no-history -p no:cacheprovider -q` | 非 UI 499 项完成且无失败；UI 4 passed、499 deselected（3 个上游弃用警告） |
| M13–M17 离线契约 | 对应 `.github/workflows/loadtest.yml` 的测试集合 | 245 passed（21 个上游弃用警告） |
| Compose 静态配置 | `docker compose -f docker-compose.yml -f docker-compose.production.yml config --quiet`，使用临时 secret 文件与占位 OIDC 值 | 通过 |
| 迁移、备份、恢复和 Smoke | 见 `production-readiness-runbook.md` | 当前 Windows 主机 Docker Desktop Linux daemon 不可连接，未运行容器演练；待 Docker daemon 可用后执行 |
| 独立服务器 OIDC/HTTPS/公网 Smoke | 需要服务器、域名、正式 secret 与 IdP 配置 | 待服务器提供后执行 |

本任务修复两项可被契约捕获的集成风险：Bearer 认证的 API 写操作会正确跳过 Cookie CSRF 校验；Reference Agent 机器遥测发送器能够读取 Docker secret 文件。报告、备份和 secret 文件均不应提交。
