# 云服务器迁移与回滚

## 迁移

1. 准备 Ubuntu LTS、Docker Engine、Compose 插件和最小权限部署用户。
2. 复制 `docker-compose.yml` 与生产 `.env`，不要复制开发密钥。
3. 拉取 Release 对应镜像，或在服务器构建同一 Git 标签。
4. 恢复 `reference_agent.db` 到命名卷 `/data`。
5. 配置 Caddy/Nginx、域名、HTTPS 和防火墙，仅公开 80/443。
6. `docker compose up -d --wait` 后运行 Smoke，并在部署 Issue 留证据。

## 回滚

部署前执行 `deploy/backup.ps1` 并记录当前镜像标签。异常时运行：

```powershell
.\deploy\rollback.ps1 -ImageTag <上一稳定版本>
.\deploy\smoke.ps1 -ReportPath reports/rollback-smoke.json
```

若数据库 Schema 不兼容，先停止服务，再从部署前备份恢复数据库。当前版本没有自动迁移，因此不得跨未知 Schema 直接覆盖数据。回滚只有在 Smoke 通过并记录镜像、数据库备份和时间后才算完成。
