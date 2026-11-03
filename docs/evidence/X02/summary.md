# X02-A / Issue #82：显式检查层级

起点 `5fa3ebd8bd769498caf9de07e42e025109fcb404`，隔离分支
`codex/x02-test-tiers`。仅本地离线实现；没有 push、PR、Actions、保护设置、合并、
Release、provider/UI/系统/容器验收。本任务不重试 B08 审计，不校准 X03 的旧 Mock 限制。

原始命令、XML、日志、退出码放在父工作区 `.context/X02/A/<批次>/`。
工具是既有 uv 0.9.11；新私有 `.context/x02-a-env` 使用 Python 3.12.14 和 A 原 uv.lock。
第一次 `sync --locked --offline --extra ci --python 3.12` 缺 cp312 pydantic-core 缓存，
无测试执行；随后锁定安装成功。原 110 条锁记录和 requires-python>=3.9 不变。

| 批次 | 实际结果 | 解释 |
| --- | --- | --- |
| legacy-red | 2 failed / 9.79s | 旧 smoke 的 1 skip 导致 exit0；旧 regression 首次断言失败经一次 rerun 变成 exit0。合成测试不调用 app/model。 |
| interface-gap | 1 setup error / 0.58s | 缺 scripts/check.py，单列接口缺失，不计业务 RED。 |
| focused-first | 23 passed / 20.82s | 隔离 suite 核对选中/排除、真实失败/跳过/xfail/依赖/空集/凭据隔离等边界。 |
| inventory-edge-red | 1 failed / 2 passed / 23 deselected / 4.71s | 初稿允许把必需 smoke 节点同时排除，真实少跑误绿；零退出无证据和收集漂移守卫已通过。 |
| focused-final | 26 passed / 27.65s | 最小禁止 smoke 必需节点被排除后通过。 |
| smoke-first | 5 selected / 5 executed / 5 passed | 实际收集 1299 nodes，1294 排除逐项说明；不是整套 tests 冒充 smoke。 |
| focused-archived | 26 passed / 29.41s | 辅助函数新增子证据归档后复核；各黑盒调用的报告/XML/exit保留在children。 |
| core-related | 833 passed / 2 failed / 464 deselected / 2 warnings / 145.58s | 835所选全部执行，入口真实非零；下述两失败独立保留，不能称本批全绿。 |
| env-repair-focused | 2 passed / 2 warnings / 5.69s | 新入口不强设Mock模型名；黑盒scrub和原M13价格表相关检查通过。 |
| clock-fixture-related | 89 passed / 2 warnings / 5.40s | 获批仅原2参数测试使用上下文逻辑时钟，原20ms预算/断言不变；整个async相关文件通过。 |

`core-related` 的新入口回归：清除配置后额外强设 `REFERENCE_AGENT_MODEL=mock`，
改变了默认 Mock 模型身份（原默认空字符串），与原 M13 合成 `mock/` 价格表不匹配，
导致 7 场景成本不完整。最小移除非必要模型名强设，保留 mode/provider=mock 和凭据scrub；
不修改价格表、场景或成本阈值。

另一失败是原20ms预算测试观察到 rate_wait=0；现有XML不足以证实具体在init耗尽或CPU原因。
静态上总deadline从预处理前起算，limiter之前有多处checkpoint，原测试把“主机能及时进入
所选阶段”混进了“该阶段受预算约束”。经主明确批准，仅该2参数夹具在上下文内使用逻辑时钟：
保留20ms，真正进入所选阶段后推进30ms并实际await；断言entered/cancelled、deadline、零send、
已取得适配器closed/未取得not_created及clock还原。产品预算代码、其他墙钟/队列测试不变，
不能把本改动称作性能改善或已实证主机调度根因。

修后core一次必要相关回归中；尚无本任务 full/root 通过主张。
新增辅助归档保留每项黑盒子调用的 report、XML、日志和 exit，避免系统临时目录轮转丢证据。
父测试通过不等于子负例通过：子进程的预期非零、failed/skip/收集错误全部保留。

普通 offline 排除边界：5 UI + 2 Windows 系统集成 + 1 Compose CLI；
native Windows 额外 3 POSIX 参数契约不运行，PowerShell fake-docker 参数契约可运行。
Linux 按 PowerShell 实际可用性分类，不能伪称覆盖该环境。
没有降低阈值、改 TTL、删除负例或执行断言 rerun。

定向静态检查：ruff0.14.5新增4文件通过；mypy1.18.2对3个新增模块通过（首次observer
变量缺类型注解1项，已补dict[str,Any]，不是产品测试失败）。命令/exit保留type-final/lint-final。

新入口及 manifest、独立 pytest observer、CI master push/稳定上下文、UI 前提与无跳过检查见
`docs/统一检查入口.md`。当前修改不需新增运行依赖，uv.lock 不作凑格式改动。
已保存的远端 master protection=HTTP404 来自主流程准备证据，未改设置。
独立审阅、不可变 full、当前 SHA CI、故意失败 PR、分支保护、合并/发行和环境分开验收。
用户练习未完成，掌握状态未评估。

主流程恢复核对：core-after-repairs 已实际结束，835 selected / executed /
passed、464 excluded、errors=[]、exit0；执行 XML、日志和 before/after 源哈希
均已保存。没有遗留后台命令，原实现者已停止写入，由主流程接管冻结整理。
原 core-related 的833通过/2失败证据保留；没有把它改写为全通过。
当前只完成 core 相关回归，full 尚未执行。主静态审阅共同入口、完整性守卫、
CI 与已批准时钟夹具未发现未闭合问题；接下来冻结提交，再做 full 与B适配。

最终普通本地full：固定提交ddb9f10cedd841e87f68b973a3733b0fb5a12640，
Python3.12.14下1288 selected / executed / passed、11 excluded、errors=[]、exit0；
实际XML1288项无失败/错误/skip，8项资产核对，258项工作哈希及clean状态前后
一致。排除是5个UI、2个主机系统、1个Compose CLI、3个非原生POSIX参数节点，
不把这些环境写为已验收。主证据work/ci-m0-resume/x02-a-frozen-full-verification.json。
产品包目录与A08的110依赖锁未变，未虚称新的wheel或真实服务效果。
最终文档提交仅记录证据，继承受测代码，不为文档重复运行测试。当前SHA远端
CI、分支保护/失败PR、合并/Release和环境验收仍待执行；B适配继续独立推进。
