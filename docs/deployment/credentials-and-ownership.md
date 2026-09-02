# 凭据与单人责任矩阵

## 凭据管理

| 凭据 | 当前状态 | 本地存放 | GitHub 存放 | 未来生产存放 |
| --- | --- | --- | --- | --- |
| `LLM_API_KEY` | 当前 Mock 模式不需要 | `.env` | Environment secret | 服务器只读环境文件 |
| `JUDGE_API_KEY` | 质量 Judge 启用时申请 | `.env` | Environment secret | 服务器只读环境文件 |
| `PRODUCTION_HOST` | 待服务器 | 不需要 | Environment secret | 不适用 |
| `PRODUCTION_SSH_USER` | 待服务器 | 不需要 | Environment secret | 最小权限部署用户 |
| `PRODUCTION_SSH_PRIVATE_KEY` | 待服务器 | 安全密钥库 | Environment secret | 仅公钥 |
| `APP_SECRET_KEY` | 正式鉴权实现时生成 | `.env` | Environment secret | 服务器只读环境文件 |
| `DIFY_API_KEY` | 里程碑 14 才启用 | `.env` | Environment secret | 服务器只读环境文件 |

仓库只保存 `.env.example` 空值模板。禁止在提交、Issue、PR、测试资产、报告和日志中出现真实密钥。测试与生产密钥必须分离并支持单独轮换。

## 单人责任模型

当前责任人均为项目所有者本人，但每次发布要按角色分别留下证据：

| 角色 | 责任 | 证据 |
| --- | --- | --- |
| 产品负责人 | 范围与验收标准 | Issue、规格、状态表 |
| 开发负责人 | TDD、实现、提交 | 分支、测试日志、提交 |
| 测试负责人 | 独立回归与 Smoke | pytest、JSON Smoke 报告 |
| 审查负责人 | 安全、兼容性、diff 检查 | PR review checklist |
| 发布负责人 | Release、版本与回滚批准 | Release、镜像标签、回滚记录 |
| 运维负责人 | 部署、备份、监控、问题响应 | 部署日志、备份、Issue |

同一人承担多角色时，不虚构人员隔离，以自动检查、固定 checklist 和分时复核降低自审风险。
