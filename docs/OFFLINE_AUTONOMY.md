# 弱网自治、幂等与恢复

本实验对应工博会语音平台与通信链路不稳定的工程经验，验证的是软件任务机制，不模拟物理失控、无线电传播或停车阈值。

## 断网行为

- offline_supported 的本地 Mock Skill 继续运行。
- 远端数据依赖任务或需要网络授权的任务在网络探测失败时进入 WAITING_NETWORK；不产生伪造成功结果。
- 网络恢复后重新排队并复查安全策略；缺少独立审批仍等待。
- 本地任务和事件先落 SQLite，网络中断不丢失已经提交的事件。内存 Buffer 尚未 flush 的证据不承诺耐进程崩溃；关键状态事件绕过 Buffer 直接事务持久化。

## Outbox 与投递语义

状态事件和 outbox 同事务保存，证据和 evidence_outbox 同事务保存。SyncManager 读取 PENDING，模拟网络请求后发送到 MockRemote，收到成功返回才标 SENT。失败保留 PENDING 及尝试次数；ACK 丢失会重复发送。

MockRemote 用持久化 inbox 主键 event_id 去重并检查同 ID 的 payload 一致性。投递语义为 at-least-once；单数据库任务幂等键和模拟远端去重不能保证任意外部副作用的绝对 Exactly-once。当前同步端点是本地模拟 SQLite，不连接真实云端。

## 重启

在独占 Worker 锁下显式 `app.recovery.recover()`。运行中任务标记执行结果 UNKNOWN。必须同时声明 retryable、idempotent、recovery_safe，且版本未变、预算剩余、状态与审批满足，才恢复到 RETRY_WAIT；非幂等或未声明不确定效果可安全恢复时转 WAITING_APPROVAL 并清除批准位；未注册、版本改变、预算耗尽则 FAILED。WAITING_NETWORK 和 RETRY_WAIT 已持久化，Scheduler 可继续处理。不要在另一个活跃 Worker 旁边扫描并重跑所有 RUNNING 任务。

`Worker.serve(stop_event)` 正常退出完成当前有截止时间的执行后停止领取；SIGKILL 或数据库写入失败可能留下 RUNNING。恢复使用实际持久化状态，不猜执行成功。底层数据库错误向调用方抛出，不能当正常结果。
