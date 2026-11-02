# 运行时可靠性 Follow-up

基线：fdc997e432ee65c524e12556feba013031dbed20。当前原开发分支 feature/edge-task-runtime 保持不变。执行前发现 PR #2 实际已合并；经用户选择，在同分支推送修复并创建后续 Draft PR，不修改 main、不强推、不改写历史。

## 修改前后

| 模块 | 原有问题 | 修改后 | 核心证据 |
|---|---|---|---|
| Recovery | 漏查 retryable，与 Worker 不一致 | 统一 retry_decision；额外要求不确定结果 recovery_safe | 两条路径同一组合矩阵 |
| Scheduler | BEGIN IMMEDIATE 中请求网络 | 候选快照 → 事务外 preflight → 新事务重读与原子领取 | 独立连接可写、取消/撤销竞态、双 claim |
| Approval | 字符串 false 被当 truthy | type(allow) is bool；actor/token 非空；终态与重复审批拒绝 | True/False/string/int/None、审计 |
| Skill | 输出只满足结构 | 每个 Mock 能力的 request/result 业务校验钩子 | Schema 通过但设备/记录/时间/来源错误被拒绝 |
| Evaluation | evidence 指标复制完整 Validator | 独立文本证据检查，阶段分母和 unavailable 明示 | Schema/证据/完整 Validator 可分别得出不同结论 |
| E5/E6 | 重建对象与进程异常文字混淆 | E5 同进程运行时重建；E6 Skill 执行内 SIGKILL | 新编号不变、旧数据不改 |
| Regression/CI | 历史文件缺失且无 CI | 严格入口保留；CI 精确标记前置资产，执行其余关键测试 | Git 历史搜索、Actions 真实运行 |

## 恢复与副作用

retryable 表示允许重试，idempotent 表示重复调用的效果合同，二者不等价。Worker、Recovery 和退避后的 Scheduler 都调用同一策略，要求状态可重试、版本一致、预算剩余、安全条件满足。结果不确定时还需要 trusted Mock Skill 显式 recovery_safe=true（现有三个只读 Mock 能力满足）；不将“幂等”标签当任意外部副作用的证明。未声明可安全恢复或非幂等结果进入现有 WAITING_APPROVAL，清除批准位并记录原因。版本变化、禁止重试或预算耗尽则失败；取消任务不重跑。

不确定执行记录仍标 UNKNOWN；人工复核不是自动执行信号，独立本地操作员必须先核查结果。没有外部副作用 Exactly-once 承诺。

## 调度三阶段与一致性

第一次短事务调整到期任务并读取队列快照；释放连接锁和写事务后进行网络预检查；最后新事务按 mission_id 重读。状态必须仍为 QUEUED，updated_at 必须与快照一致，注册版本/合同仍相同，审批和安全策略仍允许，才能原子地写 RUNNING、尝试次数及 execution-start。预检查期间取消或 revoke_approval 导致原快照失效。并发 claim 可以重复预检查，但不能重复领取同一任务。本版本仍只运行一个 Worker，不扩展分布式租约。

## 契约边界

Registry 先验证 input/output JSON 结构，再调用 Skill 自身的 validate_request / validate_result。只有 Mock 查询家族要求设备、记录时间和固定来源，不给任意 Skill 强加统一业务字段。单设备用 device_id，多设备用 device_ids（非空、唯一，二选一），输出设备集合须等于请求集合，所有记录必须属于该集合并在 [start,end) 中。各记录包含独立 Mock 来源与告警/测温必需字段；测温比较按设备分组，不能把不同设备的最后两条记录直接比较。

业务校验失败通过 Worker 错误路径记录，绝不成功；是否重试仍服从统一策略。Mock 标记与 SHA 校验均不是现场数据真实性证明。

## 评测口径

Evidence Constraint 独立重查原文区间、设备/编号、数值/单位、时间、否定、自我修正和条件，与原确定性 evidence 对照，不调用 validation.valid。它只衡量文本约束，intent/DAG/draft 的完整政策仍由完整 Validator 判断。无人工确认 Gold 时 human_gold_accuracy=null。

JSON Parse 只统计有实际 JSON 解析观测的响应，MockProvider 没有传输解析则 null。Schema 按可观察的解析候选统计，Evidence 按可观察证据检查统计；均保存样本分母。完整 Validator 接受率按全部请求尝试统计，传输/模型失败计未接受。失败分为 transport_failure、timeout、json_parse_failure、HTTP 与响应合同错误。真实模型和 Mock 始终分组；不可将合成字段匹配率当人工语义正确率。

详见[历史资产](HISTORICAL_TEST_ASSETS.md)、[性能报告](PERFORMANCE_REPORT.md)、[验收记录](VALIDATION_REPORT.md)和[E5/E6 修订](experiments/faults/REVISION_FOLLOWUP.md)。
