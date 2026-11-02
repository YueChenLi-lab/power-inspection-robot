# 电力语音第二轮交付与运行说明

## 已交付与验证边界

工作区根目录的实际`voice-evaluation.json`已逐条读取并保留，SHA256为`003cadbb21918b998d0504807bc7ad24e40d6ac36dc0074160782572b0213ee5`。9条均为manual，audio/raw_asr_text为空、同音纠错关闭；1条确认参考、8条未确认。没有把这些转写归因为SenseVoice错误。

独立领域v2现包含50个术语（新增22个）、上下文候选、只读口语整理、数值核验、多意图和禁止/条件作用范围、综合问答证据覆盖检查、新评分和历史重分析。v1核心词库、原语音路由仍保留；原机器人各工程没有接入新模块。

SenseVoice已在WSL独立环境实际加载，并用官方5.592秒真实中文WAV完成推理。诊断转写为“开饭时间早上9点至下午5点。”，首次诊断推理约0.790秒。另已验证真实WAV经localhost HTTP上传→ASR→领域分析→导出，以及同一音频再次推理的转写一致性和原文件哈希。

这些是真实CPU推理与服务集成测试，不是用户Windows麦克风或电力领域音频验收。Windows录音路径通过模拟浏览器测试；实际Windows麦克风权限、转发和行业朗读质量仍需现场点击录音验证。没有人工核实的官方样例参考文本，不计算其质量CER，也不宣称电力ASR改善。

## 启动、导入与回退

在WSL根目录：

```bash
cd /home/user/inspection_robot
python3 InspectionBrain/run_voice_lab.py --import-export voice-evaluation.json
```

Windows浏览器打开 **http://localhost:8890/**。启动器自动选择已验证的`InspectionBrain/.venv-asr/`，默认加载本地INT8模型和领域v2。选择题目会同步标准文本；手动改参考会标为自定义，不沿用错误question_id。新音频或新转写需重新勾选“确实对应本次朗读”，才能由网页保存计分结果；清空参考可只做不计分分析。

1. 录音并结束，或上传PCM16 WAV（8～48kHz、1/2声道、最长60秒、最大12MiB）。浏览器录音最长30秒。
2. 检查实际原ASR、术语规范化、口语可读文本、数值风险、全部候选与修改位置、实体及多意图。纠错开关默认关闭，需主动开启对照；不确定候选确认/拒绝后再次分析新增记录。
3. 校核参考文本，分析并保存，导出JSON/CSV。人工粘贴、Windows外部转写、实际本地ASR独立标注；本地SenseVoice单独汇总。
4. 历史行点“载入原样本”，再核实参考后重新分析，不覆盖旧行。当前音频可点“对同一原WAV重新识别”，新ASR另存，保留来源audio_id和原SHA256。

导入把原导出原样另存于runtime/imports，原记录按原ID保留；同ID不同内容拒绝覆盖。历史旧评分字段不改，绑定未经新核实的历史行不进入v2汇总。

```bash
# 无模型或希望关闭ASR时，仍可录音、上传与手动分析
python3 InspectionBrain/run_voice_lab.py --asr none

# 独立测试台回退第一轮语义；原机器人语音从未被切换
python3 InspectionBrain/run_voice_lab.py --domain-version v1 --asr none

# 电力领域v2纯文本演示，无ASR/HTTP
python3 InspectionBrain/domain_demo.py '制定巡检计划，但不要未经授权启动机器人自主导航。'
python3 InspectionBrain/domain_demo.py '变压器的绕阻温度是什么？' --apply-homophones
```

Ctrl+C停止。没有注册系统服务，不部署Xavier，不连接机器人或云端ASR，没有运动/倒闸按钮与接口。

## 真实数据诊断与增强对照

- [逐条错误分类表](../reports/ROUND2_ERROR_ANALYSIS.md)及[完整原字段分析](../reports/round2_error_analysis.json)：含original/enhanced/reference/确认标记/来源/原ASR/纠错开关/analysis/result/metrics。
- [逐条增强对照](../reports/ROUND2_COMPARISON.md)及[完整新旧分析](../reports/round2_comparison.json)：同音开/关分别重分析，未把未确认参考当真值。
- [真实HTTP推理与重复识别演示](../reports/round2_http_real_asr_demo.json)。样例来自官方模型包，不是用户电力录音，也没有伪造参考或音频。

唯一确认样本的旧兼容CER为34.48%→36.21%，变差；新严格CER（包括空白/标点）诊断为38.21%→39.84%，也变差，主要有合法“主变”扩写影响逐字分数。新口径不能直接与旧CER混比。术语别名等价评分独立，不篡改严格CER；危险数字仍未修复，该样本不能得出识别质量改善结论。

工程行为改进由回归证实：隔离开关异常查询不再unknown；记录查询/测温对比/复检建议同时输出；制定计划与禁止未授权导航同时保留；“不能自动执行倒闸操作”没有肯定动作提案；开关柜综合需求不以局放定义冒充完整答案。

## 词库、口语、数值与安全语义规则

词库在[editable electrical_terms_v2.json](../inspection_brain/data/electrical_terms_v2.json)，保留v1独立文件以回退。字段含term_id/id、standard_name、category、equipment_category、aliases、confusion_candidates、context_keywords、risk_level、correction_policy、parent_id和device_ids。完整新增/修改清单见 [ROUND2_TERMS.md](ROUND2_TERMS.md)。同时输出词库版本与SHA256。

低/中风险混淆只有在开关启用、上下文命中且不是肯定/条件操作时才自动规范化。上下文检查去掉混淆词本身，不用“什么”这样的普通疑问词证明电力语境。分合闸、有载分接开关、倒闸、SF6压力和相别为高风险候选；用户确认也只影响可读展示，不改原ASR、原身份、授权或数值参数。

口语整理：只读“1号的主变”可删冗余“的”；清晰句首“嗯/呃”作填充；并列需求插标点而不丢词。相邻重复和中途重启必须人工确认。“三号柜开关3号开关柜”只在两序号格式等价时给同一柜的重启候选，`01`和`1`不混同；“分别检查一号…和二号…”保留两台。确认后示例为“三号开关柜的A相接头温度”“变压器套管渗漏油”“1号主变的油温”。缺音频时只称“可能的口语重复”，不判断发生原因。

保留raw_transcript、term_normalized_text、cleanup_source_text、cleaned_display_text、correction_candidates和correction_trace。每项追溯说明stage和source_span；主变可读别名回投影与术语标准名分开。操作类文本不清理，即使提交确认ID也不能形成动作授权。

数值支持阿拉伯/中文数、小数、百分比、℃、kV/V、A、MPa、设备序号和相别，保存raw_value、原单位、normalized_unit/value、source_span、uncertainty和verification_status。一百一十千伏→110kV属于格式转换，110kV与110000V数学等价；11000V不能修成110kV。685/823/125保留原值并提示核查小数；05赵帕保留未解析值/单位，不能猜为0.5MPa。mPa不能自动归并MPa；a箱/b箱是相别候选，不能把收纳箱全局改成电力相别。数值槽位按指标/相别/等价值比较，设备编号另做类型+编号匹配；均不是实际设备身份绑定。所有数值现场核验状态均未验证，不输出异常结论或写正式缺陷记录。

否定及条件按局部子句处理。“不执行/不要移动/不能操作/未经授权”不能作为肯定动作；“前进，但不要后退”保留前进提案和后退禁止；条件操作仍为不可执行提案。多意图列表、constraints、conditional_clauses、信息需求和来源保留；未来Mission草案带这些约束与数值核验，不提供执行器。

综合检索把设备、指标、缺陷需求分开；概念证据标为concept_only，缺少说明书/规程/运行数据明确列出。无足够覆盖返回undetermined，示例资料继续标示例，原文来源一致性验证继续保留；没有编造规范、阈值或故障。

## 评分及分组

strict_characters是含标点/空白的严格CER；characters保留旧兼容CER。术语按标准ID及次数报告精确率、召回率，另列alias_equivalent_terms；编号按类型+序号/ID匹配；numeric_slots按可核对格式和值比较，不猜小数，错误单位不计作正确。油温与绕组温度交换数值不能得满分。没有确认参考/有效分母时为null，不显示100%。可读文本的人工确认候选得分单独显示，不能冒充模型输出改善。

汇总按来源分开，列improved/unchanged/worse次数，再按模型ID/版本、词库版本和纠错开关分组。Windows外部版本来自人工声明，manual不被标为模型输出。旧记录保留原口径，未经迁移确认不混入新汇总。统计次数不是独立录音数量；重复推理请按audio_id及其来源链选取比较。

真实9条是规则开发样本，另有16条独立合成挑战；没有训练新模型，没有把开发集成绩当未见语音成绩。下一阶段应另采电力音频，冻结词库后盲测，并逐条核实参考、相别与测量值。

## SenseVoice安装、版本、许可与故障路径

环境：Ubuntu26.04 / Linux x86_64，检查时可用磁盘约946GiB、内存约16GiB、20逻辑CPU。系统Python3.14.4未替换；由于[官方PyPI](https://pypi.org/project/sherpa-onnx/1.13.8/)有cp314 Linux x86_64 wheel，使用独立`.venv-asr`，不需要安装3.11/3.12或修改RobotTerminal环境。

依赖：sherpa-onnx1.13.8、sherpa-onnx-core1.13.8、NumPy2.5.3；[requirements-asr.txt](../requirements-asr.txt)固定版本，[asr_pip_install.json](../reports/asr_pip_install.json)记录下载源及wheel哈希。

模型：`InspectionBrain/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx`及`tokens.txt`。[官方模型文档](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html)提供该包；压缩文件163,002,883字节，发布SHA256为`7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e`，下载已核验。各文件大小/哈希见 [sensevoice_installation.json](../reports/sensevoice_installation.json)。不执行包内export-onnx.py。

许可核查：sherpa-onnx代码为[Apache2.0](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE)。模型包LICENSE指向FunASR模型许可；[SenseVoiceSmall模型卡](https://huggingface.co/FunAudioLLM/SenseVoiceSmall)标model-license，不能把代码许可当作权重许可。[FunASR MODEL_LICENSE](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)为自定义模型协议，包含来源/作者/模型名保留要求；保留包内LICENSE及来源信息。本轮仅独立本地验证，未重新分发模型或部署现场。

```bash
# 当前环境已安装；后续重建仅写InspectionBrain
python3 InspectionBrain/install_sensevoice.py

# 可复现真实WAV诊断，不填任何手动转写
InspectionBrain/.venv-asr/bin/python InspectionBrain/diagnose_asr.py \
  InspectionBrain/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
```

诊断输出模型ID/版本、provider、Python环境、真实采样率和时长、推理耗时、原转写和错误；[本轮真实诊断](../reports/sensevoice_real_wav_diagnostic.json)。CPU默认2线程，子进程虚拟地址空间上限4GiB，模型加载30秒/推理45秒超时。没有GPU或云识别默认路径。

长录音最长60秒，按约20秒连续分段，优先在低能量窗口切分；不做VAD删除、不做文本去重，保留每段起止与原输出。没有丢弃/重复输入帧，但硬切边界仍可能影响单词，需要人工核查，未声称长句零漏识别。音频做真实单声道及线性重采样，绝不只改元数据。

Ubuntu缺少ensurepip，安装器使用官方哈希核验pip wheel在venv内引导，没有apt或系统pip安装。初次虚拟环境创建方式失败后已修复；保留失败记录便于审计，以后续成功安装和实际推理报告为准。下载/库不兼容/模型缺失/超时显示清晰错误，ASR不可用时网页仍支持录音保存及人工文本。模型、venv、下载缓存、用户录音均加入InspectionBrain/.gitignore。

## 测试

```bash
cd /home/user/inspection_robot/InspectionBrain
.venv-asr/bin/python -m unittest discover -s tests -v
node tests/test_voice_audio.mjs
node tests/test_voice_browser.mjs
```

在系统Python运行时真实模型测试会明确跳过；本轮使用独立环境实际执行，不以跳过冒充成功。测试/完整验收计数见 [round2_validation.json](../reports/round2_validation.json)，完整日志[round2_tests.log](../reports/round2_tests.log)。真实HTTP测试用官方样例，原74条v1文本回归继续运行。

最终执行结果：71项Python测试、5项Node测试通过，失败0、跳过0。额外实际验证系统Python启动器自动选择独立环境、模型就绪、9条真实历史导入及自动停止。原系统及用户导出共9,633个受保护文件全部不变。测试服务已停止，等待下一阶段指令。

所有新增在InspectionBrain，完成后停止。原项目与用户导出文件的前后SHA256校验见[round2_integrity.json](../reports/round2_integrity.json)。
