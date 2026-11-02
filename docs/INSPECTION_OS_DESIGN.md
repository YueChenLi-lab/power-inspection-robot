# InspectionOS v0.1 设计

## 运行入口

```bash
# 仓库根目录；Python >=3.10，Linux
python3 -m InspectionOS --db /tmp/inspection-demo/local.db --idempotency-key alarm-demo
python3 -m InspectionOS --db /tmp/inspection-demo/offline.db --offline
```

默认使用 v2 规则，显式 `--provider mock` 使用 v3 脚本候选。数据均为 Mock。`--recover` 在领取任务前执行恢复；恢复必须确认没有另一 Worker 在运行。CLI 将证据写入 SQLite、尝试同步到同目录的模拟远端，并打印结果；诊断日志独立轮转。Ctrl+C 不保证任务已提交终态，重启后应显式恢复。

## 任务合同

任务具有 mission_id、trace_id、correlation_id、skill_id、mission_type、payload、status、priority、created_at、updated_at、idempotency_key、source、attempts、max_attempts、skill_version、fingerprint。时间为 UNIX 秒；业务时间窗为带时区 ISO 日期、左闭右开。

MissionManager 创建、查询、列举、取消和审批；Registry 提供显式版本的 Skill；Scheduler 按 priority 降序、创建时间与 rowid 升序取候选；事务外网络预检查后，新事务重读状态/版本/审批并原子领取；Executor 子进程执行并验证输出；Recovery 显式处理被中断的持久化任务。`Worker.serve(stop_event)` 支持常驻轮询和正常退出，`run_until_settled()` 等待有界重试但不擅自解决网络和审批等待。

`Database.transaction()` 使用 BEGIN IMMEDIATE 和回滚，missions、mission_events 与 outbox_events 一同提交。skill_executions 的开始随领取提交，结束随任务结果提交。幂等键唯一；相同键内容不一致报错，已完成任务不再次执行。payload 与策略摘要进入 fingerprint，不凭键值覆盖旧请求。

## 运行限制

同一数据库由操作系统文件锁限制为一个 Worker / Recovery；SQLite 支持多个提交请求序列化写入。Skill 的 Python 对象属于可信本地代码，子进程是超时/故障隔离，不是恶意代码安全沙箱。当前接口允许以后替换 Worker，但没有实现多 Worker 租约、分布式集群或高可用。

任务数据库和证据需随环境保留，进程不能假定持续运行。正常恢复不需要重新安装模型。API 操作在本地 Python 调用层提供，尚未提供网络认证服务或管理 UI。

重试统一策略与输入输出业务合同见[本轮修复说明](RELIABILITY_FOLLOWUP.md)。
