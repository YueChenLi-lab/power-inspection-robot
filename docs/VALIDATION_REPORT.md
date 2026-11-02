# 可靠性 Follow-up 验收记录

## 分支与历史

本轮基线 fdc997e，原工作区干净，当前分支与 PR #2 的 head 均为 feature/edge-task-runtime。执行前 GitHub 显示 PR #2 已合并（与任务描述不同），因此未尝试重开或篡改；经用户选择建立[后续 Draft PR #3](https://github.com/YueChenLi-lab/power-inspection-robot/pull/3)。所有修复在原分支，不合并 main、不强推、不改原 v2、语音实验室或原测试。

[上轮验收原文](experiments/followup-v1/validation_report-before.md)、原实验 JSON/JSONL 与时间戳全部保留。本轮新增实验在 experiments/followup-v1。

## 实际本地结果

| 项目 | 本轮实际结果 | 口径 |
|---|---|---|
| 新增及原任务运行时套件 | 46 项通过 | 包含原 31 项及本轮恢复、调度、审批、业务与评测测试 |
| 严格原 Python 回归 | 121 项：111 通过、6 缺资产错误、4 模型跳过 | 与本轮基线一致；退出码 1，不称全部通过 |
| 原 Python 的显式 CI 资产策略 | 121 项：111 通过、0 失败/错误、10 跳过 | 6 缺历史资产 + 4 模型，跳过不计通过 |
| 原 Node | 19 项通过 | 4 个文件，前端/浏览器流程模拟 |
| E1–E7 重跑 | 7/7 通过 | E5 运行时重建，E6 执行内 SIGKILL |
| Scheduler 解耦实验 | 预检查阻塞时另一连接可提交；取消后领取数 0 | 测量网络等待/事务/提交时长，另测并发 claim 与撤销审批 |
| 性能重跑 | 9 × 12 个任务，网络恢复后 108/108 完成 | 单 Worker、固定 Mock，无真实模型性能 |

[严格全回归日志](experiments/followup-v1/strict-validation.log)记录新/原/Node 的退出码 `[0,1,0]`；[CI 资产策略本地日志](experiments/followup-v1/original-ci-local.log)与[机器可读计数](experiments/followup-v1/original-ci-local-summary.json)区分 passed / skipped。没有修改原断言或制造历史样本。

## 本轮针对性证明

- Worker / Recovery 使用同一策略，矩阵覆盖 retryable=False、非幂等、不确定副作用未声明安全、版本变化、预算耗尽和审批问题；取消任务不恢复。退避到期时再核验。
- 网络请求不持有写事务或连接互斥锁；另一条真实 SQLite 连接先提交，网络后释放。期间取消或撤销审批令快照失效；双 claim 只生成一次 execution-start。
- approve 仅接受 True / False，字符串 false/true、1、None 拒绝；actor/token 非空，重复或终态审批拒绝，凭据失败有审计。
- Schema 合法的错设备头、错记录设备、越界时间、缺记录字段和不可信来源被业务 Validator 拒绝，不能 SUCCEEDED。正常单/多设备对三个 Mock 能力均验证。
- 独立 Evidence Constraint 检查不读取 validation.valid，覆盖原文区间、设备、数值/单位、时间、否定和自我修正。Schema 可通过而 Evidence 失败；Evidence 可通过而完整 Validator 失败。无人工 Gold 不计算语义准确率。
- 传输失败、超时和非法模型 JSON 分别记录；没有真实模型调用时不把 Mock 的指标归入模型效果。

## GitHub Actions 真实运行

首轮修复代码提交 55097a0 的[真实运行 41391529726](https://github.com/YueChenLi-lab/power-inspection-robot/actions/runs/41391529726)已完成，5 个 Job 均 success：Python 3.10 运行时、Python 3.12 运行时、Brain v3、原回归、Node。每个运行时 Job 还重新执行 E1–E7。API 返回的实际 Job/Step 结果已[归档](experiments/followup-v1/actions-result.json)。本地与云端计数分开，不把本地日志冒充 Actions 日志。

普通 CI 不下载模型，不要求 GPU/Ollama 或用户本地文件。6 项历史资产仅在确实不存在时标明 skipped，其余关键测试照常运行；原套件至少执行 100 项的防误配置检查保留。可选 jsonschema 对照及真实 ASR 的自带 skip 因环境而异，见 CI artifact 的 original-summary。

当前代理允许读取 Actions 状态 API，但完整日志下载的 results-receiver 域名仍受网络策略拦截；不能声称已下载原始云端日志。已保存精确域名的环境配置草稿，状态与 Job 成功证据不依赖日志下载。最终提交的 Actions 状态以 PR Checks 页面为准。

## 未完成的外部前置条件

Git 历史和可达对象中没有两个原始历史文件，详见[历史资产与恢复路径](HISTORICAL_TEST_ASSETS.md)和[搜索记录](experiments/followup-v1/history-search.json)。严格回归仍有这 6 项未完成验证，需要原始授权归档，不能伪造。

真实 Qwen3 效果、人工 Gold、真实 ASR 到 OS、真实台账/巡检库、真机和生产认证均未验收。本轮不增加硬件权限，不声称绝对 Exactly-once 或生产部署成功。
