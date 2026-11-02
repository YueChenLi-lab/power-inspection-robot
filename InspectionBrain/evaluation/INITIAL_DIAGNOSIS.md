# 本地 0/3 Smoke 的初步诊断

## 证据范围

用户报告 Windows Ollama 0.40.2、qwen3:4b-instruct、4B Q4_K_M，WSL 可访问 API，旧 Smoke 的输出为 samples=3、accepted=0。这里只能确认没有任何样本进入 validated_candidate，不能由此断言 API、JSON 或语义哪一层失败。

本会话工作目录是 /workspace/power-inspection-robot；用户指定的 ~/public-releases/power-inspection-robot 和 /tmp/qwen3-private-smoke.json 均不可读/不存在。不能把云机缺 Ollama 的现象作为用户 WSL 的根因。真实 0/3 根因标记 **PENDING_LOCAL_ERROR_METADATA**，等待仅含 status/error/validation.errors/diagnostics 的信息，不要求上传原始输入和模型输出。

## 已审计调用链

ProviderConfig → make_provider → OllamaProvider.generate → POST /api/chat（完整format=SCHEMA、stream=false、think=false）→ 严格响应JSON与message.content JSON解析 → SemanticValidator（先封闭Schema，再原文引用/关系/语义约束）→ SafetyGuard重建不可执行草案 → SemanticEngine结果。

inspection-task-draft-v3.0 不等于可执行命令。InspectionOS 的 BrainAdapter 会独立重校验并仅映射 Mock，本轮评测不导入或启动它。

## 排查判据

| 实际证据 | 分类 |
|---|---|
| HTTP/连接错误、timeout、disabled | Provider调用失败，不能算JSON/语义错误 |
| done=false / done_reason=length | 响应未完整结束；检查实际Token和原报告，不擅自升超时或截断后接受 |
| json_parse_success=false | JSON解析失败 |
| schema_errors非空 | 必填、类型、枚举、额外字段或固定安全常量失败 |
| Schema通过但validation.valid=false | 原文证据或关系/业务语义拒绝，保留具体errors |
| 上游拒绝且Guard空草案 | 失效安全封装，不是自动授权，也不单独归因为Guard缺陷 |

只有摘要没有上述字段时，原因未知。60秒超时、4096输出Token、复杂Schema或模型未保留证据都是待检查项，不是已证实结论。

## 最小修改范围

不修改Schema、Validator、SafetyGuard、v2或OS。旧smoke补充不含原文/原响应的失败阶段摘要；新CLI可离线读取既有报告诊断，再用逐条附带HTTP/解析/结构/完整校验/安全状态的私有JSONL定位。未知字段保持unknown，不用Mock冒充真实结果。

```bash
python3 tools/brain_evaluate_local.py --diagnose-smoke /tmp/qwen3-private-smoke.json --output-dir .local-evaluation/diagnosis
```
