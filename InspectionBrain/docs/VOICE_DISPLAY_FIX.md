# 语音测试台识别结果展示修复

后续评分流程已单独修复，最新按钮、v2.3 运行版本检查和真实 WAV 验证见 [SCORING_WORKFLOW_FIX.md](SCORING_WORKFLOW_FIX.md)。下文保留本次展示修复时的行为与测试结果，作为历史说明。

## 确认的行为与问题

用户在 Chrome Network 确认 `/api/audio` 返回 HTTP 200、`asr.status=ok`、SenseVoice 原始转写、推理约 1.409 秒、音频 11.112 秒 / 16000 Hz。这是用户提供的真实请求证据；本轮回归使用该响应的文本与字段模拟前端，不冒充重新运行模型。

检查发现旧 `app.js` 已经保存 `audio=result`、写入 `raw-asr` 并选择 `asr` 来源。用所述响应运行旧代码，原始转写写入测试通过。因此无法仅凭该响应断言用户页面未显示的具体运行时原因；旧区域位于较下方，浏览器仍加载旧脚本等可能性需要 Chrome 页面 / Console 验证。

已确定的缺口：

- 旧领域分析按钮是 **“分析并保存本条评测”**，不会在上传后自动分析。选择题目产生参考文本但未确认时，按钮会拒绝提交；这是计分保护，应保留。
- 模型 / 推理耗时仅在响应含 `model_id` 时更新。成功响应只含 `engine`、`text` 和 `inference_seconds` 时，耗时不会显示。
- 时长格式化使用 `duration_seconds.toFixed()`，发生在显示转写前。回归复现：缺少该元数据时，成功转写停留在“等待本次音频转写”。用户已经报告时长为数值，因此这不能认定为其实际请求的原因。
- 没有独立的上传、识别、分析状态，也没有成功 ASR 的前端回归。

## 本次修复

原始转写区域移到录音 / 上传控件附近，并保留唯一 `raw-asr` DOM ID。上传、结束录音和重新识别统一更新本次音频状态：先写入原始文本，再安全格式化元数据。显示 `audio_id`、引擎、模型 / 版本和推理耗时；响应缺少模型字段时使用服务配置，缺失元数据明确显示“未提供”。不改后端 ASR 或模型。

新增 **“分析本次识别结果”**：只在本次音频有非空成功 ASR 和 `audio_id` 时启用，直接通过已有 `/api/evaluate` 传递该 ID 和 `input_source=asr`。服务仍从保存的音频元数据读取原文，客户端粘贴不能替代模型输出。此入口不提交参考或题目 ID，保存不计分记录；页面参考文本不删除。计分继续使用原按钮及参考确认保护。领域分析失败保留成功识别结果；上传成功不等于识别成功，识别成功不等于取得现场证据。

## 使用方法

```bash
cd /home/user/inspection_robot
python3 InspectionBrain/run_voice_lab.py
```

Windows Chrome 打开 **http://localhost:8890/**。已有服务运行时先刷新页面获取新 HTML / JS；无需为前端展示更换模型。新词库由进程启动时加载，应用新纠错规则需在原终端 Ctrl+C 停止 **InspectionBrain 测试台**，再用上述命令启动。不要重启 RobotTerminal 或机器人服务。

1. 录音后点击“结束录音”，或上传 WAV。成功后原始文本直接显示，三个状态分别呈现。
2. 点击“分析本次识别结果”，查看增强文本、实体、意图与解释。没有核实参考时不计分。
3. 如需评分，核实对应的参考文本，勾选确认，再点击“分析并保存本条评测”。每次分析新增记录，保留历史。

## “主片”只读候选

词库版本为 `electrical-v2.2`。在既有 `main_transformer` 下增加混淆候选“主片”，展示替换为别名“主变”；标准名称仍为“主变压器”，设备类别与标准 ID 不变。

仅匹配候选所在位置，依赖附近的高压套管、变压器套管、高压侧、绕组温度、油温、变电或变压器上下文。电影、影片、纪录片或视频上下文阻止应用。开启只读同音纠错后才自动应用；默认关闭时展示可读确认候选。无设备上下文时不能通过确认绕过限制；肯定 / 条件操作文本也不能纠正或授权。规则不全局替换，不改 ASR 原文，不确认设备身份和编号。

回归覆盖用户句子、关闭 / 开启纠错、非电力语境、含电力词的纪录片语境、原文保存及导航操作保护。新增候选配置只能使用同一术语的标准名或别名，禁止借此合并不同设备类型。

## 验证边界

新增 5 个 Node 前端回归，验证成功 WAV、录音、重新识别、模型 / 耗时展示、当前 `audio_id`、无确认参考的直接分析、空转写 / 失败 / 未配置回退、领域分析失败保留原文和 HTML ID 唯一性。新增 2 个 Python 电力候选回归。

实际执行：68 项相关 Python 测试、10 项 Node 测试通过；失败 0，跳过 0。其中包含既有原文保护、旧路由回退、评分、问答、ASR 接口模拟、音频格式和手动评测回归。本轮未重跑真实模型 / HTTP 套接字测试，未操作运行中的服务；浏览器 DOM / fetch 测试不等于 Windows Chrome 实际录音验收。

```bash
cd /home/user/inspection_robot/InspectionBrain
python3 -m unittest tests.test_domain_v2 -v
node tests/test_voice_asr_display.mjs
node tests/test_voice_browser.mjs
node tests/test_voice_audio.mjs
```

完整日志：[Python](../reports/voice_display_python_tests.log)、[前端](../reports/voice_display_frontend_tests.log)。保护校验：[voice_display_validation.json](../reports/voice_display_validation.json)。原有报告、用户历史记录未覆盖，不宣称 ASR 识别质量改善。
