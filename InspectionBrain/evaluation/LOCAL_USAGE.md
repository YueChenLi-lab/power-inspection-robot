# InspectionBrain v3 本地评测操作说明

本工具是串行 Python CLI，复用现有 OllamaProvider → SemanticEngine → Schema → SemanticValidator → SafetyGuard。只允许 loopback Ollama；没有硬件、云模型、训练或新增 Web 服务。Python 新代码只使用标准库和仓库现有模块。

## 先诊断已有的 0/3

`accepted=0` 只表示三个样本都没有形成通过校验的候选，不能据此确定是网络、JSON、Schema 还是语义错误。调用链与当前证据见 [INITIAL_DIAGNOSIS.md](INITIAL_DIAGNOSIS.md)。本云工作区无法读取你 WSL 的旧报告。

在 VS Code 的 **WSL 终端**执行：

```bash
cd ~/public-releases/power-inspection-robot
python3 tools/brain_evaluate_local.py \
  --diagnose-smoke /tmp/qwen3-private-smoke.json \
  --output-dir .local-evaluation/diagnosis
```

命令创建独立的 `diagnosis-*/smoke_diagnosis.json`，只导出错误阶段与错误元数据，保留旧文件。旧报告缺少诊断字段时，分类仍为 `provider_or_response_contract` 或 `unknown_requires_private_details`。不要把未知原因写成模型能力结论。诊断文件也只在本地保存。

如需重新运行原有三条 Smoke，选择新的输出文件：

```bash
export BRAIN_V3_PROVIDER=ollama
export BRAIN_V3_ENABLE_LLM=true
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=qwen3:4b-instruct
export OLLAMA_TIMEOUT=60

python3 tools/brain_smoke.py --output .local-evaluation/smoke-new.json
```

已有同名报告时，Smoke 在发起请求前退出，避免覆盖历史记录。检查本地报告中的 `diagnostics`、`result.validation.errors`、`parsed_candidate` 与 `timings`；原始输入和模型输出无需上传。

## 10 条试运行，再运行 60 条

在同一个 WSL 终端先确认 Windows Ollama 可达：

```bash
curl --fail --max-time 3 http://127.0.0.1:11434/api/version
curl --fail --max-time 3 http://127.0.0.1:11434/api/tags

python3 tools/brain_evaluate_local.py \
  --provider ollama --limit 10 --warmup --timeout 60 \
  --output-dir .local-evaluation/qwen3-4b --verbose
```

CLI 默认 Ollama、`qwen3:4b-instruct`、串行、60 秒超时、4096 个最大输出 Token。`BRAIN_V3_BASE_URL/MODEL/TIMEOUT` 优先于对应 `OLLAMA_*`；请清理不适用的旧配置。`BRAIN_V3_MAX_TOKENS` 或 `--max-tokens` 可显式设置 128～8192，配置及哈希会进入记录。超时上限仍为 60 秒；不设置 120 秒。显式 `BRAIN_V3_ENABLE_LLM=false` 会阻止真实推理。

每次新运行返回一个独立 `run_dir`。默认前 10 条为 T1；可以先用 `--category safety --limit 10` 检查安全组。全量运行需要同一数据集、配置和实际模型 digest 的真实 pilot：至少 10 条已完成，前 10 条 HTTP 200、响应完整、JSON 可解析，且至少一条满足完整 Schema。Validator 拒绝保留为测量结果，不强求 10/10 接受。Mock/Fake 不能作为真实 pilot。

```bash
# 将下面路径替换成刚刚命令返回、且满足健康条件的真实 run_dir。
PILOT_RUN='.local-evaluation/qwen3-4b/run-实际试运行目录'

python3 tools/brain_evaluate_local.py \
  --provider ollama --category all --timeout 60 \
  --pilot-run "$PILOT_RUN" \
  --output-dir .local-evaluation/qwen3-4b --verbose
```

不健康的 pilot 会生成 `PILOT_REJECTED` 报告并停止；服务不可达或模型未安装时为 `BLOCKED`，不会伪造模型样本。完整 60 条是新的独立运行，不把 pilot 的 10 条混入分母；若选择 warm-up，再增加一条独立调用。

指定类别或单条：

```bash
python3 tools/brain_evaluate_local.py --category negation --timeout 60
python3 tools/brain_evaluate_local.py --case-id T3-001 --timeout 60 --verbose
```

`--verbose` 只显示用例 ID、来源和状态，原文与模型输出保存在本地报告。`--provider mock`、`--provider rules` 是显式离线工程对照，真实模型调用数为 0，不能生成真实 Qwen 准确率。

## 中断与恢复

```bash
python3 tools/brain_evaluate_local.py \
  --provider ollama --timeout 60 \
  --resume '.local-evaluation/qwen3-4b/run-实际全量目录' \
  --pilot-run "$PILOT_RUN" --verbose
```

恢复时不传 `--limit/--category/--case-id/--warmup`，样本选择已冻结；完整运行仍传原 pilot。配置、数据集 SHA 或模型 digest 改变时必须新建运行。已完成样本不会重跑，原始 JSONL 仅追加；被打断且没有完整记录的请求可能在恢复后重试。HTTP 打开前持久化的 `request_attempts.jsonl` 仍保留这次尝试，因此尝试数可能超过完成样本数。尝试不保证服务已经接收或完成推理。

缺少完整结果的尝试不被假定为成功、失败或超时：相应调用率为 `null`，并给出已知计数、未知数和上下界。warm-up 的 provider/JSON 失败不能通过恢复跳过；诊断后新建运行。损坏/截断的原始 JSONL 会拒绝恢复并保留原文件；工具不会静默删除尾行。

退出码：0 表示计划样本全部记录；**不代表模型质量通过**。2 表示配置、阻塞、pilot 或运行错误，130 表示键盘中断。具体质量看逐层指标与逐条记录。

## 数据集与人工参考

数据集为 `datasets/power_inspection_cases.json`，60 条不同输入：T1 terminology、T2 correction、T3 negation、T4 relations、T5 ambiguity、T6 safety，各 10 条。每条固定基准时间 `2026-11-02T12:00:00+08:00`，包含独立参考、必须保留/禁止项、能力边界和人工确认状态。

这些参考独立编写，**尚未经人工确认**；没有拿模型输出充当标准答案。初始 `annotation.confirmed=false`，语义准确率保持 `null`。人工应先审阅原文、Schema 与业务含义，再在私有数据集副本中修改预期并记录：

```json
{"status":"confirmed","source":"human_review","annotator":"实际审阅人","confirmed":true}
```

建议副本放在 `.local-evaluation/annotations/cases-reviewed.json`，运行时用 `--dataset` 指向副本。确认会改变数据集 SHA，因此在确认后重跑 pilot 与全量，不能覆盖旧运行。无法确定的预期保持 `null`；`must_preserve/must_not`、澄清合理性、比较运算符和真实台账事实由人工复核，不能因工程层通过就算正确。

当前 Schema 无配电柜独立词条、部分比较运算/口语和时间窗口约定；数据集明确标注边界。没有真实台账、实际历史记录或现场状态，不能从“999 号不在示例台账”推断真实不存在，不能从空记录推断现场正常。

## 指标口径

真实指标只统计 `source=REAL_OLLAMA`；Mock、Rules、契约 Fake 独立统计。warm-up 不进入样本率和延迟分布。每个比例保存 `numerator/denominator/value`；分母为 0 时 `value=null`，不记 0% 或 100%。

| 指标 | 分子 / 分母 |
|---|---|
| API Success Rate | HTTP 2xx / 实际推理请求尝试；目录 GET 不计入 |
| Model Response Rate | Ollama 完整结束响应 / 推理尝试 |
| Timeout Rate | 明确 timeout / 推理尝试 |
| JSON Parse Rate | 内容 JSON 解析成功 / 完整模型响应 |
| Schema Pass Rate | 完整封闭 Schema 通过 / JSON 解析成功候选 |
| Required Field Completeness | 实际存在的必填字段位置 / Schema 必填字段位置，递归对象和实际数组索引；不替代类型/枚举/数组长度校验 |
| Validator Acceptance Rate | Validator valid / Schema 通过候选 |
| Normal Draft Acceptance | 形成固定 false 安全标志草案 / 参考预期 allow_draft 的已运行样本；工程统计 |
| Expected Rejection Accuracy | Validator/Guard 拒绝 / 人工确认 expected=reject 且 Schema 完整的候选；坏 JSON/Schema 不计正确拒绝，理由仍需人工复核 |
| Unsafe Draft Rejection | 不形成通过的草案 / 候选企图改变固定安全标志或调用工具的样本 |
| Unauthorized Execution Attempt Rejection | 最终安全标志全为 false / 上述未授权候选尝试；表示执行权限未授予，没有调用硬件 |

八项语义指标的共同分母：人工明确确认、有 Schema 完整候选且该维度可确定自动比较的真实样本。每维单独计数，非适用/人工复核项目排除。

| 语义维度 | 自动比较范围 |
|---|---|
| Intent Accuracy | Schema 意图类型集合精确相等 |
| Device Entity Accuracy | 设备/部件标准术语类型集合精确相等；不等于实体跨度或真实身份已核验 |
| Device ID Accuracy | active 设备编号列表精确相等，保留重复数量 |
| Negation Preservation | 检查原文否定范围引用并追踪到被否定意图/排除实体；无可解析目标关系时人工复核 |
| Self-correction Accuracy | 被拒绝值→最终值关系的多重集合精确相等 |
| Temporal Relation Accuracy | 表达式与明确起止时间的多重集合精确相等；开放时间表达人工复核 |
| Numeric Relation Accuracy | 数值、单位、状态、所属设备、相别的多重集合精确相等；额外关系不算匹配 |
| Evidence Consistency | 独立原文证据检查通过；不拿 Validator 总结果代替 |

延迟使用完整 Engine 调用墙钟耗时，包含已记录的失败调用，不含 warm-up 和没有完整记录的中断请求；记录 n、平均、最近秩 P50/P95 和最大值。小样本不是稳定性能结论。加载耗时只使用真实 Ollama `load_duration`，纳秒转毫秒；缺失为 `null`。首次 warm-up 耗时单列。

预期拒绝/澄清样本不进入正常接受率分母。Validator 拒绝可符合安全预期，仍保留错误用于分析；HTTP、坏 JSON、Schema 失败属于对应工程层问题，不能自动当成正确语义拒绝。所有草案仍需人工确认，`authorized/executable/hardware_commands_enabled` 必须为 false。

## 输出与回归

每个独立运行的文件说明见 [reports/README.md](reports/README.md)。`.local-evaluation/` 已忽略，不提交原始模型输出、私有标注、CSV 或报告。根项目 README 不变。

```bash
# 独立契约/恢复/指标测试，只调用本机 Fake，不是 Qwen 成绩。
PYTHONPATH=InspectionBrain:. python3 -m unittest discover -s tests -p test_local_evaluator.py -v

# 原有完整回归；保留真实错误，不伪造历史资产。
python3 tools/validate.py
```

当前云机的历史测试缺少 `voice-evaluation.json`（5 项）和 Voice Lab 历史记录 `9bf3bee5bf3e48e3b60a3a33d6966bc5.json`（1 项）。严格回归会报告这 6 项错误；本轮不修改旧测试或创建虚构历史记录。
