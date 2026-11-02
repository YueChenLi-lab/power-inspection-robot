# 边缘模拟任务系统架构

[首页](../README.md) · [模块边界](MODULE_BOUNDARIES.md) · [验收记录](VALIDATION_REPORT.md)

当前版本是 Python / SQLite 单机 Mock 运行时，未接真实硬件、台账、SCADA 或生产云端。ASR 原实验室保持独立；原有硬件控制源码不在此仓库。本地 Ollama Provider 已实现和完成 Mock HTTP 验证，真实 Qwen3 尚未实测。

```mermaid
flowchart TD
    IN[手动文本 / 既有语音实验室] --> B[InspectionBrain v2 / v3]
    B --> P[规则 / Mock / Ollama原生Provider]
    P --> V[原Schema与Evidence Validator]
    V --> G[SafetyGuard：不可执行草案]
    G --> A[BrainAdapter：重新校验与Mock白名单映射]
    A --> M[Mission Manager / State Machine]
    M --> S[Scheduler：单Worker，优先级FIFO]
    S --> SAFE[独立Safety Supervisor]
    SAFE --> W[Worker / Executor：可终止子进程]
    W --> K[三个Mock Skill]
    M --> DB[(SQLite：任务、事件、审批、执行)]
    K --> DB
    DB --> O[事务Outbox]
    O --> N[可复现网络模拟器]
    N --> R[(Mock远端SQLite inbox去重)]
    DB --> C[Collector / 有界Buffer / BatchWriter]
    C --> E[(证据SHA256与Evidence Outbox)]
    E --> O
    DB --> T[Trace与Metrics / Benchmark / SVG]
    DB --> REC[显式Recovery：幂等重试或人工复核]
    REC --> M
    H[真实硬件、真实云端：未接入]
    classDef external fill:#eeeeee,stroke:#666,stroke-dasharray:5 5;
    class H external;
```

执行权来自可信的本地注册元数据和独立操作员审批，不来自 Brain 输出。这里的“执行”只指模拟业务函数；草案原有 `executable=false` 等字段不会变成硬件授权。

## 实际实现与局限

- `InspectionBrain/brain_v3/ollama.py`：Ollama `/api/chat`、`format=SCHEMA`、非流式 JSON、超时与有界原响应诊断。
- `InspectionOS/`：独立任务内核、Mock Skills、运行隔离、持久化与恢复；不依赖模型即可运行。
- `observability/`：任务/事件追踪、真实本地计时、最近秩百分位、单 Worker 性能实验。
- `data_pipeline/`：证据采集、背压、批写、延迟同步、保留策略与 SHA-256。

不支持分布式调度、真实物理副作用、任意复杂语义到任务 DAG 的自动执行或硬件安全认证。跨 Skill 复合请求、未解析时间、未知设备映射和条件请求会明确拒绝并要求进一步分解或澄清。
