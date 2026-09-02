# 本机类生产部署演练

本方案是零预算的本机类生产演练，不等同于公网生产环境。目标是让同一镜像、Compose 配置、环境变量和数据备份流程可在未来复制到 Linux 云服务器。

## 目标环境

| 环境 | 当前目标 | 状态 |
| --- | --- | --- |
| 开发 | Windows 工作区与 Python 虚拟环境 | 已具备 |
| 类生产 | Windows + Docker Desktop + Docker Compose | 本交付验证 |
| CI | GitHub Actions Ubuntu runner | PR 自动验证 |
| 公网生产 | Ubuntu LTS、2 核 4 GB、Docker Compose | 待取得服务器 |

## 演练命令

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d --wait
.\deploy\smoke.ps1 -ReportPath reports/local-production-smoke.json
.\deploy\backup.ps1
docker compose down
```

Smoke 覆盖健康检查、知识问答、工单和权限申请，并输出 JSON 证据。`.env`、备份数据库和报告不应提交。

## 公网生产缺口

- 尚无独立服务器、域名、HTTPS、外部可用性监控和告警接收渠道。
- 尚未配置真实生产密钥；当前参考 Agent 离线 Mock 流程不需要模型密钥。
- V3 的脱敏 Trace、反馈、人工复核与线上离线闭环尚未实现。
