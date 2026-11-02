# 边缘任务运行时实施计划与基线审计

## Stage 0 审计

仓库当前仅含 InspectionBrain；没有底盘、导航、摄像头、云台控制源码，本次不补造这些接口。原文档 PR #1 已合并，开发分支从该 main 继续。

现有链路：voice_lab → LocalASR / 手动文本 → ElectricalBrainV2 → build_evidence → Provider → SemanticValidator → SafetyGuard → SemanticStore。v2 默认不调用模型，v3 只产生不可执行草案。Mock 复制契约证据；RulesFallback 采用规则证据；OpenAICompatible 使用 Chat Completions JSON object。Validator 精确保护原文区间和设备、数值、时间、否定、条件关系，SafetyGuard 重建草案并强制无硬件权限。mission.py 不是任务内核。

依赖：核心 Python >=3.10，无第三方必需依赖；Node 用于原浏览器模拟测试；SenseVoice 为独立可选模型环境。ASR 模型和 Ollama 不在本 checkout 中。localhost:11434 探测连接拒绝，真实 Qwen3 推理不具备当前运行条件。

## 顺序与取舍

1. P0：新增 Ollama 原生 Schema Provider，复用原 SemanticEngine / Validator；Mock HTTP、T1–T5、独立 smoke 与分段计时。
2. P1：SQLite 事务事件、严格状态机、独立安全策略、注册合同、单 Worker 和有界重试；Skill 子进程提供可终止超时，不使用无法终止的线程作为执行隔离。
3. P2：可复现网络模拟、事务 outbox、显式恢复；不确定非幂等执行进入人工复核，不无条件重跑。
4. P3：持久化 trace、阶段耗时、实际 benchmark 与 SVG 图；ASR 和真实 Qwen3 未接入指标保持空。
5. P4：有界证据缓冲、SQLite / JSONL 批写、SHA256、审计保护与诊断轮转；同步复用 outbox。
6. 集成：Brain 适配层重新验证语义，只映射白名单 Mock 查询；不采信模型权限，运行完整回归、E1–E7 和 A–C。

每阶段先运行测试再提交；不更改原测试、不删除历史记录、不引入重型框架。该系统为单机模拟运行时，不宣称真机自治或 Exactly-once。

## 基线

基线命令及实际计数见最终 VALIDATION_REPORT.md。默认沙箱不允许 socket，HTTP 测试需要允许本地 socket 的执行上下文；首次根目录直接 discover 缺少原项目 import 路径，正确方式是在 InspectionBrain 目录运行。Node 原有四个测试文件通过。所有最终报告区分跳过与通过。
