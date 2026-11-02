# Power Inspection Robot · 电力巡检机器人

上海电力大学大学生创新创业训练计划（大创）项目，面向电力设备巡检的移动机器人软件与系统工程实践。项目曾作为上海电力大学大创项目代表，在 **2026 年中国国际工业博览会（工博会）**进行现场展示。

当前公开仓库以 [InspectionBrain](InspectionBrain/README.md) 语音与电力领域语义实验室为主。**理解查询意图不代表已接入真实业务系统，结构化任务草案不代表机器人可以执行任务。** InspectionOS v0.1 已新增单机 Mock 任务内核；真实硬件任务系统仍是后续建设目标。

## 项目背景与应用场景

目标场景包括变电站及电力设备巡检、设备运行状态查询、红外测温记录查询、历史测温比较、告警查询、自然语言语音交互，以及移动巡检、环境建图和巡检记录展示。这些是应用目标，并非全部已经实现。

当前查询演示使用明确标记的 Mock 台账、记录和示例知识。尚未接入真实 SCADA、DMS、EMS 或设备台账；模拟结果不能用于现场状态判定。

## 工博会展示经历

根据项目成员提供的现场经历，实验室中曾运行语音前进、后退、左转、右转及瞬时速度、角速度反馈；展厅复杂无线环境下，机器人与上位机通信及线上平台访问不稳定，语音控制和识别文本展示受到影响。团队重新启用手持遥控器进行人工控制，并保留自动建图、双摄像头相关视觉展示和部分巡检记录展示。

这些整机经历与当前公开仓库的离线语义原型属于不同证据范围，不能据此声称本仓库包含当时整机控制代码或已完成真机集成。完整分析见[工博会工程复盘](docs/EXHIBITION_REVIEW.md)。

## 硬件配置

以下设备名称和用途来自项目提供的信息；仓库未附完整硬件清单或实测规格。

| 设备 | 主要用途 | 系统位置 | 配置确认状态 |
|---|---|---|---|
| Scout 移动机器人底盘 | 承载与移动 | 硬件执行平台 | 系列已知；具体型号、速度、载荷与控制协议待补充 |
| NVIDIA Jetson AGX Xavier | 边缘计算 | 本地计算平台 | 平台名称已知；系统、部署环境及资源配置待补充 |
| RS16 激光雷达 | 环境感知与建图相关能力 | 感知层 | 名称已知；具体参数、驱动与建图关联待补充 |
| 双摄像头配置 | 现场视觉感知与展示 | 视觉感知层 | 具体型号、分辨率、视场角与安装位置待补充 |
| 海康云台摄像机相关设备 | 视频采集与云台控制 | 视频与云台设备层 | 具体型号、接口及与双摄像头的关系待补充，暂不合并 |
| 麦克风 | 采集语音指令 | 交互输入层 | 型号、采样配置和连接方式待补充 |
| 手持遥控器 | 人工接管与备用控制 | 人工控制通道 | 现场使用已说明；链路和接管优先级配置待补充 |
| 无线网络设备 | 机器人、上位机与控制平台通信 | 通信层 | 型号、拓扑、频段和协议待补充 |

不根据设备系列推定规格。建图传感器组合、算法、定位精度及红外干扰源均需以实际实现和测试核实。

## 核心技术与本人负责的工作

本人工作以机器人软件架构、智能语义理解和任务调度方向为主；整机硬件集成及现场保障为团队工作，不全部归于个人。

### InspectionBrain：语音与电力领域语义理解

负责语音输入与 ASR 接入、SenseVoice 本地识别实验、电力术语词库与规范化、转写纠错候选和原文保护，以及领域意图、设备实体、编号、时间、数值和否定关系处理。软件输出保留原文证据、不确定性和结构化任务草案，使用语义 Schema、Validator 与 SafetyGuard 约束输出。

纠错不是无条件改写：同音词、口误和复杂表达可能需要人工确认，设备编号也不自动成为真实设备身份。源码入口包括 [v2 领域语义](InspectionBrain/inspection_brain/domain_v2/service.py)和[本地 ASR](InspectionBrain/voice_lab/asr.py)。

### InspectionBrain v3：可替换文本模型探索

已有 Provider 抽象接口、Mock Provider、RulesFallback Provider、OpenAI Compatible Provider，以及结构化 JSON、原文证据验证和不可执行草案原型。Mock 是脚本化契约演示，RulesFallback 是规则回退，均不是真实模型推理。

据项目成员提供的信息，Qwen3 4B Instruct 已下载并通过 Ollama 命令行测试；**尚不能认定已完成 InspectionBrain v3 真实模型集成**。仍需验证模型输出能否通过现有 Schema 和 Validator，以及设备、数值、否定与条件关系是否保真。本项目没有训练专用电力大模型的成果声明。详见 [v3 技术说明](InspectionBrain/docs/V3.md)。

### InspectionOS：任务内核与后续设计

已实现 Mission Manager、Skill Registry、Scheduler、State Machine 和 Safety Supervisor 的模拟版本，负责任务生命周期、调度、状态及独立安全监督。当前已实现独立的单机 Mock 任务内核，包含事务持久化、状态机、排队、审批、超时、恢复与三个模拟 Skill；尚未接入真实硬件。

## 系统总体架构

下图表示当前可运行的模拟链路。真实 ASR 仍为独立可选实验，真实 Ollama / Qwen3 推理尚未在本环境验收。

```mermaid
flowchart TD
    T[文本 / 既有语音实验室] --> B[InspectionBrain v2 / v3 Provider]
    B --> V[JSON Schema / 完整语义Validator]
    V --> G[SafetyGuard：语义输出约束]
    G --> D[Mission Draft：不可执行草案]
    D --> A[BrainAdapter：重新验证与Mock设备映射]
    A --> M[Mission Manager / State Machine]
    M --> SAFE[独立Safety Supervisor：受理与领取均复核]
    SAFE --> S[Scheduler：短事务候选快照]
    S --> N[Network Preflight：写事务之外]
    N --> C[新事务：状态、版本、审批重新核验与领取]
    C --> REG[Skill Registry / 单Worker Runtime]
    REG --> K[三个Mock Skill / 可终止子进程]
    K --> OVAL[输出Schema / 业务一致性Validator]
    OVAL --> DB[(SQLite / Event Store / Outbox)]
    DB --> REC[Recovery：统一重试策略，不绕过审批]
    REC --> M
    DB --> SYNC[模拟网络 / Mock远端去重]
    DB --> OBS[Trace / Metrics / 数据管线]
```

## 软件模块划分

| 模块 | 职责 | 状态与边界 |
|---|---|---|
| InspectionBrain v2 / v3 | 规则语义、模型候选、原文证据校验、不可执行草案 | 原有能力保留；新增 Ollama 原生接口通过 Mock HTTP，真实模型待验证 |
| InspectionOS v0.1 | 任务、注册、审批、优先级 FIFO、截止时间和恢复 | 已实现单机 Mock 运行时，无真实设备权限 |
| Mock Skills | 告警查询、测温与比较、复检建议 | 三个可运行模拟 Skill，明确标记数据来源 |
| observability | trace、计时、指标、性能实验和 SVG 图 | 已实现本地模拟测量；ASR / 真实 Qwen3 指标未接入 |
| data_pipeline | 有界缓冲、批写、SHA256、Outbox 同步、保留与容量保护 | 已实现轻量实验；真实云端与审计归档未接入 |
| 真实适配器与控制 | 真实台账、现场数据和机器人动作 | 尚未建设，本轮未接硬件 |

[当前系统架构](docs/SYSTEM_ARCHITECTURE.md) · [模块边界](docs/MODULE_BOUNDARIES.md) · [OS 设计](docs/INSPECTION_OS_DESIGN.md)

## 工博会现场问题与工程经验

| 问题 | 现场表现 | 已采取措施 | 后续方向 |
|---|---|---|---|
| 语音交互 | 控制链路与识别文本展示不稳定 | 遥控器备用 | 本地化语音链路、分环节诊断 |
| 无线网络 | 通信中断、平台访问不稳定、控制受延迟影响 | 人工接管 | 独立局域网、质量监测、超时重连与离线运行 |
| 运动安全 | 通信延迟带来失控风险与载荷风险 | 底层停车保护、速度和转向限制 | 独立安全监督与故障注入验证 |
| 环境建图 | 自动建图及部分展示仍可运行 | 保留可用功能展示 | 多传感器稳定性验证 |
| 电梯红外干扰 | 进入电梯后电梯门无法正常关闭 | 记录现场问题 | 干扰源排查与兼容性测试 |

**通信延迟超过底层配置的安全阈值时触发停车保护，具体阈值以实际控制程序和配置为准。** 不将口述中不确定的 200ms 或 500ms 作为已验证参数。网络展示失败不能直接归因于 SenseVoice 识别准确率；电梯干扰机理也尚未确定。

机器人系统不能只追求运动控制的灵敏度，还必须考虑通信异常情况下的失效安全。详细事实、证据边界和验证建议见[现场复盘](docs/EXHIBITION_REVIEW.md)。

## 当前开发进度

| 模块 | 当前状态 | 证据范围 |
|---|---|---|
| SenseVoice ASR | 已有本地识别接口和既有实验记录 | 源码及原技术文档；当前 checkout 不包含模型，不代表已部署 Xavier |
| 电力术语规范化 | 已有规则实现 | 词库、规范化与原文保护代码 |
| InspectionBrain v2 | 已有领域语义分析 | 规则与示例知识、Mock 数据 |
| InspectionBrain v3 | Provider、Schema、Validator 原型及 Ollama 原生接入 | Mock HTTP 验收通过；真实 Qwen3 效果待验证 |
| Qwen3 4B Instruct | Ollama 命令行测试完成，真实项目接入待验证 | 项目成员提供的信息，非本仓库集成验收 |
| Mission Manager / Skill Registry | 已有独立 Mock 内核实现 | 新模块位于 InspectionOS；原 mission.py 草案协议保留 |
| Evaluation Lab v0.1 | 浏览器评测平台已实现；真实 Smoke BLOCKED，人工评测 PENDING | 独立存储与逐层检查，未计真实模型效果 |
| InspectionOS | v0.1 单机 Mock 任务内核可运行 | 非真实硬件 OS、非分布式集群 |
| 真实设备台账接入 | 待建设 | 当前为 Mock |
| 真实巡检记录查询 | 待建设 | 当前为 Mock，现场记录展示不等于此仓库已接真实数据 |
| 完整自主任务执行 | 未实现 | 公开语义链路不能执行机器人动作 |

## 工程设计与可靠性演进

本轮在原任务运行时上修复异常路径与执行合同，仍是单 Worker、全 Mock 的研究原型。下面记录设计为什么变化，以及如何验证；没有新增真机权限或生产身份系统。

### 任务恢复：允许重试不等于重复执行安全

原 Worker 检查 `retryable`，Recovery 却漏查，导致崩溃路径可能重跑明确禁止重试的 Skill。现在 Worker、Recovery 和退避后调度共用 `retry_decision`：`retryable` 表示允许重试，`idempotent` 表示重复执行效果合同；还必须版本一致、预算剩余、状态允许且没有未解决审批。

即使声称幂等，结果不确定也不能自动证明外部副作用安全。本版本只对显式 `recovery_safe=true` 的可信 Mock 只读能力自动恢复；其余不确定结果进入 `WAITING_APPROVAL` 并清除批准位，独立操作员先复核。禁止重试、版本改变或预算耗尽会安全失败，已取消任务不重跑。

```mermaid
flowchart TD
    R[失败 / 重启后结果不确定] --> S{状态与安全审批允许?}
    S -->|否| STOP[失败或等待独立人工复核，记录原因]
    S -->|是| C{retryable、幂等、版本一致、预算剩余?}
    C -->|否| STOP
    C -->|是| E{不确定结果是否显式声明可安全恢复?}
    E -->|否| REVIEW[WAITING_APPROVAL，清除批准位]
    E -->|可信Mock只读合同| RETRY[RETRY_WAIT，退避后再次校验]
```

### Scheduler：网络等待退出写事务

SQLite `BEGIN IMMEDIATE` 持有写锁，事务内请求网络会把一次超时扩散为其他任务无法写入。现在先在短事务中读取候选，再释放事务和连接锁进行 Network Preflight，最后开启新事务重读任务。必须重新检查状态、快照版本 `updated_at`、Skill 版本及审批；网络恢复不代表仍有执行资格。

```mermaid
flowchart TD
    T1[事务1：准备候选并读取快照] --> COMMIT1[提交并释放写锁]
    COMMIT1 --> NET[事务外：网络预检查，可等待 / 超时]
    NET --> T2[事务2：按任务ID重新读取]
    T2 --> CHECK{仍排队、快照未失效、版本和审批有效?}
    CHECK -->|否| SKIP[放弃旧预检查结果，不领取]
    CHECK -->|是且网络失败| WAIT[WAITING_NETWORK]
    CHECK -->|是且允许执行| CLAIM[原子RUNNING与execution-start]
```

并发预检查可以重复，但原子状态核验保证同一任务只领取一次。测试在网络被阻塞时使用另一条 SQLite 连接提交任务，并覆盖期间取消、撤销审批和并发 claim；网络等待、事务时长与提交时长的[实测记录](docs/experiments/followup-v1/scheduler-timings.json)分开保存。

### 审批：严格 bool 与本地凭据边界

Python 的非空字符串 `"false"` 为 truthy，不能代表布尔 False。`approve()` 现在只接受真正的 `bool`；`"false"`、`"true"`、`1`、`None` 在审批逻辑前拒绝。actor 和 token 必须是非空文本，已取消、终态或已处理的任务不能重复批准；批准、拒绝和凭据失败具有审计记录。

actor 是本地调用方给出的审计标签，不等于已经认证的用户身份；token 只验证本地操作员凭据。当前仍是 Mock 审批机制。Safety Supervisor 独立于 LLM，运动或非 Mock scope 始终拒绝，Recovery 不能替模型授予审批。

### Skill 合同：Schema 之后验证业务一致性

JSON Schema 能限制结构与类型，不能独自证明查询对象正确。例如“请求 CB-003、返回 CB-001”可能结构合法，仍必须拒绝；本仓库实际 ID 使用 `MOCK-CB-3` / `MOCK-TR-1`，不冒充真实资产编号。

```text
输入 device_id=MOCK-CB-3 → 输出 device_id=MOCK-TR-1
                        → JSON Schema 通过
                        → 业务 Validator 拒绝：输出设备集合不匹配
                        → 任务不会 SUCCEEDED
```

Registry 在输入/输出 Schema 之后调用具体 Skill 的业务校验钩子。单设备身份必须一致，多设备用明确的允许集合，所有记录不得属于未请求设备；记录时间必须落在带时区的 `[start,end)` 内，Mock 输出与每条记录都须保留固定来源。测温比较按设备分组。不同 Skill 家族可以有不同业务字段，不给所有 Skill 强加同一记录格式。

### 模型评测：分层指标与独立证据检查

```text
模型输出 → JSON Parse → JSON Schema → 完整 Validator
                                      ↓
                           独立 Evidence Constraint 检查
                                      ↓
                           独立人工 Gold Annotation（如有）
                                      ↓
                           人工语义正确率（当前为 null）
```

JSON 合法不代表语义正确，Schema 通过不代表证据一致，完整 Validator 接受也不代表现场事实成立。本轮移除了重复计算的旧 evidence 指标：新检查独立定位原文 source_span，核对设备编号、数值/单位、时间、否定、自我修正和条件，不复用 `validation.valid`。

JSON 解析、Schema、完整 Validator 与证据指标分别保存分母；无观测返回 `null`。传输失败、模型超时和 JSON 解析失败分别计数。Mock 没有真实传输解析时不填假解析率，也不计为真实模型效果。语义准确率仍需人工确认 Gold，ASR 转写不能充当语义金标准。

### E5 / E6：明确两种故障模型

- **E5：任务领取后运行时重建**。关闭 Application 后在同一父进程重开数据库，验证持久化恢复；没有杀死 Worker 进程。
- **E6：Worker 执行期间进程强制终止**。在 Mock Skill execute 内 SIGKILL 实验 Worker 子进程，再重启验证恢复。

编号保持不变；历史数据和时间戳保留，通过[修订说明](docs/experiments/faults/REVISION_FOLLOWUP.md)纠正旧文字，新运行另存日志。

### 修改前后对照

| 工程模块 | 原有问题 | 修改后设计 | 验证方式 |
|---|---|---|---|
| Recovery | 重试策略不一致 | 统一策略及不确定副作用复核 | Worker/Recovery 同组合矩阵 |
| Scheduler | 网络请求占用写事务 | 网络预检查与事务解耦，重新核验状态 | 独立连接提交、取消/撤销竞态、并发 claim |
| Safety Approval | truthy 输入可能被批准 | 严格 bool 与非空凭据、重复/终态拒绝 | 非法类型与审计测试 |
| Skill Contract | 仅检查 Schema | 设备集合、记录、时间和来源业务校验 | Schema 通过但业务错误的拒绝测试 |
| Model Evaluation | evidence 与完整 Validator 指标重复 | 独立证据检查、分母和 unavailable | 指标可产生不同结果的测试 |
| Fault Simulation | E5 文字易误解为进程崩溃 | E5 重建、E6 SIGKILL；保留原始数据 | E1–E7 重新运行 |

### 当前能力边界

| 能力 | 当前状态 |
|---|---|
| InspectionBrain v2 | 已实现，原核心行为保留 |
| InspectionBrain v3 Provider | 接口已实现，真实模型验收另记 |
| Qwen3 4B | 真实项目效果尚未完成验收 |
| InspectionOS / SQLite / 单 Worker | Mock 运行时原型，已实现持久化和单 Worker |
| 多 Worker | 尚未实现 |
| 弱网模拟 / Outbox | 已实现，模拟远端、至少一次投递 |
| 进程恢复 | 已实现统一策略；不确定效果先复核 |
| 真实设备台账 / 真实巡检数据库 | 未接入 |
| 真机执行 / 生产部署 | 未接入、未验收 |

CI 实际执行核心测试，历史资产缺失和外部模型条件单独报告，不把 skipped 当 passed。详细依据见[可靠性修复说明](docs/RELIABILITY_FOLLOWUP.md)、[验收报告](docs/VALIDATION_REPORT.md)和[历史资产说明](docs/HISTORICAL_TEST_ASSETS.md)。

## InspectionBrain v3 · 真实模型评测实验室

规则能保护已知术语与原文证据，但复杂表达、关系和多意图仍需要真实文本模型的可重复验证。Evaluation Lab v0.1 提供本地浏览器实验台，用 Ollama 运行用户已安装的模型；Provider 隔离模型协议，现有 SemanticEngine、Schema、Validator 和 SafetyGuard 保持职责不变，不开发新的 Agent 框架。

```mermaid
flowchart TD
    U[用户电力巡检指令] --> E[InspectionBrain v3 SemanticEngine]
    E --> P[Provider API]
    P --> M[Mock：显式离线对照]
    P --> R[Rules：显式规则对照]
    P --> O[Ollama Native：完整JSON Schema约束]
    O --> Q[用户选择的已安装Qwen3等文本模型]
    Q --> J[原始响应 / JSON解析]
    M --> J
    R --> J
    J --> S[JSON Schema]
    S --> V[原Evidence / Semantic Validator]
    V --> G[独立SafetyGuard]
    G --> D[不可执行Task Draft]
    D --> DB[(独立评测SQLite / 人工标注)]
    DB --> UI[四页仪表盘 / 历史 / JSON、CSV、Markdown]
```

Ollama 的 Schema 约束帮助生成结构合法的 JSON，但不能保证业务关系正确。Validator 继续核验原文区间、设备编号、数值/单位、时间、否定、自我修正和依赖；独立 SafetyGuard 强制 `authorized=false`、`executable=false`、`hardware_commands_enabled=false`。ACCEPTED 仅表示通过当前工程检查，既不是人工语义正确结论，也不是任务执行授权。平台不导入 InspectionOS，不提供机器人、审批或执行接口。

平台包含模型连接与已安装模型选择、单条逐层结果、顺序批量进度、按来源/模型配置分组的统计，以及历史筛选、独立人工标注和三种导出。12 条电力领域测试用例的独立期望全部 `pending`，不发送给模型、不自动改写为 Gold。模型不可用会保存 PROVIDER_ERROR，不会自动切换 Mock。

| 指标 | 分母 / 含义 |
|---|---|
| Request Success | 完整响应 / 全部请求 |
| JSON Parse | 成功解析 / 完整响应 |
| Schema Pass | 结构通过 / 成功解析 |
| Validator Acceptance | 完整 Validator 接受 / Schema 通过 |
| 人工 Evidence Consistency | 人工确认一致 / 已标注证据样本 |
| Semantic Accuracy | 人工确认正确维度 / 已标注维度 |
| Latency | 实际端到端耗时均值、P50/P95、样本量和分布 |

无分母或无人工标注时显示 `null`，工程证据检查与人工一致性单列。REAL LLM、MOCK、RULES 分组，错误、候选安全违规和实际回退分别计数；规则对照不冒充真实推理。Ollama 原生纳秒耗时正确转为毫秒，记录加载、推理及 Token 数。已知 thinking/reasoning 字段在保存前剔除，原文输入不改写。

从仓库根目录启动（无需新增第三方依赖）：

```bash
# 必须在后端能够访问本地 Ollama 的机器运行
# 如不设置 OLLAMA_MODEL，可在页面检查连接后选择已安装模型
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_MODEL=qwen3:4b-instruct \
python3 InspectionBrain/run_evaluation_lab.py
```

在本机浏览器输入 `http://127.0.0.1:8891/`，点击“检查 Ollama”，选择已安装模型后运行。前端只请求实验室后端，默认仅监听 loopback，不开放 11434。Ctrl+C 停止；独立评测库位于 `InspectionBrain/runtime/evaluation_lab/`，不覆盖旧语音/语义记录。

```bash
# 五类真实 Smoke Test：设备纠正、禁止约束、数值、多意图、模糊表达
OLLAMA_MODEL=qwen3:4b-instruct \
python3 InspectionBrain/run_evaluation_smoke.py --output /tmp/qwen3-real-smoke-new.json
```

| 验收层级 | 本次状态 |
|---|---|
| 真实模型调用接口、浏览器评测与工程异常处理 | 已实现，Mock HTTP / 本地 Web 测试通过 |
| 真实 Qwen3 Smoke Test | **BLOCKED**：当前云机 Ollama 不可访问，五类请求无完整响应 |
| 独立人工语义评测 | **PENDING**：12 条用例未确认 Gold，不计算准确率 |

用户本机已下载模型，不表示本云机的 loopback 服务可访问。平台可在具备 Ollama 和模型的同一机器运行；当前没有训练、微调、GPU 优化或真机集成。设计与步骤见[OLLAMA_EVALUATION](docs/OLLAMA_EVALUATION.md)，实际结果见[OLLAMA_EVALUATION_RESULTS](docs/OLLAMA_EVALUATION_RESULTS.md)。

## 后续技术路线

1. **Phase 1 · InspectionBrain v3**：接入真实文本模型，验证 Qwen3 结构化 JSON、Schema、原文证据、设备与数值关系、否定、自我修正和条件约束；记录拒绝、回退与实际耗时。
2. **Phase 2 · InspectionOS v0.1**：已建立 Python 单机 Mock 任务内核，包含 Mission Manager、Skill Registry、Scheduler、State Machine、Safety Supervisor；后续继续扩展，不直接控制真实硬件。
3. **Phase 3 · 模拟巡检任务系统**：已提供告警查询、红外测温与比较、复检建议三类 Mock Skill；后续完善复合任务分解，模拟结果始终标识来源。
4. **Phase 4 · 硬件适配与可靠性**：逐步验证本地网络自治、控制接口适配、传感器接入、执行监控、故障恢复与人工接管。满足独立安全与现场验证条件后再讨论真机执行。

Phase 2–3 的 Mock 基础能力已在本轮实现；跨 Skill DAG、真实模型验收及 Phase 4 真实硬件接入仍属后续路线。

## 快速开始

需要 Python 3.10 或以上。以下离线文本演示无第三方运行依赖，不需要硬件、ASR 模型或文本大模型。从仓库根目录运行：

```bash
python3 InspectionBrain/cli.py '电流互感器和电压互感器有什么区别？'
python3 InspectionBrain/run_v3_demo.py '制定巡检计划，但不要启动导航'
python3 InspectionBrain/run_v3_demo.py '不是2号断路器，是3号断路器' --provider rules --mode auto_fallback
```

第一条使用示例知识；第二条默认为 Mock；第三条展示规则回退。所有结果均不能用于驱动真机。可选手动文本测试台：

```bash
python3 InspectionBrain/run_voice_lab.py --asr none --semantic-provider mock
```

测试台仅监听本地回环地址，Ctrl+C 停止；此模式不执行真实语音识别。SenseVoice 安装、模型与音频验证要求见[语音实验说明](InspectionBrain/docs/VOICE_LAB.md)及[第二轮说明](InspectionBrain/docs/ROUND2.md)。不要把原文档中的历史机器路径当作当前部署路径。

## 运行新增任务系统与测试

Python >=3.10，Linux；使用标准库，无需安装模型也能运行完整 Mock 链路：

```bash
python3 -m InspectionOS --db /tmp/inspection-demo/local.db --idempotency-key demo-alarm
python3 -m InspectionOS --db /tmp/inspection-demo/offline.db --offline --provider mock
PYTHONPATH=InspectionBrain:. python3 -m unittest discover -s tests -v
python3 -m InspectionOS.simulation.scenario_runner --output /tmp/inspection-faults
python3 -m observability.benchmark --output /tmp/inspection-bench --tasks 12
```

测试中的本地 HTTP 需要允许 loopback socket。原有 Python / Node 测试保持独立：

```bash
(cd InspectionBrain && python3 -m unittest discover -s tests -v)
(cd InspectionBrain && node --test tests/*.mjs)
```

本 checkout 缺少原历史导出与一份记录，严格原 Python 回归仍有 6 项缺文件错误及 4 项真实 ASR 跳过；未伪造文件或改原测试。CI 只对确切缺失资产列出 skipped，其余关键测试照常运行。新增套件与原基线结果分别见[验收记录](docs/VALIDATION_REPORT.md)。真实模型 Smoke Test 见[Qwen3 接入说明](docs/QWEN3_INTEGRATION.md)，当前环境未完成真实推理验收。

## 文档导航

- [Evaluation Lab 设计与使用](docs/OLLAMA_EVALUATION.md) · [实际执行结果](docs/OLLAMA_EVALUATION_RESULTS.md)
- [本轮可靠性修复](docs/RELIABILITY_FOLLOWUP.md) · [历史测试资产与 CI](docs/HISTORICAL_TEST_ASSETS.md)
- [当前系统架构](docs/SYSTEM_ARCHITECTURE.md) · [模块边界](docs/MODULE_BOUNDARIES.md)
- [InspectionOS 设计](docs/INSPECTION_OS_DESIGN.md) · [状态机](docs/MISSION_STATE_MACHINE.md) · [Skill 合同](docs/SKILL_CONTRACTS.md)
- [安全模型](docs/SAFETY_MODEL.md) · [弱网自治](docs/OFFLINE_AUTONOMY.md) · [故障实验](docs/FAULT_INJECTION.md)
- [可观测性](docs/OBSERVABILITY.md) · [性能报告](docs/PERFORMANCE_REPORT.md) · [数据管线](docs/DATA_PIPELINE.md)
- [Qwen3 接入](docs/QWEN3_INTEGRATION.md) · [验收记录](docs/VALIDATION_REPORT.md) · [架构决策](docs/ADR/0001-single-machine-runtime.md)
- [初始总体架构规划（历史快照）](docs/ARCHITECTURE.md)
- [2026 年工博会工程复盘](docs/EXHIBITION_REVIEW.md)
- [InspectionBrain 原有说明](InspectionBrain/README.md)
- [v3 使用说明](InspectionBrain/docs/V3.md) · [v3 设计](InspectionBrain/docs/V3_DESIGN.md) · [既有验证报告](InspectionBrain/docs/V3_VALIDATION.md)
- [既有集成边界](InspectionBrain/docs/INTEGRATION.md) · [语音实验室](InspectionBrain/docs/VOICE_LAB.md)

## 安全声明与项目边界

- InspectionBrain 的语义理解不等于现场事实验证；Mock 数据不是真实设备台账或巡检记录。
- 设备编号必须经过真实台账核验；示例知识不能代替现场规程和授权。
- LLM 输出不能直接作为硬件控制命令，也不应获得底盘控制权限。
- InspectionOS 当前仅为 Mock 任务运行时；安全审批独立于模型输出，真实硬件执行仍未接入。
- 当前公开仓库中的任务草案不可直接执行机器人动作；Schema 通过不授予执行权。

本文中的硬件及展会经历来自项目成员提供的信息；软件状态以当前仓库源码为依据。未补充的硬件参数、现场数据和模型效果不作推定。
