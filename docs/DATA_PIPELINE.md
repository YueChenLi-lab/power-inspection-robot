# 数据管线与存储管理

Collector 支持 transcript、task_log、mock_alarm、mock_temperature、state_change、skill_result、recovery，要求 trace、source 和 SHA-256。Mock 类型必须带 is_mock=true。`ingest_mission` 将任务快照、状态链与 Skill 输出收集为证据；CLI 另存手动输入原文。

Buffer 为有界线程安全 FIFO。满时显式抛 BackpressureError，调用方必须重试、暂停输入或拒绝请求，不能继续假装已采集。它是内存缓冲，未 flush 数据不保证耐崩溃；关键任务事件不经过它。

BatchWriter 在事务内验证校验和、检查容量、批写 evidence 和 evidence_outbox；成功提交后才 acknowledge 缓冲。写失败保留缓冲；同证据 ID 重投会去重，内容冲突拒绝。JSONL 是显式新文件导出、fsync 且不覆盖已有文件，SQLite 为主存储。批写对比脚本见 [batch_writer.py](../data_pipeline/batch_writer.py) 的 compare_writes，测量包含序列化与事务，不保证批量一定更快。

SyncManager 同时发送任务与证据的 Outbox，失败保留，模拟远端持久化去重。实际 at-least-once 边界见[离线自治](OFFLINE_AUTONOMY.md)。

## 保留与容量

- 任务、审批、执行、状态事件和关键证据没有默认删除接口。
- 只有明确的 `diagnostic/` 轮转日志与 `temporary/*.tmp` 可按年龄清理；临时缓存另可按容量从旧到新清理。
- 不跟随符号链接删除，不把数据库或普通 audit.jsonl 当可清理缓存。
- max_missions 与 max_bytes 为新任务/证据的 admission 保护；达到上限拒绝新写入而保留历史。关键终态/事件仍可写入以便收尾。
- storage_status 报告逻辑数据库大小、独立 WAL 字节与预警。max_bytes 不是操作系统磁盘配额，也不覆盖 WAL/文件系统总量；生产部署需外部磁盘监控、预留审计空间和备份。

SHA-256 可检测内容变化，不提供来源真实性证明、签名或安全备份。当前没有自动审计归档和外部对象存储。真实音频仍由原 voice_lab 管理，新系统不复制或删除历史音频。
