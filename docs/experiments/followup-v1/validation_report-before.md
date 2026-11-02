# 本轮实现与验收记录

## 执行范围

分支 `feature/edge-task-runtime`，从已经合并文档 PR #1 的 main 继续。原 InspectionBrain 不重写；只扩展 Provider 配置与工厂，新增原生 Ollama 文件。原 v2、ASR、语音服务、原测试、示例历史与文档均保留。仓库没有底盘/导航/摄像头/云台控制源码，本轮没有创建或接入这些执行接口。

## 测试结果

| 套件 | 实际结果 | 边界 |
|---|---|---|
| 原 Python 基线 | 121 项：111 通过、6 错误、4 跳过 | 6 项缺历史文件，4 项需真实 ASR 模型/音频 |
| 原 Python 最终回归 | 121 项：111 通过、同样 6 错误、4 跳过 | 没有新增错误；不能称整套全通过 |
| 原 Node 模拟测试 | 4 个文件中的 19 项检查通过 | 浏览器流程模拟，不是实际浏览器麦克风测试 |
| 新增 Python | 31 项通过 | 包含模块、HTTP、集成、E2E 与故障注入；部分测试内含多组子场景 |
| E1–E7 独立实验 | 7/7 通过 | 单机软件模拟与进程故障，非现场硬件验收 |
| 性能实验 | 9 组 × 12 任务，恢复后 108/108 完成 | 一个 Worker、并发提交 1/4/8、模拟网络 |
| 真实 Ollama smoke | 3 请求、0 接受 | 本地服务连接失败，真实模型未验证 |

统一测试命令 `python3 tools/validate.py` 已实际运行，退出码为 1；内部新套件 / 原套件 / Node 返回 `[0, 1, 0]`，如实保留原缺文件失败，见[统一日志](experiments/validation/unified-validation.log)。此入口重定向原可选 ASR 测试的报告写入，不覆盖历史报告。

原始记录：[原基线](experiments/validation/original-baseline.log)、[原最终回归](experiments/validation/original-final.log)、[Node](experiments/validation/node-final.log)、[新增套件](experiments/validation/new-tests.log)、[故障汇总](experiments/faults/summary.json)、[真实模型不可用记录](experiments/validation/real-ollama-unavailable.json)。

### 原有 6 项错误

- test_domain_v2 的 test_multi_intent_and_real_cases、test_real_data_rules_and_switch_are_separate。
- test_round2_audit 的 test_actual_export_is_read_and_preserved。
- test_round2_scoring 的 test_complex_query_does_not_claim_complete_answer_from_one_keyword、test_import_preserves_history_and_excludes_unbound_old_metrics。
- test_scoring_workflow 的 test_actual_record_without_reference_leakage。

前五项依赖根目录未提交的 voice-evaluation.json；第六项依赖 InspectionBrain/runtime/voice_lab/records/9bf3bee5bf3e48e3b60a3a33d6966bc5.json。未生成假样本，也未跳过或删除这些测试。若恢复原始已授权历史文件，可重跑验证。

## 分阶段验收

- Stage 0：审计与基线已记录，见[实施计划](IMPLEMENTATION_PLAN.md)。默认沙箱不允许 socket 的错误在允许 loopback 的执行上下文中重跑排除；首次根目录错误工作目录也已纠正。
- P0：原生 Ollama Schema Provider 和独立真实 smoke 可运行。T1–T3 验证原文、3号设备、上周、否定、自我修正和未解析时间；T4 拒绝非法 JSON、缺字段、类型、未知字段和枚举；T5 拒绝设备/时间/动作/否定冲突。Mock HTTP 不计为真实 Qwen3。
- P1：三类 Mock Skill、生命周期、优先级/FIFO、版本、幂等、审批与运动拒绝；SQLite 状态/事件/outbox 原子提交。独立任务运行不需要模型。
- P2：断网本地继续、远端等待，恢复重调度；ACK 丢失重投去重；幂等恢复、非幂等人工复核；真正执行期间进程 SIGKILL；SQLite 写失败、容量保护与审计保留。
- P3：trace、阶段计时、P50/P95/P99、均值、吞吐、失败/重试/利用率/超时/积压及真实 SVG 图。
- P4：Collector、背压、批写、JSONL 新文件导出、延迟同步、保护审计的保留策略、SHA256 篡改检测。
- 集成 A：文本 → v3 Mock 或 v2 → 原校验 → Mock 映射 → OS → Skill → 事务事件 → 证据 → 延迟同步。B：离线/恢复。C：执行进程崩溃/重启。

## 安全证据与限制

新增测试证明注册的非 Mock scope 或 motion 风险被拒绝，高风险未审批不领取，未知 Skill 不受理，模型授权字段为 true 被适配层拒绝。审批认证失败同样记录，网络恢复不能自动获得授权。执行中取消持久化且子进程回收，重试有预算；幂等键并发重提只创建一个任务。所有业务输出需 is_mock=true 和固定 Mock 来源。

这是可信本地代码和本地操作员边界，不是恶意插件安全沙箱、生产身份服务或整机认证。未完成：真实 Qwen3 推理与独立人工金标准、真实 ASR 到 OS 的音频入口、跨 Skill DAG 执行、多 Worker、真实云端同步、真实台账、Xavier 部署与真机控制。内存缓冲未提交证据不承诺耐崩溃，容量限制是 admission 保护而非物理磁盘配额，投递为 at-least-once。

后续先补真实模型与人工标注验收，并恢复原始历史测试资产；再在 Mock 环境扩展任务分解和外部身份/审批服务。未经独立设计与安全验收，不接硬件。
