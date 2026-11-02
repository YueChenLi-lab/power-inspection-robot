# E5 / E6 定义修订记录

历史 E1–E7 的 JSON / JSONL、事件 ID 和时间戳保持原样，不将本轮名称回填至旧数据。

| 编号 | 修订后的准确名称 | 故障模型 |
|---|---|---|
| E5 | 任务领取后运行时重建 | 同一父进程关闭 Application、重开数据库；没有杀死 Worker 进程 |
| E6 | Worker 执行期间进程强制终止 | 在 Mock Skill execute 中 SIGKILL 实验 Worker 子进程，重启后恢复 |

原代码中 E5 的步骤文字“Exit unexpectedly”不够准确，应按此修订说明解读。E6 才验证进程崩溃，不把对象重建当作 SIGKILL 实验。

本轮重新运行的[结果与日志](../followup-v1/faults/summary.json)使用 definition_revision=followup-v1，结果包含准确的 name 和 steps。恢复使用统一重试策略，不能绕过 retryable、幂等性、版本、预算、状态和审批。
