# 历史测试资产、严格回归与 CI 前置条件

## 查找结果

在当前仓库现有全部 11 个提交、所有本地/远程已知分支，以及全部可达 Git 对象中查找，以下两个原始文件没有任何已提交版本：

- `voice-evaluation.json`
- `InspectionBrain/runtime/voice_lab/records/9bf3bee5bf3e48e3b60a3a33d6966bc5.json`

已读取远程分支 main、docs/project-overview、feature/edge-task-runtime；没有访问其他本地项目，没有生成替代记录或 WAV。缺失是测试输入资产问题，不能据此认定相关业务代码正确或错误。原 audit 测试还检查导出 SHA256，不可伪造一个同名文件。

| 缺失资产 | 依赖测试 |
|---|---|
| voice-evaluation.json | test_domain_v2 的 test_multi_intent_and_real_cases、test_real_data_rules_and_switch_are_separate |
| voice-evaluation.json | test_round2_audit 的 test_actual_export_is_read_and_preserved |
| voice-evaluation.json | test_round2_scoring 的 test_complex_query_does_not_claim_complete_answer_from_one_keyword、test_import_preserves_history_and_excludes_unbound_old_metrics |
| 历史 record JSON | test_scoring_workflow 的 test_actual_record_without_reference_leakage |

## 两种明确的执行策略

```bash
# 原默认入口：严格执行，缺资产依然报错，退出码非零
python3 tools/validate.py
# CI：只标记上述确切缺失资产，不删测试、不中和断言
python3 tools/validate.py --original-child --asset-policy skip-missing --summary /tmp/original-summary.json
```

CI 的 asset policy 只对列出的 6 个测试实例，在文件确实不存在时用 unittest skipTest 报告环境前置条件；测试仍计入 tests_run / skipped，不计为 passed。文件存在时原测试完整执行，内容错误仍会失败。未匹配测试不受影响，并设置原套件至少执行 100 项的防误配置检查。原测试源码和期望值均未修改。

本机原套件 121 项：严格方式 111 通过、6 错误、4 模型跳过；CI 资产策略 111 通过、0 错误、10 跳过（6 资产 + 4 模型）。CI 上可选 jsonschema 是否安装还会影响其自带标准实现对照测试的跳过，不能把跳过当成功。普通 CI 不下载大模型、不要求 GPU、Ollama、真实音频或机器人；Brain v3 与运行时关键测试仍实际执行。

## 恢复真实资产的方法

由持有原始数据的项目成员从经授权的归档中恢复到上述相对路径，先核对来源、导出记录和既有 audit 测试的 SHA256；不要改期待值。可能包含私人音频或文本的文件不应直接提交公开仓库，可使用受控环境/CI artifact 或安全存储提供。恢复后运行严格入口和原真实 ASR 测试，并单独记录结果。没有真实文件时，这 6 项仍是未完成验证。
