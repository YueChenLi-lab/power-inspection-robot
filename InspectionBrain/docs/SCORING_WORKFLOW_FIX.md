# 真实语音评分流程、样本去重与领域解析修复

## 根因与事实

已读取实际记录 `9bf3bee5bf3e48e3b60a3a33d6966bc5` 及原 WAV `2cd65701e7a44ff88e1c5a1202f997dc.wav`。原文件 SHA256 为 `a7582a831e6a040d37d98f692e3692b4599ba17c97281099a902c178e3b2f84f`，时长 8.992 秒，SenseVoice 原转写成功。原记录的参考为空、确认标记 false，评分 before/after 为 null，故不能计分；不是 ASR 上传失败。

旧“分析本次识别结果”入口主动提交空参考并保存不计分结果。原文保护是正确的，但界面把分析与评测保存混在一起，缺少持续显示的评分步骤与原因。旧服务每次请求创建新 UUID，汇总按评分运行数累计字符和术语分母；重复录音 ID、重新识别与规则对照没有按原 WAV 哈希去重。GET 刷新本身不写记录。

原记录确实使用 `electrical-v2.1` / `ea5e8ee142de03ea6d31e2cb4be90bb2220e67ebd6816f8fe15764a0d02c8dca`。开发开始时磁盘文件已为 v2.2；本轮升级为 v2.3。实际 8890 `/api/config` 的只读检查仍无词库版本、哈希或工作流版本信息，开发期间新保存的记录仍为 v2.1。词库仅在 `VoiceLab` 创建 `ElectricalBrainV2` 时加载，编辑磁盘与刷新 JS 均不会更新旧 Python 对象。没有 v2.1/v2.2 小版本选择开关；只有 `--domain-version v1|v2`，v2 读取 `inspection_brain/data/electrical_terms_v2.json`。新启动的临时服务已实际确认 v2.3 和磁盘 SHA256 一致。历史 v2.1 记录没有改写。

旧解析只有“比较在温度词之前”等模式，基础分析又将测温记录归为温度告警；`上周` 未被时间解析器覆盖；词库缺少高压套管及相关长词，所以“电压高套管”没有候选，独立“电压”被命中。

## 当前操作：无需重复录音

现有 8890 服务需在原终端 **Ctrl+C 只停止 InspectionBrain 测试台**，再启动：

```bash
cd /home/user/inspection_robot
python3 InspectionBrain/run_voice_lab.py
```

Windows Chrome 打开 **http://localhost:8890/**，按 **Ctrl+F5** 加载新页面。页面应显示实际运行词库 **electrical-v2.3**、文件路径、SHA256，以及运行 / 磁盘是否一致。当前文件 SHA256 是 `fe43978ba1363d84905c556eb5b50f9da3d494cc7f8d026a7e46de5ba5eb24b7`。若文件以后再编辑，实际哈希以页面为准；磁盘与已加载哈希不同会提示需重启。

最少步骤：

1. 当前音频已在页面时直接继续；若已刷新，在历史表点对应记录的 **“载入原样本”**，即可复用保存的音频与原始转写，无需上传或重识别。
2. 输入实际朗读的人工参考，核实后勾选确认。
3. 点 **“评分并保存（使用当前音频，无需重录）”**。CER 前后、其他指标及汇总会即时更新。

新录音的流程是：录音 / 上传 → 原始 ASR 自动显示 → **“领域分析 / 重新分析本次识别结果（不计分）”** → 校对并确认参考 → 评分保存。没有人工参考也能分析，页面明确显示未计分原因；不会产生虚构的 CER 或术语分数。

分析、评分和重新识别有独立按钮 / 状态。重新分析不重跑 ASR；评分复用同一配置的分析，保留该分析的时间语义，另存评分并关联原记录。配置改变时重新分析后再评分，参考文本与确认保持；也可直接评分，由后端分析新配置。重新识别才会实际重跑模型，产生新的转写 ID，仍保留原音频哈希、人工参考和历史。

ASR 未配置 / 失败时可以粘贴文本，点 **“分析手动 / 外部转写（不计分）”**；核实参考后也可评分。manual、Windows 外部与实际本地 ASR 分开统计。

## 保存与统计规则

- 完全相同的分析 / 评分请求可重复提交，返回已保存的相同 `record_id`；服务重启后仍有效。页面重复分析也会复用当前显示。刷新只读取记录。历史重复数据保持原样。
- 同一音频的评分修订另存并通过 `derived_from_record_id` 关联原分析。评分复用分析时保持同一个 `analysis_run_id`；来源、原文或音频不一致的关联会被拒绝。
- 新 `analysis_key`、`evaluation_key` 和 `provenance` 关联原音频 ID / SHA256、原转写、模型 ID / 版本、领域 / 语义版本、词库 SHA256、纠错开关和人工候选选择。改配置会生成独立结果，保持音频身份。
- `record_count` 是全部记录数；`unique_audio_sha256_count` 是记录及已保存上传音频的唯一哈希数。
- `independent_test_sample_count` 是有实际成功 ASR 结果的唯一音频哈希数，manual 不计入。`confirmed_reference_unique_audio_count` 是其中参考已经有效确认、可计分的唯一音频数。
- `analysis_run_count` 按 `analysis_run_id` 去重；无法追溯分析 ID 的旧记录按每条记录计为一次运行，不冒充恢复了旧时全部网络点击。
- `confirmed_runs` 保留已确认运行次数作为兼容字段；**`scored_unique_samples`** 才是去重后的计分样本数。总汇总对每个音频哈希选最新已确认评分，字符 / 术语分母只累加一次。不同模型、词库、语义及配置的对照在各自分组内去重，不能把分组相加当作独立样本数。manual 按来源与原文本去重，仍不是语音样本。

## 领域解析与证据边界

词库由 50 条增至 54 条：新增“套管”“高压套管”“红外测温”“红外测温记录”，保留既有术语类型与 ID。长词与整词混淆窗口优先，避免把“电压高套管”中的“电压”当作独立测量指标。

“电压高套管 → 高压套管”为高风险、需上下文和原音频核实的候选，**即使开启纠错也不自动应用**。主变 / 变压器 / 红外测温上下文支持展示确认；小说、网名等语境及操作文本阻止应用。人工确认只影响可读展示，不能改原始 ASR、设备编号、执行授权或正式结论。

当前真实句子识别为 `thermometry_history` 与 `temperature_comparison`，提取 2 号主变、套管检查部位及红外测温方式。新增 `temperature_anomaly_query`、`temperature_measurement_query`，明确告警请求才归入 `temperature_alarm_query`。

时间依据 **Asia/Shanghai**。在 2026-10-09 参考日期，“上周”是 2026-09-28 00:00 至 2026-10-05 00:00，右端不含，作为比较基准；用户没有说当前查询范围，`target.resolved=false`，不能默认本周。UTC / 上海跨周边界有独立回归。编号 02、危险数值 685℃ 等保持原值，不猜小数。设备序号仍未核对台账，套管高压部位仍是待核实候选；没有历史测温数据库时返回证据不足，不输出现场温度或异常诊断。

## 验证结果与实际范围

最终完整执行 **87 项 Python 测试、14 项 Node 测试通过，失败 0、跳过 0**。新增 12 项 Python 领域 / 评分 / 版本回归、2 项 HTTP 回归，以及 4 项前端评分流程 / 旧服务版本提示回归。既有语音、音频、路由回退与安全约束测试继续通过；旧真实模型测试仅调整输出报告位置以保留上一轮报告，没有改其验收期待值。

真实用户 WAV 通过独立临时 loopback 服务完成 SenseVoice 推理、分析、无确认拒绝评分、确认参考后评分、即时汇总、重复提交、规则对照及再次识别。两次真实转写均与用户所述原文一致。最终该测试有 5 条记录、3 次分析、**1 个独立音频样本**；新分析使用 v2.3。原 WAV 字节与 SHA256 未变。

**真实评分参考尚未由用户提供。** HTTP 计分环节采用明确标注的固定接口测试参考，并程序化确认，验证评分协议和指标即时返回；没有用 ASR 输出自动生成标准答案，没有把这些数值当成实际朗读的 CER 质量成绩，不宣称 ASR 改善。这些记录只保存在临时测试目录，未导入用户运行历史。

**Windows Chrome 实际点击 / 麦克风 UI 本轮未验证。** 当前环境没有可操控的浏览器。Node 是 DOM / fetch 模拟，HTTP 与模型推理是真实执行，二者分别报告，不混为真实浏览器验收。用户此前提供的 Chrome 证据与本轮自动测试分开归档。

```bash
cd /home/user/inspection_robot/InspectionBrain
.venv-asr/bin/python -m unittest discover -s tests -v
node tests/test_voice_audio.mjs
node tests/test_voice_browser.mjs
node tests/test_voice_asr_display.mjs
```

日志：[完整 Python](../reports/scoring_full_tests.log)、[Node](../reports/scoring_frontend_tests.log)。真实 WAV 报告：[scoring_real_user_wav_http.json](../reports/scoring_real_user_wav_http.json)；前后事实与保护校验：[scoring_validation.json](../reports/scoring_validation.json)。此前 `ROUND2` 与展示修复报告保留原样。

## 修改文件

| 文件 | 修改目的 |
|---|---|
| `voice_lab/server.py` | 分析 / 评分模式、关联、分析复用、请求去重、词库与进程自检、统计接口 |
| `voice_lab/metrics.py` | 原有 CER 算法保留，按音频哈希 / 版本配置去重统计 |
| `voice_lab/static/app.js`、`index.html` | 分阶段操作、即时评分、参考保护、历史升级、实际版本显示 |
| `inspection_brain/data/electrical_terms_v2.json` | v2.3、4 条长词与上下文候选 |
| `inspection_brain/domain_v2/normalization.py` | 保存实际词库路径用于自检 |
| `inspection_brain/domain_v2/semantics.py`、`service.py` | 历史测温、异常 / 告警区分、上海时间比较、部位 / 测量方式、无证据结果 |
| `tests/test_scoring_workflow.py`、`test_scoring_http.py` | 新增领域与真实 HTTP 验收 |
| `tests/test_voice_asr_display.mjs` | 扩展前端计分和去重回归 |
| `tests/test_real_sensevoice.py` | 本轮报告另存，保护旧报告 |
| 本说明、`VOICE_LAB.md`、`VOICE_DISPLAY_FIX.md`、`reports/scoring_*` | 使用指引、事实和验证记录 |

本轮修改只在 InspectionBrain。原机器人控制、Vosk / RobotTerminal 接入、模型、固定回复、导航、MotionGuard、CAN 均未修改；未重启既有服务，测试临时服务已关闭，用户历史未删除或覆盖。
