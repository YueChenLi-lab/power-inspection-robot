# ASR热词能力核查与可选配置

核查日期：2026-10-08。源码只读核查，没有导入Vosk/SenseVoice、修改模型或运行音频识别。

## 当前工程事实

- `RobotTerminal/backend/interaction.py:709` 使用`vosk.KaldiRecognizer(self.asr, 16000)`，未传grammar，也没有SetGrammar调用。当前生产路径没有启用领域语法/热词。
- `backend/asr_worker_candidate.py:145` 使用`sherpa_onnx.OfflineRecognizer.from_sense_voice`，参数包括model、tokens、线程、采样率、language、use_itn和cpu provider，没有热词参数。
- `backend/gateway.py:88–164`按浏览器ASR配置启用SenseVoice隔离worker，固定2线程；无配置走Vosk。candidate文件头“not wired into gateway”落后于实际调用。
- 本地未读取真机运行模型或已安装库源码；实际安装版本和模型动态词图需后续独立验证，不能把上游最新版API当成真机验证通过。

## 上游接口证据

Vosk官方Python接口存在第三参数grammar和SetGrammar；官方模型适配说明区分动态与静态语言图，动态模型可用语法预选识别候选。这里属于词表/语法约束，不是任意软热词加权，也不能凭语法加入模型完全未知的词。[官方Python接口](https://raw.githubusercontent.com/alphacep/vosk-api/master/python/vosk/__init__.py)、[官方模型适配说明](https://alphacephei.com/vosk/lm)

sherpa-onnx官方热词文档明确将热词支持限定于transducer与modified_beam_search；SenseVoice接口未提供hotwords_file/hotwords_score。因此当前SenseVoice路径不支持该类热词配置。[官方热词文档](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html)、[官方SenseVoice Python接口](https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/master/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py)

## 本阶段选择

两个ASR路径均保留原样；规范化只在独立Brain文本入口发生。同音候选默认suggestion_only，显式开启也只作用于白名单只读问题，设备身份仍来自原文，不能授权动作。

`hotwords.optional.json`是未来独立Vosk实验的配置候选，enabled=false，production_integration=false，含领域短语与`[unk]`。`export_vosk_grammar()`只返回JSON，不加载模型，不调用SetGrammar，不改变原控制词/固定回答/识别流。后续若做语法实验，应新建独立识别器，验证该模型词表和动态图，保留未约束基线，收集真实中文专业词音频；不得覆盖原控制识别器。

`[unk]`也不保证开放词汇与原识别器等价。热词/语法识别效果不能从本轮文本回归推导；本轮没有ASR WER/CER改善结论。
