# 2026-09-03 本机类生产演练证据

环境：Windows、Docker Desktop 29.2.1、Docker Compose；该证据不代表公网生产部署。

| 检查 | 结果 |
| --- | --- |
| `docker compose build reference-agent` | 成功，镜像 `llmtest-reference-agent:local` |
| `docker compose up -d --wait` | 容器达到 `healthy` |
| 初次 `deploy/smoke.ps1` | 4 项通过：健康、知识、工单、权限 |
| `deploy/backup.ps1` | SQLite 备份生成，12,288 bytes |
| 回滚目标 | `llmtest-reference-agent:drill-stable`，镜像 ID `sha256:6486b2987246db4b264b71ec4e8a7fadc48d0ae516b9321184c9f824088a14b0` |
| `deploy/rollback.ps1` | 等待容器恢复为 `healthy` |
| 回滚后 Smoke | 4 项通过 |
| 全量 pytest | `116 passed, 1 skipped, 83 warnings` |

跳过项是无本地 Embedding 模型；警告来自 LangGraph/Python 3.14 上游弃用路径，均为持续跟踪项。原始 Smoke JSON、数据库备份与容器日志属于本机运行产物，不进入 Git；PR 的 GitHub Actions 会上传 `container-smoke-evidence` artifact 作为独立 CI 证据。
