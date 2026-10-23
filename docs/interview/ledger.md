# 面试素材账本

## A01：固定日期夹具与保留期时钟分离

状态：本地修复与验证；PR/CI/合并/发布/部署尚未完成。Issue [#61](https://github.com/Neil558719/llm-test-framework/issues/61)。用户是否已理解或掌握：未评估。

**问题与证据。** 2026-10-20 在源 `cd51114b` 的专用新环境复现 `18 failed, 516 passed`。固定的 8/9 月数据被真实当前日期判过期；测试过去通过不能证明未来日期也通过。问题不是 TTL 太短，生产到期规则仍需生效。

**原理。** 仓储注入 `Clock = Callable[[], datetime]`，默认返回 UTC aware 的 `utc_now`。`now is None` 才读 clock；显式 now 优先。复核与晋级一次操作解析一个时间，用于资格检查与写入时间戳。API 不再传墙上时间覆盖仓储；质量引擎用仓储时间产生 validation 时间戳；CLI 在进程内 main 注入仓储 factory。

**负例红绿。** 原实现新增验收 `13 failed`（无 clock 参数）；撤掉晋级过期保护时，首次晋级与幂等重放两个负例 `2 failed`；恢复 API 的真实时间覆盖时，读 API 负例 `1 failed`。恢复修复后相关回归 `81 passed`，最终完整回归 `556 passed, 5 deselected, 2 warnings`，原 18 项失败全部转绿。测试与脱敏逐项结果见 `../evidence/A01/summary.md`。

**边界与取舍。** 30 天窗口仍按 `timestamp > now - 30 days` 读取，等于 cutoff 就过期。覆盖差 1 微秒、等于、超出、跨月、2024 闰日；共享 wall-clock provider 模拟 2026-09-01、2026-10-20、2028-02-29 时，固定应用时间夹具给出相同结论。UTC 不合法的 clock 返回值拒绝。到期后的晋级幂等重放也拒绝，这是一处有意的行为修正。没有改 TTL、删负例、放宽门禁或新增任意时钟环境变量。

**兼容。** 构造函数只新增可选 keyword-only clock；已有调用继续默认真实 UTC。新增写接口 now 为可选 keyword-only。数据库 schema、迁移版本、持久化 payload 无变化；无数据迁移和历史删除。撤销本修复提交即可回退。

**练习（尚未作答）。** 用三分钟解释：为什么把日期改成“今天”或增大 TTL 会掩盖问题？画出显式 now、注入 clock、默认 utc_now 的优先关系；说明为什么截止点采用严格大于；写出首次晋级和幂等重放过期的负例；说明本地绿灯与完成发布的区别。

## A-container：非 root 应用与备份 helper 的权限边界

状态：PR #62 的远程 Container Readiness 首次运行发现独立阻断；修复已在同一分支本地验证，Issue [#63](https://github.com/Neil558719/llm-test-framework/issues/63)；远程复跑待执行。用户是否已理解或掌握：未评估。

**触发与证据。** Actions run 39444075058/job 118701218642 在 `deploy/backup.sh` 的 SQLite 在线备份阶段报 `PermissionError: [Errno 13] Permission denied`，临时文件路径为挂载的 `/backup/...db.m_*.tmp`。应用服务在 `docker-compose.yml` 中保持 `user: "10001:10001"`，helper 继承该用户，无法写入 runner 的挂载目录。

**修复与取舍。** 仅给短生命周期的备份/恢复 helper 增加 `docker compose run --user "0:0"`；应用容器仍以 10001:10001 运行，保留只读 immutable 完整性检查、恢复校验和清理 trap。没有放宽业务门禁或改变数据库 schema。聚焦守卫旧脚本先失败，修复后 `3 passed, 14 deselected`。

**面试表达。** “容器服务必须非 root，但迁移 helper 需要向宿主挂载目录写临时 SQLite 文件。我先读完整堆栈确认失败在 helper 写入边界，再用最小的 helper-only 用户覆盖修复，避免把应用改回 root。”

**练习（尚未作答）。** 解释为什么修改 compose 的应用 `user` 是更大风险；指出 backup helper 的写入挂载与 integrity checker 的只读挂载差异；说出 CI 远程复跑通过前为什么只能说“本地修复”。

### 2026-10-23 补充：root helper 产物的交接

首轮 root helper 修复后的远程 run `39448584021` 仍因 host runner 无法读取私有 root-owned 备份失败，artifact 上传也 EACCES。根因是 mkstemp 的私有权限与运行身份跨边界，而非 SQLite 备份内容错误。最终补充修复将备份及 manifest 交还调用脚本的 host UID/GID，从镜像可信 appuser 解析应用 UID/GID，在恢复 staging 校验后、原子替换前设置属主，保持应用非 root 与私有文件模式。

新增3项回归先在旧脚本 `3 failed`；独立审查又发现旧 root-owned 目标与替换后 chown 失败两种边界，补负例初稿 `4 failed, 1 passed, 8 deselected`。最终相关回归 `58 passed, 2 deselected, 2 warnings`；限定复审无剩余阻断项。测试运行真实 SQLite/payload；Windows 仅替代 chown/pwd 边界，真实 Linux 容器演练待验证。完整证据见 `../evidence/A01/container-ownership.md`。当前 SHA CI、合并、Release 与部署仍单独记录。

**取舍与练习（待作答）。** 仅能写成功不等于能完成交付；按 runner→helper→应用三种身份逐一验证文件读取和替换。说明为什么把备份 chmod 成全员可读写会增加风险，以及原子替换为什么可能改变文件属主。用户掌握未评估。
