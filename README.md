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
    T[文本 / 既有语音实验室] --> B[InspectionBrain v2 / v3]
    B --> P[规则 / Mock / Ollama原生Schema Provider]
    P --> V[Schema / Evidence Validator / SafetyGuard]
    V --> D[不可执行任务草案]
    D --> A[BrainAdapter：重新验证与Mock设备映射]
    A --> M[InspectionOS Mission Manager / State Machine]
    M --> S[Scheduler / Skill Registry / Safety Supervisor]
    S --> W[单Worker / 可终止子进程]
    W --> K[Mock告警 / 测温比较 / 复检建议]
    K --> DB[(SQLite任务、事件、执行与证据)]
    DB --> O[事务Outbox / 模拟网络 / Mock远端去重]
    DB --> R[Recovery / Trace / Metrics / 数据管线]
    HW[真实底盘、传感器、业务系统：未接入]
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
| InspectionOS | v0.1 单机 Mock 任务内核可运行 | 非真实硬件 OS、非分布式集群 |
| 真实设备台账接入 | 待建设 | 当前为 Mock |
| 真实巡检记录查询 | 待建设 | 当前为 Mock，现场记录展示不等于此仓库已接真实数据 |
| 完整自主任务执行 | 未实现 | 公开语义链路不能执行机器人动作 |

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

本 checkout 缺少原历史导出与一份记录，原 Python 基线存在 6 项缺文件错误及 4 项真实 ASR 跳过；未伪造文件或改原测试。新增套件与原基线结果分别见[验收记录](docs/VALIDATION_REPORT.md)。真实模型 Smoke Test 见[Qwen3 接入说明](docs/QWEN3_INTEGRATION.md)，当前环境未完成真实推理验收。

## 文档导航

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
