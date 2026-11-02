# 私有本地评测报告

本目录仅保存报告结构说明。实际运行、人工标注和原始模型输出放在被 Git 忽略的 `.local-evaluation/`，不放入此目录。

每次 CLI 新建独立 `run-日期时间-随机后缀/`：

| 文件 | 用途与写入策略 |
|---|---|
| metadata.json | 创建时配置、数据集 SHA、实际可观测模型与量化信息、Ollama/Python/平台版本；独占创建 |
| session-*.json | 每次启动/恢复观测到的服务版本和模型 digest；独占创建 |
| request_attempts.jsonl | HTTP 打开前追加的尝试记录，含中断请求；目录检查不计模型推理 |
| raw_results.jsonl | 每条完整样本原文、响应、解析、Schema、Validator、Guard、计时和参考诊断；追加后 fsync |
| warmup.json | 独立首次 warm-up，不计语义样本和延迟分布；独占创建 |
| raw_results.json | 已完成样本快照，从 JSONL 原件派生 |
| results.csv | 逐条工程状态及人工复核状态；使用 UTF-8 BOM，转义公式起始符 |
| metrics.json | 逐层比例、明确分子分母、来源隔离、延迟与模型加载耗时 |
| run_status.json | 完成/中断/阻塞状态与计划数、完成数、当前请求 |
| failures.json | 实际拒绝/失败的阶段和原因；运行阻塞另标 not_a_model_sample |
| evaluation_report.md | 实际环境、类别汇总、指标、典型实际案例及能力边界 |

尚无完整模型样本时，`raw_results.json=[]`，率和延迟为 `null`，报告没有虚构案例。JSONL 仅在有对应事件时创建。派生视图可原子刷新，原件不覆盖；中断后完整样本保留，HTTP 尝试单独保留。已知思考字段/标签在持久化前移除，同时保存移除前响应的 SHA。

`COMPLETED` 或退出码 0 只代表计划样本已记录，不代表真实模型准确率、工程层全通过或可执行。预期拒绝样本保留为诊断，不自动视为模型失败；坏 JSON 不算正确拒绝。初始参考未获人工确认，语义准确率应为 `null`。

具体 WSL 命令、10 条 pilot 前置条件、60 条运行、恢复和每项指标口径见 [LOCAL_USAGE.md](../LOCAL_USAGE.md)。本工具不发布报告、不提交代码，也不调用机器人控制接口。
