# Issue #63：备份与恢复的属主边界

2026-10-23 接续 PR #62。首次 helper-only root 修复为 `9ad1fbd`；随后 Container Readiness run `39448584021` / job `118716994756` 仍失败。

SQLite backup/restore 使用 mkstemp 创建私有文件。root helper 能写挂载后，host runner 读取备份计算 SHA256、上传 artifact 时出现 PermissionError/EACCES；恢复后原子替换的数据库同样可能不再归应用 UID 所有。

最终修复仅调整必要文件属主：backup.sh 传入调用者 `id -u` / `id -g`，helper 将备份和 manifest 交还调用者；restore.sh 从镜像内可信 `appuser` 账号解析应用 UID/GID，通过新增可选 keyword-only `restore_database(..., owner=None)` 将属主设置在 staging 校验之后、原子替换之前。不扩大文件访问权限，应用继续以 `10001:10001` 运行，保留完整性校验、恢复校验和清理逻辑。旧调用不传 owner 时行为保持兼容，schema 无变化。

独立审查发现初稿沿用旧文件属主不能修复已 root-owned 的数据库，且替换后 chown 失败可能已发布不可读文件。最终实现使用可信应用账号，并让 chown 失败保留原数据库。限定复审无剩余阻断项。

| 验证 | 实际结果 |
| --- | --- |
| 旧脚本运行新增3项行为回归 | 3 failed：缺少文件属主交还 |
| 审查新增 root-owned/缺失目标、发布前 chown 与 chown 失败负例 | 初稿4 failed, 1 passed, 8 deselected |
| 最终权限、ops、脚本、资产及所有 restore 调用相关回归 | 58 passed, 2 Windows 系统集成项 deselected, 2 上游警告 |
| 当前 SHA 的远程 Linux 容器演练 | 待推送和验证 |

本地最终命令：`python -m pytest -q tests/test_deployment_helper_permissions.py tests/test_production_ops.py tests/test_deploy_scripts.py tests/test_deployment_assets.py tests/test_final_hardening_fixes.py tests/test_production_hardening_contract.py -k 'not windows'`。

测试执行真实脚本 Python payload 及真实 SQLite 数据操作，仅替代 native Windows 无法执行的 chown/pwd 和模拟不同应用 UID；完整 shell/Docker 编排和真实文件访问控制仍须远程工作流验证。初轮审查负例曾因测试 SQLite 句柄未显式关闭触发 WinError，修正 closing 后重新确认失败来自预期缺陷，未删除旧日志。工作区保存 `a-permissions-red`、`a-review-red-confirmed`、`a-review-green-final` 日志及 JUnit XML。未操作用户既有 Docker 服务。

练习（待用户复现）：为什么把 helper 改成 root 只能解决写入，还可能导致 runner 读取或应用重启失败？画出 runner、helper、应用三个 UID 与备份目录、数据卷的访问关系，并解释为何只交还属主、不放宽到全员可读写。