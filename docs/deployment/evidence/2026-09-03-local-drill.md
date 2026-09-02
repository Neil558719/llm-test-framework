# 2026-09-03 本机类生产演练证据

环境：Windows、Docker Desktop 29.2.1、Docker Compose；该证据不代表公网生产部署。

| 检查 | 结果 |
| --- | --- |
| `docker compose build reference-agent` | 成功，镜像 `llmtest-reference-agent:local` |
| `docker compose up -d --wait` | 容器达到 `healthy` |
| 初次 `deploy/smoke.ps1` | 4 项通过：健康、知识、工单、权限 |
| `deploy/backup.ps1` | SQLite 备份生成，12,288 bytes |
| 回滚目标 | `llmtest-reference-agent:drill-stable`；本次只验证标签切换和健康恢复，不代表不同应用版本兼容性已验证 |
| `deploy/rollback.ps1` | 等待容器恢复为 `healthy` |
| 回滚后 Smoke | 4 项通过 |
| 全量 pytest | `116 passed, 1 skipped, 83 warnings` |

跳过项是无本地 Embedding 模型；警告来自 LangGraph/Python 3.14 上游弃用路径，均为持续跟踪项。原始 Smoke JSON、数据库备份与容器日志属于本机运行产物，不进入 Git；PR 的 GitHub Actions 会上传 Smoke 和容器日志 artifact。不同版本镜像回滚和数据恢复兼容性仍是服务器迁移前的待补验证项。
