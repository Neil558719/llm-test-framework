# 面试素材账本

## A01：固定日期夹具与保留期时钟分离

状态：本地修复与验证；PR/CI/合并/发布/部署尚未完成。Issue [#61](https://github.com/Neil558719/llm-test-framework/issues/61)。用户是否已理解或掌握：未评估。

**问题与证据。** 2026-10-20 在源 `cd51114b` 的专用新环境复现 `18 failed, 516 passed`。固定的 8/9 月数据被真实当前日期判过期；测试过去通过不能证明未来日期也通过。问题不是 TTL 太短，生产到期规则仍需生效。

**原理。** 仓储注入 `Clock = Callable[[], datetime]`，默认返回 UTC aware 的 `utc_now`。`now is None` 才读 clock；显式 now 优先。复核与晋级一次操作解析一个时间，用于资格检查与写入时间戳。API 不再传墙上时间覆盖仓储；质量引擎用仓储时间产生 validation 时间戳；CLI 在进程内 main 注入仓储 factory。

**负例红绿。** 原实现新增验收 `13 failed`（无 clock 参数）；撤掉晋级过期保护时，首次晋级与幂等重放两个负例 `2 failed`；恢复 API 的真实时间覆盖时，读 API 负例 `1 failed`。恢复修复后相关回归 `81 passed`，最终完整回归 `556 passed, 5 deselected, 2 warnings`，原 18 项失败全部转绿。测试与脱敏逐项结果见 `../evidence/A01/summary.md`。

**边界与取舍。** 30 天窗口仍按 `timestamp > now - 30 days` 读取，等于 cutoff 就过期。覆盖差 1 微秒、等于、超出、跨月、2024 闰日；共享 wall-clock provider 模拟 2026-09-01、2026-10-20、2028-02-29 时，固定应用时间夹具给出相同结论。UTC 不合法的 clock 返回值拒绝。到期后的晋级幂等重放也拒绝，这是一处有意的行为修正。没有改 TTL、删负例、放宽门禁或新增任意时钟环境变量。

**兼容。** 构造函数只新增可选 keyword-only clock；已有调用继续默认真实 UTC。新增写接口 now 为可选 keyword-only。数据库 schema、迁移版本、持久化 payload 无变化；无数据迁移和历史删除。撤销本修复提交即可回退。

**练习（尚未作答）。** 用三分钟解释：为什么把日期改成“今天”或增大 TTL 会掩盖问题？画出显式 now、注入 clock、默认 utc_now 的优先关系；说明为什么截止点采用严格大于；写出首次晋级和幂等重放过期的负例；说明本地绿灯与完成发布的区别。
