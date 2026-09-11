# 本机类生产部署演练

本方案是零预算的本机类生产演练，不等同于公网生产环境。它验证与未来 Linux 服务器一致的迁移、在线备份、恢复、就绪探针和 Smoke 流程；完整服务器参数与步骤见 [生产就绪运行手册](production-readiness-runbook.md)。

## 目标环境

| 环境 | 当前目标 | 状态 |
| --- | --- | --- |
| 开发 | Windows 工作区与 Python 虚拟环境 | 已具备 |
| 类生产 | Windows + Docker Desktop + Docker Compose | 本次已完成构建、迁移、备份、恢复、跨重启和 rollback 演练 |
| CI | GitHub Actions Ubuntu runner | PR 自动验证 |
| 公网生产 | Ubuntu LTS、2 核 4 GB、Docker Compose | 待取得服务器 |

## 演练命令

```powershell
Copy-Item .env.example .env
docker compose build
.\deploy\migrate.ps1 -ComposeFiles docker-compose.yml -ReportPath reports/local-production-migrate.json
docker compose up -d --wait
.\deploy\smoke.ps1 -ReportPath reports/local-production-smoke.json
.\deploy\backup.ps1 -ComposeFiles docker-compose.yml -ReportPath reports/local-production-backup.json
docker compose down
```

若已准备好本地生成的 OIDC 测试配置、镜像 digest 和临时 secret 文件，可依次使用 `docker-compose.yml` 与 `docker-compose.production.yml` 的叠加配置完成更严格的演练。不得把真实 IdP、模型密钥或公网 URL 用作本机验收输入。Smoke 覆盖健康检查、知识问答、工单和权限申请，并输出 JSON 证据。`.env`、临时 secret 文件、备份数据库和报告不应提交。

## 公网生产缺口

- 尚无独立服务器、域名、HTTPS、外部可用性监控和告警接收渠道。
- 尚未配置真实生产密钥；当前参考 Agent 离线 Mock 流程不需要模型密钥。
- 生产 OIDC、遥测接收端、指标访问者和公网 Smoke 尚未接入真实基础设施。
