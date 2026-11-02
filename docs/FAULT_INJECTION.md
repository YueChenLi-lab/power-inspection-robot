# 可复现故障实验

```bash
python3 -m InspectionOS.simulation.scenario_runner --output /tmp/inspection-faults
```

每次在新运行目录建立独立数据库，输出每组 `result.json`、原始 `events.jsonl`、`network.jsonl` 和总 summary。参数、步骤、预期、实际与结论均来自执行代码；[本次归档](experiments/faults/summary.json)保存实际结果。

| 编号 | 条件 | 检查 |
|---|---|---|
| E1 | 延迟 0.02 秒 > 模拟超时 0.01 秒 | 超时被观测，远端任务等待网络 |
| E2 | 完全断网 | 本地任务成功、远端任务等待 |
| E3 | 断网恢复，接收已提交但 ACK 丢失 | outbox 重投、接收去重、无已提交事件丢失 |
| E4 | 同幂等键重复提交及完成后重提 | 一个任务、一次执行 |
| E5 | 领取提交后 Worker 对象意外丢弃 | 重启识别 UNKNOWN 并恢复幂等任务 |
| E6 | 在 Mock Skill execute 内 SIGKILL 实验 Worker 子进程 | 真正进程异常退出；重开数据库后恢复 |
| E7 | 确定性 admission 上限一个任务 | 新任务拒绝、已有审计保留 |

E1 参数仅用于软件故障实验，不是机器人停车阈值。E7 是容量保护策略验证，不是写满真实磁盘的试验；底层 SQLite 实际写入失败另用 `PRAGMA query_only` 测试。E6 仅杀死实验新建的 Worker 子进程，不操作用户服务；恢复时用同版本无崩溃钩子的模拟 Skill。

网络模拟器支持 seed、online、latency、loss、timeout。seed 保证同参数下丢包序列可复现；操作系统调度和实际耗时不保证逐字节一致。其他测试覆盖非法状态、非幂等复核、审批拒绝、未注册 Skill、输入输出错误、超时、执行中取消、数据库事务回滚、Outbox 重试、缓冲与容量保护。
