# Qwen3 / Ollama 接入与验证边界

原 OpenAI Compatible Provider 可以请求 Ollama 的兼容端点，但只请求 json_object。新增原生 Ollama Provider 是为使用 `format=现有完整Schema`，其他语义安全模块复用不变。

```bash
# 在有 Ollama 和已安装模型的机器，仓库根目录执行；不会自动下载或训练模型
BRAIN_V3_PROVIDER=ollama BRAIN_V3_ENABLE_LLM=true \
OLLAMA_BASE_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen3:4b-instruct \
OLLAMA_TIMEOUT=60 python3 tools/brain_smoke.py --output /tmp/qwen3-private-smoke.json
```

现有 BRAIN_V3_BASE_URL / MODEL / TIMEOUT 优先于 OLLAMA_*，真实调用需显式 enable；rules 默认和旧兼容配置不变。Native 地址不能带 `/v1`，客户端追加 `/api/chat`。默认仅 loopback；非本地地址继续要求原配置的 HTTPS 和显式外发授权，不提供绕过网络或 TLS 验证的选项。

响应必须 done=true、完整结束、无工具调用且为严格 JSON 对象。重复字段、非 JSON 常数、非法结构、过大或截断响应均拒绝；原 Validator 再验证语义，SafetyGuard 保持不可执行。`auto_fallback` 模式可显式回退规则，v3_llm 模式拒绝失败，不冒充模型成功。

Provider.last_response 保存本次有界响应，timings 分别保存请求与解析计时，不含 HTTP headers。诊断可能包含私人原文；只有独立 smoke 显式导出原响应，默认语音实验室不会自动复制到日志。连接或解析失败不会复用上次响应。

本环境没有 Ollama 可执行文件，11434 端口连接拒绝。已完成本地 Mock HTTP 的 T1–T5、原 Schema、语义冲突及超时回退测试；服务端响应明确标为 mock-http-not-real-qwen，不能计为真实 Qwen3 推理。

`tests/fixtures/semantic_cases.json` 是合成开发期望，含设备号、上周时间、否定与纠正。提供人工复核字段但 confirmed=false，不冒充人工语义金标准。smoke 区分 JSON 成功率、Schema 通过率、Validator 接受率、合成关键字段准确率、证据接受率、回退次数与延迟分布；human_gold_accuracy 为 null。原文 evidence 检查不等于现场事实验证。

真实模型输出能否通过合同、Qwen3 质量/延迟和独立人工标注准确率均待实测。本版本只完成可调用接入实现与模拟接口验收，不声称已完成真实模型验收。
