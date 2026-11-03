# A 项目交付与面试演示

本页帮助复现质量评测平台的离线工程行为，并据此讲清设计取舍。X04 当前是本地文档交付阶段，独立文档审查与最终字节继承另记。用户尚未独立复现或口述，练习与掌握状态仍未评估；测试通过数不代表模型准确率、线上收益或生产规模。

## 已有证据与交付边界

| 检查点 | 已实际完成 | 解释范围 |
| --- | --- | --- |
| X03 本地完整验收，源码 `85acc66bf2410b6b380774f034992aea3eb28909` | 1346 项选择、执行并通过；11 项逐项说明环境排除；373 文件哈希前后一致 | 本地工程回归；未把环境排除记为通过 |
| X03 历史失败 | 首次全量 1340 通过、6 项 Windows 完成记录路径失败；原 XML 保留，最小修复后完成上述全量 | 历史失败不覆盖，定向计数不加到全量计数 |
| X04 预备命令演练，同一源码 | smoke 5 项通过；下述两个演示函数展开为 3 项通过；两条命令均退出 0 | 实测命令总耗时 14.641 秒，约 14.64 秒；这是现有本地环境的命令耗时，不是生产性能指标或用户已完成演示的证据 |
| X03 数据与调用 | A 60 条、B 60 条 AI 自建 synthetic silver；公共工具已消费 B 语料；真实模型请求为 0 | 没有独立人工金标或真实 Judge 效果证据 |

X03 是仓库工程工具；运行时发行包仍为 dev8，没有为这次工具变更重新制作运行时 wheel。详见 [X03 证据](evidence/X03/summary.md)、[校准工具指南](calibration.md) 和 [面试账本](interview/ledger.md)。

## X03 远程检查与当前阻塞

| 环节 | 已核验状态 |
| --- | --- |
| PR 与受检 head | [PR86](https://github.com/Neil558719/llm-test-framework/pull/86)，head 为 [709020c6797b9f410e0eca67273e65eb098a9f6f](https://github.com/Neil558719/llm-test-framework/commit/709020c6797b9f410e0eca67273e65eb098a9f6f) |
| 同 SHA 的 CI | [PR 检查记录](https://github.com/Neil558719/llm-test-framework/pull/86/checks) 在 2026-11-03 16:40 UTC 观察时为 42 项 SUCCESS；21 个 required contexts 绑定 App15368，strict 与 enforce_admins 生效，当时 merge state 为 CLEAN |
| 下载后的 CI 全量产物 | [CI run41675753935](https://github.com/Neil558719/llm-test-framework/actions/runs/41675753935) 的 Python3.12、3.14 各实际选择/执行/通过 1349 项，8 项显式排除；各含 54 条校准节点和 8 项运行时资产核对，不与本地或另一版本计数相加 |
| 合并到 master | 未执行。自动审批明确拒绝该受保护主分支合并，理由是当前对话缺少对该操作的明确用户授权；正常合并需取得针对 PR86/head709020c 的明确授权后重新审批 |
| 工程发行 | 尚未发布；合并及后续验收未完成，不能把 CI 成功记作已发行 |
| X04 文档 | 当前仅本地集成，未推送或创建本阶段 PR；上面的 CI 记录属于 X03 的受检 head |

Linux CI 比 Windows 本地多执行的 3 项，精确对应 `tests/test_final_deploy_args.py::test_shell_operations_preserve_compose_file_order` 的 `backup.sh`、`migrate.sh`、`restore.sh` 参数契约。它们在原生 Windows 明确排除，Windows 没有额外独有执行节点；1349/8 与 1346/11 的差异来自平台范围，不是无解释的用例丢失，也不代表执行了真实备份或部署。

本地原始证据保存在父工作区的 `work/ci-m0-resume/x03-a-current-PR-checkpoint.json`、`x03-a-CI-full-verification.json`、`x03-a-merge-approval-block.json`、`x03-a-frozen-full-verification.json` 和 `x04-offline-rehearsal-verification.json`。这些是父工作区记录，不是本仓库随附的发布附件。演示可在下述新目录生成自己的报告与 XML。

人工金标、真实 Judge 调用与效果、真实 IdP/provider/HTTPS/持久部署仍未验收。B 的外部交付和完整 B08 安全审查缺口也未由本页关闭。可选增强 E01–E04 不属于本页承诺。

## 原生 PowerShell 离线演示

在 A 仓库根目录打开原生 PowerShell 5.1 或更新版本。使用已经安装本仓库及其开发测试依赖的解释器；下面默认 `.venv\Scripts\python.exe`，若现有环境在别处，只修改 `$pythonExe`。显式 `-p llmtest` 使用已安装的 pytest 插件入口，`pytest_asyncio.plugin` 也须在该环境中可用。

以下命令按已有演练的模式、插件和两个完整 node ID 编写，输出目录改为当前仓库中的独立目录。此次纯文档集成没有重复这些命令。

```powershell
$repoPath = (Resolve-Path -LiteralPath '.').Path
$pythonExe = Join-Path $repoPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw '请将 $pythonExe 设为已安装本仓库及开发测试依赖的 Python 解释器。'
}

$env:LLM_MODE = 'mock'
$env:LLM_TEST_MODE = 'mock'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTHONPATH = $repoPath
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'

$demoStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$demoRoot = Join-Path $repoPath ('.context\delivery-demo\' + $demoStamp)
New-Item -ItemType Directory -Path $demoRoot -ErrorAction Stop | Out-Null

& $pythonExe -B -X utf8 scripts/check.py --tier smoke --mode offline --out (Join-Path $demoRoot 'smoke')
if ($LASTEXITCODE -ne 0) {
    throw 'smoke 未通过，请保留输出目录并查看报告。'
}

& $pythonExe -B -X utf8 -m pytest -q -o 'addopts=' -p llmtest -p pytest_asyncio.plugin --basetemp (Join-Path $demoRoot 'pytest-temp') --junitxml (Join-Path $demoRoot 'cases.xml') 'tests/test_evaluation_validity.py::test_empty_claims_block_required_assertion' 'tests/test_evaluation_validity.py::test_helpfulness_score_is_not_gold_accuracy'
if ($LASTEXITCODE -ne 0) {
    throw '证据用例未通过，请保留 cases.xml 和控制台输出。'
}
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 关闭自动发现，再由 `-p` 显式加载插件。smoke 入口由自身检查清单加载插件；不要把 pytest 的 `-p` 参数传给 `scripts/check.py`。这些命令不启用 live 模式，不需要真实模型凭据。

成功时，smoke 报告列出实际选择、执行及排除节点；第二条命令应为 3 项通过。空事实用例按 OpenAI/Anthropic 两个 mock 客户端展开，加上 helpfulness 用例共三项，并非调用两个真实模型。pytest 父用例通过表示预期拒绝或断言确实发生，不能把退出码 0 解释成被拒绝的业务操作成功。

## 五分钟讲述顺序

| 时间 | 操作与要讲清的证据 |
| --- | --- |
| 0:00–0:45 | 运行 smoke，打开选择/执行/排除清单，结合覆盖范围解释绿色退出码 |
| 0:45–2:00 | 运行两个演示函数，解释空 claims 为何不是零幻觉，以及 helpfulness 均分为何不是 gold accuracy |
| 2:00–3:00 | 对照保留的旧失败与修复后结果，解释必需测量缺失时门禁拒绝；使用原始日志，不临时修改生产代码制造失败 |
| 3:00–4:00 | 打开 X03 报告与 manifest，解释 silver、不可评分母、意图分组、首次 holdout 消费和显式 exploratory；live `run` 未就绪时写 `not-run` 报告并退出 2 |
| 4:00–5:00 | 展示 PR86/head709020c 的已核验 CI 与当前合并阻塞；另展示历史 X02 失败 PR 的阻断证据，明确后者验证的是当时的保护规则 |

这是一份讲述安排，尚未证明用户能在五分钟内独立完成。

## STAR A1：把“没有测到”与“测得很好”分开

**S — 情境：** 旧实现把空 claims 补成零幻觉，并把 helpfulness 均分汇总成 accuracy；缺少测量时仍可能呈现良好结果。

**T — 任务：** 让必需评测在证据不足时阻断，同时保留正常事实、非事实场景和已有接口。

**A — 行动：** 明确 evaluated/inconclusive/not_applicable/error 状态，严格检查 Judge JSON 类型、分数范围与结论一致性；将显式真值分母与 `mean_judge_score` 分开。非事实场景允许显式不适用，必需断言不能借此通过。

**R — 结果：** A02 首批实际 84 项失败证据保留，最终合并回归 658 通过、7 项按规则排除，安装包 95 项契约通过；PR66 与 dev1 发行已验。后续 A05 接通 YAML 质量评测。这些是工程契约结果，没有证明真实 Judge 准确率提升。

可结合 [`llmtest/hallucination/detector.py`](../llmtest/hallucination/detector.py)、[`llmtest/metrics/tracker.py`](../llmtest/metrics/tracker.py)、[演示用例](../tests/test_evaluation_validity.py) 与 [A02 证据](evidence/A02/summary.md) 解释根因、负例和取舍。

## STAR A2：证明 CI 真正阻断，而不只展示配置

**S — 情境：** 选择范围、运行模式、执行结果和分支保护分属不同环节；单看绿色徽章不能证明必需工作都已执行。

**T — 任务：** 形成可检查的选择/排除/执行清单，并核验同 SHA 的必需检查能约束合并。

**A — 行动：** 分离 smoke/core/full 与 offline/live；将报告绑定实际节点和资产哈希，读取主分支保护及 GitHub App 身份。使用独立负例 PR84，验证六项必需检查失败后的 BLOCKED 状态，再关闭该 PR，保留原始失败记录。

**R — 结果：** 历史 X02 合并 `1093229` 后离线 1292 项通过、11 项显式环境排除，21 个主分支检查通过；工程发行 `x02-ci-20261103` 的两项资产回下载核验完成。没有尝试绕过保护，也没有将其解释为真实服务部署完成。X03 的远程状态以本页单独列出的实际记录为准。

取舍是保留真实环境入口及排除原因，离线结果不能冒充 live。可查看 [X02 证据](evidence/X02/summary.md)、[PR83](https://github.com/Neil558719/llm-test-framework/pull/83)、[失败 PR84](https://github.com/Neil558719/llm-test-framework/pull/84) 与 [历史工程发行](https://github.com/Neil558719/llm-test-framework/releases/tag/x02-ci-20261103)。

## 十个追问

1. **为什么空 claims 不是零幻觉？** 分母为零表示未测到；必需断言应拒绝，不能制造零错误率。
2. **为什么 helpfulness 不等于 accuracy？** 它是裁判分数；accuracy 需要明确真值、真假计数及来源，不能把均分改名成准确率。
3. **拒答如何评价？** 按任务规则区分合规拒答与质量失败，不能统一按无事实处理。
4. **real 模式为什么不能回退伪 embedding？** 那会把合成结果冒充真实能力；不支持、暂时不可达和认证错误应分别报告。
5. **为什么需要应用范围过滤？** 角色不等于对象授权；过滤须在分页和关联读取之前执行。
6. **有哈希为什么还需要访问控制？** 哈希绑定特定字节的身份，不能授予读取或修改权限。
7. **平均延迟为什么不能代表吞吐？** 成功工作量和观测窗口不同，失败请求不能贡献成功吞吐。本页命令耗时也不是线上响应性能。
8. **如何证明必需 CI 生效？** 核对同 SHA 检查、App 身份与实际保护规则，再以真实失败 PR 核验阻断；X02 证据不能自动证明未来配置持续生效。
9. **120 条数据能证明 Judge 好了吗？** 不能。它们是 A/B 各 60 条 AI 自建 silver；独立人工标签与真实模型结果均缺失，工具通过不等于 human_verified。
10. **X03 的预算如何计算？** 每次物理请求及重试先预留完整输入与输出上界，未知用量不退款，关闭 SDK 隐藏重试；缺可靠上界则不发请求。缺少可追溯币种、价格来源与版本时费用未知，配置金额上限却缺报价也会阻断。当前 live `run` 仍是 `not-run`、退出 2，真实请求为 0。

## 用户练习

待用户独立运行两条命令，说明父测试通过与被测业务拒绝的区别；不看稿复述一张 STAR；解释 silver、人工金标和真实 Judge 输出的差异。只在实际练习后更新完成与掌握状态。