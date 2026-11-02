# Inspection Brain v2：电力领域增强第一阶段

最新独立语义原型：见 [v3 使用说明](docs/V3.md)、[技术设计](docs/V3_DESIGN.md) 和 [实际验证报告](docs/V3_VALIDATION.md)。v3 默认保留 v2，不连接外部 LLM；可用明确标记的 Mock 演示不可执行任务草案。下方首阶段说明与指标保留为历史。

独立、离线、无第三方运行依赖的最小闭环：术语 → 文本规范化 → 设备实体/编号与意图 → 知识检索或数据需求 → 带来源回答/不可判定/不可执行草案。

代码全部位于本目录，没有接管原有语音或Gateway。Brain核心没有CAN/ROS/硬件驱动或运动执行器；独立安装脚本只从官方源下载依赖和模型，语音测试台仅提供localhost离线测试。Vosk、SenseVoice、TTS、固定回复、点动确认与底盘安全逻辑均未修改。不要把示例问答或Mock数据用于现场判定。

## 运行与停止

Python 3.10以上；本轮在Ubuntu 26.04的Python 3.14.4运行。Xavier若使用现有独立Python 3.12环境可以后续验证；系统Python 3.8不满足本工程要求，未安装或修改它。本轮未在Xavier部署/运行。

从工作区根目录直接运行，无需pip安装：

```bash
python3 InspectionBrain/cli.py --demo --summary --at 2026-10-08T12:00:00+08:00
python3 InspectionBrain/cli.py '电流互感器和电压互感器有什么区别？'
python3 InspectionBrain/cli.py --interactive
```

单次模式输出后退出；交互模式输入`exit`或按Ctrl+C停止。默认输出JSON，`--summary`简洁展示。默认不使用网络、ASR或LLM，不连接任何真机。

独立本地语音测试台（Windows浏览器采集麦克风，WSL保存与分析）：

```bash
python3 InspectionBrain/run_voice_lab.py
```

Windows浏览器访问 **http://localhost:8890/**；Ctrl+C停止。第二轮已在`.venv-asr/`独立安装并实际验证SenseVoice INT8，启动器自动选择此环境。支持真实转写、上下文词库、口语整理候选确认、数值核验、多意图、严格CER和历史重分析；无模型时仍保留手动模式。详细交付、安装版本、来源与验证边界见 [ROUND2.md](docs/ROUND2.md)。测试台仅监听loopback，没有原系统接口或运动权限；不开启时原系统不受影响。

导入第一轮实际导出进行历史对照（原文件与历史记录不覆盖）：

```bash
python3 InspectionBrain/run_voice_lab.py --import-export voice-evaluation.json
# 独立测试台语义回退；生产语音流程始终未接入新模块
python3 InspectionBrain/run_voice_lab.py --domain-version v1 --asr none
```

离线并行路由演示（关闭是默认值）：

```bash
python3 InspectionBrain/cli.py --route '什么是局部放电？'
python3 InspectionBrain/cli.py --route --enable-brain '什么是局部放电？'
python3 InspectionBrain/cli.py --route --enable-brain '前进到一号变压器'
python3 InspectionBrain/cli.py '创建一号变压器巡检计划草案'
```

模拟路由支持`INSPECTION_BRAIN_ENABLED=1`或`--enable-brain`。此flag仅影响新目录的模拟代码；没有修改生产配置。原控制/固定回复优先，关闭或失败返回旧决策与原文。旧分发器是Mock，不执行旧命令，不声称替代或验证生产分发器全部行为。

## 五个指定问题的行为

| 输入 | 结果 | 边界 |
|---|---|---|
| 电流互感器和电压互感器有什么区别？ | 基于示例知识回答，分别提取两种设备 | 不合并为同义词；返回原文、版本、片段ID和hash |
| 变压器巡检一般检查哪些项目？ | 通用示例检查清单 | 非行业标准/非现场规程，无阈值、无动作 |
| 什么是局部放电？ | 示例概念解释 | 不能据此诊断现场局放 |
| 检查一号变压器需要哪些信息？ | 信息准备清单与设备序号候选 | 一号尚未绑定真实设备，回答不是启动任务 |
| 一号主变最近有没有温度异常？ | 不可判定，列出所需台账/测温/告警/规则 | “最近”时间不明确；无真实样本，不能声称正常或异常 |

运行结果见 [demo_summary.txt](reports/demo_summary.txt)，完整结构化样例见 [demo.json](reports/demo.json)。

## 词库与规范化

编辑 [electrical_terms.json](inspection_brain/data/electrical_terms.json)：28个首批术语，四类（equipment/metric/defect/business）。字段包括id、standard_name、equipment_category、aliases、homophones、parent_id和可选device_ids。CT/PT/VT分别归属于电流/电压互感器，断路器与隔离开关独立，主变压器是变压器下的独立子类型。

只应用显式精确别名，最长匹配并保护ASCII词边界。同音词默认保留为候选，不自动替换；`--apply-homophones`仅允许有只读问题标记、无动作词、唯一白名单候选的术语。没有拼音模糊匹配、编辑距离或数值修复。控制、否定控制、混合控制请求全句不规范化。

保留raw_text、normalized_text、变化区间、候选、术语与不确定信息。实体身份只从原文精确设备名称和邻近编号提取，纠正后的设备词不产生确认身份。`01`保留前导零；不支持的中文序号保持未解析；“一号或二号”不选其中一台。设备序号不是台账唯一ID，必须由真实台账确认。

规则识别不能覆盖所有中文表达；保守动作词检测也可能把询问动作原理归为提案。未知句仍无执行能力、不会把规范化文本送给旧控制入口。新增别名、同音候选或路由规则需补测试。

热词核查见 [ASR_HOTWORDS.md](docs/ASR_HOTWORDS.md)。[hotwords.optional.json](inspection_brain/data/hotwords.optional.json)默认关闭；`hotwords.export_vosk_grammar()`只返回候选JSON，不创建识别器或修改生产ASR。

## 意图与数据合同

ElectricalIntentAnalyzer支持：equipment_knowledge、robot_sensor_status、equipment_information、inspection_history、temperature_alarm_query、inspection_plan_draft、anomaly_procedure_explanation、operation_proposal、unknown。

输出设备类型/序号/显式ID、时间范围、所需数据源、不确定信息、原始和规范化文本。参考时间有时区，默认UTC+8；“今天/昨天/近N天/ISO日期范围”可解析，“最近/历史/上次”不擅自定窗口。不会从用户报出的测量值自动推断异常。

`operation_proposal`永远authorized=false/executable=false，任何输出均hardware_commands_enabled=false、executed_actions=[]。巡检计划接口 [mission.py](inspection_brain/mission.py)只提供MissionDraft/MissionDraftSink协议和离线预览，没有执行方法、底盘lease或授权令牌。

Mock与真实读取接口分离：EquipmentRegistry、InspectionRecords、RobotStatus见 [adapters.py](inspection_brain/adapters.py)。当前只实例化Mock，不会连接SQLite生产库/实时传感器。Mock记录缺失不等于设备正常；真实适配器即使未来注入也需新增证据验证与响应合同，本轮没有实现现场诊断。

## 知识导入与来源

编辑或新增 [data/knowledge](inspection_brain/data/knowledge) 下JSON。必填schema_version、id、title、revision、source（kind/label/uri/is_example）、chunks（id/text/required_terms/intents/keywords）。术语ID须在词库存在；重复文档/片段、缺少来源/正文会拒绝加载。

当前仅4份明确标记为人工示例的资料、8个检索片段；不冒充规范、设备说明书或现场记录。`example://`是示例来源标识，不是下载链接。导入真实资料时应保留文件来源、出版/适用版本、授权与审阅记录，PDF/DOCX先在离线工作流提取并人工校核，再写成上述JSON；当前没有PDF/OCR解析器，也不自动下载行业标准。

通过`--data-dir <目录>`可使用另一套同结构词库、knowledge、inspection_items和Mock文件。DocumentRepository提供元数据与term_index，Retriever协议可替换检索实现；LLMProvider协议可替换回答提供者。第一阶段仅允许抽取原文：片段ID与文本必须逐字匹配已检索证据，否则拒答。未来自由生成式RAG需另增逐主张证据验证，不能仅凭模型给了citation就认定可靠。

具体资产查询必须有真实台账与记录；示例知识只回答一般概念。巡检项目映射在 [inspection_items.json](inspection_brain/data/inspection_items.json)，是示例需求清单，不是可执行规程。

## 测试与评价

在InspectionBrain目录：

```bash
python3 -m unittest discover -s tests -v
python3 -m inspection_brain.evaluation
python3 -m inspection_brain --demo --summary
# 可选：浏览器音频与页面流程模拟测试，需要已有Node环境
node --test tests/test_voice_audio.mjs tests/test_voice_browser.mjs
```

测试包含74条手写确定性文本用例、词库冲突/环检测、动作原文保护、编号歧义、时间范围、无证据拒答、伪造阈值/来源拒绝、不可执行草案、flag关闭、旧回复/控制优先、Brain失败/超时/忙碌回退。报告 [evaluation.json](reports/evaluation.json)含逐条原文与规范化对照、分子/分母与指标口径。

这些是文本回归指标，不是真实ASR测评，WER/CER为null；没有真实录音，因此不宣称识别率或WER/CER改善。路由测试使用Mock旧接口，运动误触发指标仅针对离线输出，不能当真机安全认证。详见 [VALIDATION.md](docs/VALIDATION.md)。

## 后续接入边界

见 [INTEGRATION.md](docs/INTEGRATION.md)：原文先交原分发器；原固定回复/控制仍走原系统；只有未命中旧能力的电力问答才进入Brain。Brain没有任何原系统控制权限，纠错文本不能转换成运动授权。先以旁路观测验证真实语音与词库，再另行决定feature flag和内部只读接口；本轮没有部署。
