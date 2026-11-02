# 追踪、指标与性能实验

任务具有 mission_id / trace_id / correlation_id / skill_id，状态事件和执行记录持久化；Skill 版本绑定在任务与执行表。BrainAdapter 语义计时与任务共用 trace。`export_trace(db, trace_id)` 可读取完整状态链。

Metrics 从实际任务时间、执行时长、数据库读写计时和网络模拟记录计算 mean、P50/P95/P99、吞吐、失败率、重试次数、队列等待、Worker 利用率、网络超时率与 Outbox 积压。百分位采用 nearest-rank；无样本返回 null。吞吐与利用率的观察窗口由调用方传入，本次 benchmark 使用实测 perf_counter 窗口。

| 阶段 | 实现状态 / 口径 |
|---|---|
| ASR | 未在新运行时接入；指标 null，原 ASR 独立实验保持不变 |
| Semantic | BrainAdapter 的总分析计时，含规则/证据/校验 |
| LLM | 成功的 ProviderResult 推理时间；Ollama 额外暴露请求和 JSON 解析时间 |
| Validator | 独立 Schema 时间、原 Validator 整体 evidence_semantic_validator 时间；后者包含一次原有 Schema 验证，非互斥分段 |
| Scheduler | 从上次入队状态更新时间到领取的队列等待 |
| Skill | 父进程执行隔离总时间，含启动/回收和输出验证 |
| Storage | SQLite 事务及读取计时，事务计时含 commit；不等同裸磁盘性能 |
| Network | 可复现模拟请求的实测耗时与超时标志，不是现场无线延迟 |

```bash
python3 -m observability.benchmark --output /tmp/inspection-benchmark --tasks 12
```

并发量 1/4/8 表示并发提交请求，Worker 始终一个；延迟为 0/0.005/0.02 秒，模拟超时 0.01 秒。每组先观察故障前状态，再恢复网络至零延迟后执行余下任务。生成 measurements.json、事件 JSONL 与五份独立 SVG。不同并发度、恢复阶段的时间全部包含在对应任务响应窗口；不能把本机 Mock 吞吐外推为 Xavier、ASR 或真实 LLM 性能。

[本次性能报告](PERFORMANCE_REPORT.md)包含实际数据。运行时 JSONL 和数据库可能包含原文及证据，真实用户数据的导出需要调用方自行管理访问与保留策略。


Follow-up 后 Scheduler 网络预检查位于写事务外；性能报告分别列数据库事务时间、网络等待和 Skill 时间，并附独立连接提交时长与并发竞态验证。旧报告和数据另存，不将两轮数字混为同一次实验。
