# InspectionBrain v3 实际验证报告

## 完成交付及修改范围

独立包 `brain_v3/` 提供 Mock / OpenAICompatible / RulesFallback Provider、原文证据构建、严格 JSON Schema、独立 Validator、强制不可执行 SafetyGuard、任务草案协议、独立记录和语义评测。`run_v3_demo.py` 为离线 CLI；`evaluate_v3.py` 为待标注清单和语义对比；`run_v3_tests.py` 在不覆盖历史报告的前提下运行全套 Python 测试。

既有文件小幅调整：`voice_lab/server.py` 新增语义接口和配置，`static/index.html` 增加独立面板，`static/app.js` 增加面板初始化及输入更新通知，`pyproject.toml` 纳入新包，`README.md` 添加文档导航。新前端逻辑在 `static/v3.js`。v2 核心、词库、ASR 实现/环境/模型、历史音频与评测、机器人工程均未修改。

实际加载词库 electrical-v2.3，SHA256 `fe43978ba1363d84905c556eb5b50f9da3d494cc7f8d026a7e46de5ba5eb24b7`；没有 v2.1/v2.2 选择开关。旧记录原版本保留，用户已启动服务仍需通过配置自检确认，不能拿磁盘版本冒充运行版本。

## 真实执行结果

|验证|实际结果|
|---|---|
|独立 ASR 环境全量 Python|121 项：120 通过，0 失败，0 错误，1 跳过|
|系统 Python 补验证|1 项通过，0 失败，0 跳过|
|Node 前端 / 录音 / 评分 / v3|19 项：19 通过，0 失败，0 跳过|
|v3 新增 Python|34 项，其中33项通过、1项可选包环境跳过；该项系统Python补验证通过|
|真实已有 WAV + SenseVoice + HTTP|通过，使用临时 loopback 服务与临时记录目录|
|真实文本 LLM|未连接；兼容接口测试服务是明确标记的协议夹具|
|Windows Chrome 实际麦克风 / DOM|未验证，无可调用浏览器工具或已安装浏览器；Node 是 DOM/fetch 模拟|

唯一跳过项是 ASR 隔离环境没有可选 `jsonschema` 包；未安装或污染该环境。相同 Schema 已在系统 Python 使用 Draft202012Validator 校验通过，并与内置精确词汇校验器对照。生产代码不依赖该包。

首次在沙箱运行全量测试时17项本地套接字检查受 PermissionError 阻止；获准后在允许临时 localhost 套接字的环境重跑，最终结果如上。没有将权限错误改成测试通过，也没有改既有期待值。旧测试的两份历史 HTTP 报告写入由 runner 重定向为 v3 前缀，原文件哈希保持。

日志与统计：[Python](../reports/v3_python_tests.log)、[统计](../reports/v3_test_summary.json)、[Schema补验证](../reports/v3_schema_interoperability.log)、[Node统计](../reports/v3_frontend_summary.json)。

## 真实音频链路

只读使用原音频 `runtime/voice_lab/audio/2cd65701e7a44ff88e1c5a1202f997dc.wav`，原历史记录 `9bf3bee5bf3e48e3b60a3a33d6966bc5` 不变。测试上传到临时本地服务，重新执行真实 CPU SenseVoice，然后分析保存的原始输出。不会以手动文本冒充模型输出。

- 原音频 SHA256：`a7582a831e6a040d37d98f692e3692b4599ba17c97281099a902c178e3b2f84f`。
- 模型：`sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17` / `2024-07-17-int8`，provider=cpu。
- 原录音 8.992 秒，16000 Hz；本次 ASR 推理 1.259 秒，时间 2026-10-09T17:42:35.317046+08:00。耗时只代表此请求。
- 实际原文：**请查询2号主变电压高套管的红外测温记录，并与上周的结果比较。**
- 同一个成功请求再次分析复用记录；切换纠错配置保存对照记录。2次分析、1个唯一音频 SHA256；无人工语义标准，语义正确率为 null。
- v2/v3均保留原文证据与不确定部位候选；v3识别测温历史和比较需求，2号主变与套管是文本关系，身份未核验。上周按上海时区解析；待比较目标时间未明时要求确认。未读取真实测温数据库，不诊断异常。
- v3 使用 **Mock脚本，非真实LLM**。Schema与Validator通过、草案 authorized/executable/hardware_commands_enabled=false。原语音 CER 评分仍由既有流程和人工参考确认决定。

完整真实 HTTP 证据：[v3_real_wav_http.json](../reports/v3_real_wav_http.json)。这证明 WSL 的 WAV → 真正 ASR → 语义接口链路；不证明 Windows 浏览器麦克风交互或真实 LLM 能力。

## 语义开发对照及其边界

历史数据只读清单含71条记录、17个唯一音频 SHA256和17个已存 SenseVoice 转写，均为开发回归；**已确认独立人工语义标注为0**。17条转写重新分析后17个Mock候选的Schema/证据校验通过；各正确率、真实LLM耗时、ASR改善指标均不计算。清单：[v3_development_manifest.json](../reports/v3_development_manifest.json)；逐条结果：[v3_history_semantic_validation.json](../reports/v3_history_semantic_validation.json)。

另有8条手工合成的开发契约，独立填写结构化期待值；不由模型输出生成，不是未见盲测。下表只表示这些已见契约的结构完整性。Mock由确定性证据脚本构建，不能解释成LLM收益或泛化准确率。

|标注维度|v2适配表示匹配条数|v3 Mock匹配条数|
|---|---|---|
|意图及请求类别|5/5|5/5|
|设备编号与排除关系|1/2|2/2|
|时间约束|1/1|1/1|
|数值与否定关系|1/3|3/3|
|禁止范围|1/1|1/1|
|自我修正关系|0/2|2/2|
|条件范围|1/1|1/1|
|数据任务依赖|0/1|1/1|

v2 已有的禁止、条件、时间、多意图与正常设备实体在适配器中如实保留，没有将不同 JSON 格式当成能力缺失。v2 未建立的自我修正、排除/接受对象和依赖关系保留 unresolved/缺失。v3工程补充了这些关系，同时仍未核验真实身份或测量。详见 [v3_semantic_comparison.json](../reports/v3_semantic_comparison.json)。

安全回归另行覆盖：凭空更换设备、篡改小数/单位/相别或对象归属、原文引用伪造、否定/条件缺失、授权和执行标志、现场故障结论、Schema异常、工具调用、截断、超限、重定向和超时均不能产出可信执行草案。自动回退保持可用v2并明确来源。网页回归覆盖原ASR/参考保存、正确audio_id、无参考外发、模式默认、故障回退、重复刷新不累积绑定、换输入不显示旧草案。

## 原工程保护与运行

保护快照覆盖 11308 个文件；变化0、缺失0，包括机器人工程、根目录历史导出、v2核心、旧音频/记录/报告、ASR源码/模型/隔离依赖，排除Python缓存。结果：[v3_protection_validation.json](../reports/v3_protection_validation.json)。没有安装依赖或模型、改网络、操作Jetson、修改固定回答或运行硬件写操作。本轮临时服务已关闭，当前用户测试台未被重启。

启动与最少操作、Provider环境变量、回退、待人工标注与下一阶段见 [V3.md](V3.md)。启用新前端/服务时需只重启InspectionBrain测试台并强制刷新Windows浏览器；真实LLM仍需后续明确配置和独立验证。本轮完成后停止开发。
