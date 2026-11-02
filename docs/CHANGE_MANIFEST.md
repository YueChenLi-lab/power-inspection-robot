# 本轮修改文件清单

基线为合并文档 PR #1 后的 origin/main。所有新执行功能只运行 Mock；未删除文件、未改原测试、v2 或语音实验室源码。

| 状态 | 文件 |
|---|---|
| 修改 | `.gitignore` |
| 修改 | `InspectionBrain/brain_v3/config.py` |
| 新增 | `InspectionBrain/brain_v3/ollama.py` |
| 修改 | `InspectionBrain/brain_v3/providers.py` |
| 新增 | `InspectionOS/__init__.py` |
| 新增 | `InspectionOS/__main__.py` |
| 新增 | `InspectionOS/app.py` |
| 新增 | `InspectionOS/brain_adapter.py` |
| 新增 | `InspectionOS/core/__init__.py` |
| 新增 | `InspectionOS/core/mission_manager.py` |
| 新增 | `InspectionOS/core/safety_supervisor.py` |
| 新增 | `InspectionOS/core/scheduler.py` |
| 新增 | `InspectionOS/core/skill_registry.py` |
| 新增 | `InspectionOS/core/state_machine.py` |
| 新增 | `InspectionOS/runtime/__init__.py` |
| 新增 | `InspectionOS/runtime/executor.py` |
| 新增 | `InspectionOS/runtime/recovery.py` |
| 新增 | `InspectionOS/runtime/worker.py` |
| 新增 | `InspectionOS/simulation/__init__.py` |
| 新增 | `InspectionOS/simulation/fault_injector.py` |
| 新增 | `InspectionOS/simulation/network_simulator.py` |
| 新增 | `InspectionOS/simulation/scenario_runner.py` |
| 新增 | `InspectionOS/skills/__init__.py` |
| 新增 | `InspectionOS/skills/contracts.py` |
| 新增 | `InspectionOS/skills/mock/__init__.py` |
| 新增 | `InspectionOS/skills/mock/alarm_query.py` |
| 新增 | `InspectionOS/skills/mock/data.py` |
| 新增 | `InspectionOS/skills/mock/reinspection.py` |
| 新增 | `InspectionOS/skills/mock/temperature_query.py` |
| 新增 | `InspectionOS/storage/__init__.py` |
| 新增 | `InspectionOS/storage/database.py` |
| 新增 | `InspectionOS/storage/repositories.py` |
| 修改 | `README.md` |
| 新增 | `data_pipeline/__init__.py` |
| 新增 | `data_pipeline/batch_writer.py` |
| 新增 | `data_pipeline/buffer.py` |
| 新增 | `data_pipeline/collector.py` |
| 新增 | `data_pipeline/integrity.py` |
| 新增 | `data_pipeline/retention.py` |
| 新增 | `data_pipeline/sync_manager.py` |
| 新增 | `docs/ADR/0001-single-machine-runtime.md` |
| 修改 | `docs/ARCHITECTURE.md` |
| 新增 | `docs/DATA_PIPELINE.md` |
| 新增 | `docs/FAULT_INJECTION.md` |
| 新增 | `docs/IMPLEMENTATION_PLAN.md` |
| 新增 | `docs/INSPECTION_OS_DESIGN.md` |
| 新增 | `docs/MISSION_STATE_MACHINE.md` |
| 新增 | `docs/MODULE_BOUNDARIES.md` |
| 新增 | `docs/OBSERVABILITY.md` |
| 新增 | `docs/OFFLINE_AUTONOMY.md` |
| 新增 | `docs/PERFORMANCE_REPORT.md` |
| 新增 | `docs/QWEN3_INTEGRATION.md` |
| 新增 | `docs/SAFETY_MODEL.md` |
| 新增 | `docs/SKILL_CONTRACTS.md` |
| 新增 | `docs/SYSTEM_ARCHITECTURE.md` |
| 新增 | `docs/VALIDATION_REPORT.md` |
| 新增 | `docs/experiments/benchmark/batch-writes.json` |
| 新增 | `docs/experiments/benchmark/c1-l0-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c1-l0.005-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c1-l0.02-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c4-l0-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c4-l0.005-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c4-l0.02-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c8-l0-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c8-l0.005-events.jsonl` |
| 新增 | `docs/experiments/benchmark/c8-l0.02-events.jsonl` |
| 新增 | `docs/experiments/benchmark/concurrency.svg` |
| 新增 | `docs/experiments/benchmark/environment.json` |
| 新增 | `docs/experiments/benchmark/latency-percentiles.svg` |
| 新增 | `docs/experiments/benchmark/measurements.json` |
| 新增 | `docs/experiments/benchmark/network-recovery.svg` |
| 新增 | `docs/experiments/benchmark/provider-comparison.svg` |
| 新增 | `docs/experiments/benchmark/stage-distributions.svg` |
| 新增 | `docs/experiments/faults/E1/events.jsonl` |
| 新增 | `docs/experiments/faults/E1/network.jsonl` |
| 新增 | `docs/experiments/faults/E1/result.json` |
| 新增 | `docs/experiments/faults/E2/events.jsonl` |
| 新增 | `docs/experiments/faults/E2/network.jsonl` |
| 新增 | `docs/experiments/faults/E2/result.json` |
| 新增 | `docs/experiments/faults/E3/events.jsonl` |
| 新增 | `docs/experiments/faults/E3/network.jsonl` |
| 新增 | `docs/experiments/faults/E3/result.json` |
| 新增 | `docs/experiments/faults/E4/events.jsonl` |
| 新增 | `docs/experiments/faults/E4/network.jsonl` |
| 新增 | `docs/experiments/faults/E4/result.json` |
| 新增 | `docs/experiments/faults/E5/events.jsonl` |
| 新增 | `docs/experiments/faults/E5/network.jsonl` |
| 新增 | `docs/experiments/faults/E5/result.json` |
| 新增 | `docs/experiments/faults/E6/events.jsonl` |
| 新增 | `docs/experiments/faults/E6/network.jsonl` |
| 新增 | `docs/experiments/faults/E6/result.json` |
| 新增 | `docs/experiments/faults/E7/events.jsonl` |
| 新增 | `docs/experiments/faults/E7/network.jsonl` |
| 新增 | `docs/experiments/faults/E7/result.json` |
| 新增 | `docs/experiments/faults/summary.json` |
| 新增 | `docs/experiments/validation/mock-semantic.json` |
| 新增 | `docs/experiments/validation/new-tests.log` |
| 新增 | `docs/experiments/validation/node-final.log` |
| 新增 | `docs/experiments/validation/original-baseline.log` |
| 新增 | `docs/experiments/validation/original-final.log` |
| 新增 | `docs/experiments/validation/real-ollama-unavailable.json` |
| 新增 | `docs/experiments/validation/unified-validation.log` |
| 新增 | `observability/__init__.py` |
| 新增 | `observability/benchmark.py` |
| 新增 | `observability/instrumentation.py` |
| 新增 | `observability/metrics.py` |
| 新增 | `observability/report.py` |
| 新增 | `observability/tracing.py` |
| 新增 | `tests/fixtures/semantic_cases.json` |
| 新增 | `tests/test_e2e.py` |
| 新增 | `tests/test_faults.py` |
| 新增 | `tests/test_observability.py` |
| 新增 | `tests/test_ollama.py` |
| 新增 | `tests/test_pipeline.py` |
| 新增 | `tests/test_runtime.py` |
| 新增 | `tools/brain_smoke.py` |
| 新增 | `tools/validate.py` |
| 新增 | `docs/CHANGE_MANIFEST.md`（本清单） |

## 可靠性 Follow-up 文件与影响范围

基线 fdc997e；PR #2 实际已合并，经用户选择从同一分支建立后续 Draft PR #3。无原 v2、voice_lab 或原测试源码修改；原实验数据未覆盖。

| 状态 | 文件 | 修改原因 / 影响范围 |
|---|---|---|
| 新增 | `.github/workflows/mock-runtime.yml` | 普通无模型 CI，运行核心/原回归/Node 和故障实验 |
| 修改 | `InspectionBrain/brain_v3/ollama.py` | 区分传输、超时、JSON 与响应合同诊断 |
| 修改 | `InspectionOS/core/mission_manager.py` | 严格布尔审批、凭据边界与待执行授权撤销 |
| 修改 | `InspectionOS/core/safety_supervisor.py` | 严格布尔审批、凭据边界与待执行授权撤销 |
| 修改 | `InspectionOS/core/scheduler.py` | 事务外网络预检查与状态/审批重新核验 |
| 修改 | `InspectionOS/core/skill_registry.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `InspectionOS/core/state_machine.py` | 定义待执行任务撤销审批的合法迁移 |
| 修改 | `InspectionOS/runtime/executor.py` | 共享重试判定、错误原因与输入关联输出验证 |
| 修改 | `InspectionOS/runtime/recovery.py` | 共享重试判定、错误原因与输入关联输出验证 |
| 新增 | `InspectionOS/runtime/retry_policy.py` | Worker/Recovery/Scheduler 共享恢复与副作用策略 |
| 修改 | `InspectionOS/runtime/worker.py` | 共享重试判定、错误原因与输入关联输出验证 |
| 修改 | `InspectionOS/simulation/scenario_runner.py` | 明确 E5/E6 定义并在新运行中记录修订版本 |
| 修改 | `InspectionOS/skills/contracts.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `InspectionOS/skills/mock/alarm_query.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `InspectionOS/skills/mock/data.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `InspectionOS/skills/mock/reinspection.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `InspectionOS/skills/mock/temperature_query.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 新增 | `InspectionOS/skills/mock/validation.py` | 按 Skill 的设备集合、时间与 Mock 来源业务合同 |
| 修改 | `README.md` | 工程设计演进、恢复/调度图、前后对照与当前状态 |
| 修改 | `docs/FAULT_INJECTION.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 新增 | `docs/HISTORICAL_TEST_ASSETS.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/INSPECTION_OS_DESIGN.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/MISSION_STATE_MACHINE.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/OBSERVABILITY.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/OFFLINE_AUTONOMY.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/PERFORMANCE_REPORT.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/QWEN3_INTEGRATION.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 新增 | `docs/RELIABILITY_FOLLOWUP.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/SAFETY_MODEL.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/SKILL_CONTRACTS.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/SYSTEM_ARCHITECTURE.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 修改 | `docs/VALIDATION_REPORT.md` | 与实际合同、故障定义、CI、验证和性能一致的技术说明 |
| 新增 | `docs/experiments/faults/REVISION_FOLLOWUP.md` | 对旧 E5/E6 文字增加独立修订说明，不改旧事件和时间戳 |
| 新增 | `docs/experiments/followup-v1/actions-result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c1-l0-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c1-l0.005-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c1-l0.02-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c4-l0-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c4-l0.005-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c4-l0.02-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c8-l0-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c8-l0.005-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/c8-l0.02-events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/concurrency.svg` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/environment.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/latency-percentiles.svg` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/measurements.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/network-recovery.svg` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/provider-comparison.svg` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/benchmark/stage-distributions.svg` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E1/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E1/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E1/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E2/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E2/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E2/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E3/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E3/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E3/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E4/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E4/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E4/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E5/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E5/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E5/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E6/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E6/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E6/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E7/events.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E7/network.jsonl` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/E7/result.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/faults/summary.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/history-search.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/original-ci-local-summary.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/original-ci-local.log` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/performance_report-before.md` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/scheduler-timings.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/semantic-mock.json` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/strict-validation.log` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `docs/experiments/followup-v1/validation_report-before.md` | 新运行原始数据/日志/图表及上轮报告字节快照；不覆盖旧数据 |
| 新增 | `tests/test_business_contracts.py` | 新增针对性拒绝、组合矩阵与并发竞态测试 |
| 新增 | `tests/test_evaluation_layers.py` | 新增针对性拒绝、组合矩阵与并发竞态测试 |
| 修改 | `tests/test_ollama.py` | 新增针对性拒绝、组合矩阵与并发竞态测试 |
| 新增 | `tests/test_reliability.py` | 新增针对性拒绝、组合矩阵与并发竞态测试 |
| 修改 | `tools/brain_smoke.py` | 独立证据指标与显式历史资产 CI 前置条件 |
| 新增 | `tools/evidence_metrics.py` | 独立证据指标与显式历史资产 CI 前置条件 |
| 新增 | `tools/test_assets.py` | 独立证据指标与显式历史资产 CI 前置条件 |
| 修改 | `tools/validate.py` | 独立证据指标与显式历史资产 CI 前置条件 |
| 修改 | `docs/CHANGE_MANIFEST.md` | 保留初始清单并追加本轮原因及范围 |
