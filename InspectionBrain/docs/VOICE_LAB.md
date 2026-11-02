# InspectionBrain 独立本地语音测试台

最新评分流程、按音频去重、v2.3 版本自检与真实 WAV 验收见 [SCORING_WORKFLOW_FIX.md](SCORING_WORKFLOW_FIX.md)。当前按钮为“领域分析 / 重新分析”和“评分并保存”；已有音频校对参考后即可评分，无需重录。

当前展示修复与新按钮说明见 [VOICE_DISPLAY_FIX.md](VOICE_DISPLAY_FIX.md)：录音 / 上传成功后原始 ASR 自动显示在上传区域，点击“分析本次识别结果”即可做不计分分析；计分仍需核实参考。

> 以下保留第一轮说明与当时“ASR未配置”的历史核查。第二轮已经独立安装真实SenseVoice，默认启动器自动选择`.venv-asr`、网页默认领域v2；新增功能、真实推理结果、评分变更与回退方式请见 [ROUND2.md](ROUND2.md)。旧报告为第一轮历史结果，未覆盖。

## 启动、访问与停止

在 WSL 的工作区根目录执行，不需要安装任何依赖：

```bash
cd /home/user/inspection_robot
python3 InspectionBrain/run_voice_lab.py
```

Windows Edge / Chrome 打开 **http://localhost:8890/**，首次录音允许浏览器使用麦克风。服务只监听 WSL 的 `127.0.0.1:8890`，没有绑定局域网地址。Windows 浏览器经 WSL localhost 转发访问；无需让 WSL Python 打开 Windows 音频设备。

端口被占用时选择另一端口，例如 `--port 8891`，浏览器也使用对应地址。停止：WSL 终端按 **Ctrl+C**，浏览器录音请先点“结束录音”或关闭页面。不注册服务，不修改网络配置，不操作原机器人服务。

[Microsoft WSL 网络说明](https://learn.microsoft.com/en-us/windows/wsl/networking)说明 Windows 应用可通过 localhost 访问 WSL 中的服务。浏览器麦克风权限要求可信上下文；[MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)及[安全上下文说明](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts)把 localhost 列为本地可信场景。若无法访问，先核对服务日志、地址、端口和 VS Code 的 Ports 转发；本工程不会自动改防火墙或 WSL 网络。

## 最简单的使用流程

1. 从28个术语及5个业务问题中选择题目。点击“用选中题目填参考文本”，按实际朗读内容校核，勾选人工标准文本确认。
2. 点“麦克风录音”，朗读，点“结束录音”。或上传已有 WAV。浏览器可播放、下载本次 WAV。
3. 有真实本地 ASR 时使用“实际 ASR 原始转写”；当前环境未配置 ASR，可在单独文本框粘贴已有转写，选“手动粘贴”。参考文本绝不会作为识别结果自动填入。
4. 点“分析并保存本条评测”。查看四项结果、术语/编号/CER、意图解释及证据不足说明。可逐条输入参考文本，之后导出 JSON / CSV。

同音候选纠正默认关闭，可以勾选做只读白名单对照实验。所有动作、控制及混合控制原文均保护；本测试台只生成不可执行提案。即使词语纠正成功，增强后设备实体仍标为文本候选，不确认真实设备身份。

## 当前 ASR 状态及已核实接口

**代码确认 / 本机检查（2026-10-08～09）：**

- 原 `RobotTerminal/backend/interaction.py::_recognize_pcm16` 使用 `vosk.Model`、`vosk.KaldiRecognizer(model, 16000)`、`AcceptWaveform`、`Result`及`FinalResult`。原流程有片段去重，本测试台保存识别器实际分段输出及拼接文本，不修改原流程。
- 原 `RobotTerminal/backend/asr_worker_candidate.py::_sensevoice_recognizer` 使用 `sherpa_onnx.OfflineRecognizer.from_sense_voice`，中文、16000 Hz、CPU、`use_itn=True`，通过stream接收float32采样并解码。测试台只复用公开库的调用方式，不导入原生产模块、不调用原worker。
- 当前启动使用的 Python 环境未安装 `vosk`、`sherpa_onnx`、`numpy`；工作区未找到可用 Vosk 模型目录或 SenseVoice模型+tokens。页面明确显示 **“ASR 未配置”**。未检查用户其他虚拟环境或真机模型，不声称这些环境也不可用。

**可选适配器：**当你已有适配的库、模型和Python环境时，显式指定路径。模型在独立子进程加载，CPU推理；不自动下载，不扫描生产配置，不连接原服务。

```bash
# 在已有 vosk 库的Python环境中运行
python3 InspectionBrain/run_voice_lab.py --asr vosk --vosk-model /path/to/vosk-model-directory

# 在已有 sherpa_onnx 与 numpy 的Python环境中运行
python3 InspectionBrain/run_voice_lab.py --asr sensevoice \
  --sensevoice-model /path/to/model.int8.onnx \
  --sensevoice-tokens /path/to/tokens.txt

# 明确关闭ASR，仍提供全部音频保存和人工文本功能
python3 InspectionBrain/run_voice_lab.py --asr none
```

默认`auto`只考虑显式提供的路径，不发现/下载其他模型。加载超时30秒或失败则未配置，推理超时45秒则终止测试台ASR子进程；UI显示失败/无转写，不填充伪造文本。空转写也不进入ASR评分。第一版不应用ASR热词、不接入Vosk语法配置；术语增强仅发生在转写之后，与原ASR独立。

**尚待真实环境验证：**此工作区没有实际ASR模型或真实音频样本，Vosk/SenseVoice调用由接口测试覆盖，真实模型能否加载、Windows浏览器麦克风权限、录音质量及识别质量需使用者实际录音验证。不能据此宣称ASR改善。

## 音频、原文与存储

浏览器使用 `getUserMedia` + [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)采集PCM，单声道/多声道均值，线性重采样为16000 Hz、PCM16 WAV；不使用浏览器自带语音识别、不调用外部ASR网站。一次麦克风录音最多30秒。保存的原WAV是上述浏览器编码结果，不声称保留麦克风设备原始采样格式。

上传支持RIFF WAV、16-bit PCM、1/2声道、8～48 kHz、最长60秒、最大12 MiB；拒绝WebM/MP3/浮点WAV/截断文件。服务器保存上传字节原样及SHA256，再用独立副本转为16000 Hz单声道供ASR；重采样是最简线性实现，未进行降噪、训练或音质优化。

默认保存位置：`InspectionBrain/runtime/voice_lab/`（已加入该工程的.gitignore）。`audio/<uuid>.wav`保留原文件，`audio/<uuid>.json`保留ASR/采样元数据，`records/<uuid>.json`保存每次评测。可通过`--storage /path/to/local-directory`选择位置。停止服务不删除录音；文件只保存在本机，请自行管理含人声/现场信息的文件。

服务器只从已保存的音频元数据读取ASR文本，拒绝客户端替换ASR内容。人工粘贴与参考文本分字段保存；修改参考文本重新评测会新增记录，不覆盖原文件/转写。JSON导出保留完整原文与分析，CSV带UTF-8 BOM，潜在Excel公式字段加前置单引号，完整原文仍保留在`details_json`和JSON导出。

## 评测口径

- **CER**：Levenshtein字符编辑数 / 人工参考字符数，忽略Unicode标点和空白，保留数字与大小写。插入多时可大于100%，不截断。分别算原始文本、增强文本对同一参考的CER。
- **术语识别正确率**：按词库标准术语ID及出现次数配对的正确数 / 参考术语数（召回率）。精确别名视为同一术语；不同设备类型不合并。另报精确率、多识别和漏识别数，避免额外术语掩盖错误。
- **设备编号准确率**：按设备术语ID、提取序号、显式设备ID的组合及次数匹配；不把一号断路器当一号变压器，保留`01`和`1`差别。这是文本编号提取评分，不是真实台账绑定成功率。
- 参考文本未人工确认或有效字符为空，不评分；没有术语/编号分母时为`null` / “无分母”，不显示100%。参考识别使用同一套确定性规则，因此难以解析的编号应结合原文人工核查，不能把规则不识别当成ASR正确。
- 汇总分为 **asr**（真实识别输出）和 **manual**（粘贴文本），不会合并。CER按总编辑数/总参考字符数加权，术语及编号按总分子/分母计算。`confirmed_runs`是评测次数，重复评测同一音频也会计数，不代表独立录音数量；统计比较前请按audio_id选取人工定稿，避免重复样本偏重。

增强后的实体仅用于文本对照评分；原Brain的身份、不确定信息、意图与不可执行输出保留。这里不计算WER、不评估模型训练效果。没有真实语音样本时，人工文本的CER不得解释为ASR识别率提升。

## 测试与边界

```bash
cd /home/user/inspection_robot/InspectionBrain
python3 -m unittest discover -s tests -v
node --test tests/test_voice_audio.mjs tests/test_voice_browser.mjs
```

Python测试验证WAV/输入限制、评分、原ASR不可覆盖、人工与ASR分组、CSV/JSON、真实loopback HTTP、原Brain文本回归。Node（可选，仅开发测试）验证WAV编码、重采样、AudioWorklet及模拟DOM的录音→保存→手动分析流程。浏览器模拟不等于实际Windows麦克风验收。

本轮验证结果：50项Python测试、5项Node测试通过，其中保留74条原有合成文本回归；实际启动脚本已成功启动并停止。详见 [voice_lab_validation.json](../reports/voice_lab_validation.json)和同目录测试日志。SHA256前后对比确认原工程与根目录审计文档7,857个文件没有新增、删除或内容变化。真实语音样本数为0，真实ASR CER/WER为null，没有识别改善结论。

`voice_lab/`是`inspection_brain/`的同级独立模块。Brain核心仍无网络或ASR库导入；测试台仅添加本地HTTP服务和可选离线ASR适配器。无CAN/ROS/导航/云台/生产Gateway/语音运动确认调用，无执行接口。原语音路径、固定回复、安全逻辑和机器人服务全部保留；关闭测试台不改变原系统行为。
