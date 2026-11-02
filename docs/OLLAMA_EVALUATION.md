# InspectionBrain Evaluation Lab v0.1

## 目标与复用边界

本地浏览器工程评测台，验证真实模型接入质量，不是聊天窗口、模型训练或 Agent 框架。复用现有 SemanticEngine、OllamaProvider、封闭 Schema、SemanticValidator、SafetyGuard 和独立 check_evidence。没有改 v2、SenseVoice、voice_lab 或 InspectionOS 执行代码。

原 SemanticStore 按同日配置缓存语义结果，不能满足“每次独立推理均保存”和版本化人工标注，因此使用单独 SQLite 存储 evaluation / annotation / batch。它不加载旧 ASR、音频、示例台账或巡检记录。

## 启动

Python >=3.10，标准库，无 pip/npm 安装步骤。从仓库根目录运行：

```bash
OLLAMA_BASE_URL=http://127.0.0.1:11434 \
OLLAMA_MODEL=qwen3:4b-instruct \
OLLAMA_TIMEOUT=60 \
python3 InspectionBrain/run_evaluation_lab.py --port 8891
```

`qwen3:4b-instruct` 仅为用户提供的示例标签，不在 Lab 中硬编码；也可不设置 OLLAMA_MODEL，检查连接后从实际安装列表选择。后端必须与 Ollama 在可访问的本地环境；云机的 127.0.0.1 不是用户 Windows/WSL 本机。Lab v0.1 只接受 loopback Ollama 地址，不配置远程服务或外发文本。

浏览器地址为本机 `http://127.0.0.1:8891/`。后端监听固定 127.0.0.1，不接受公网 bind 参数。Ctrl+C 停止。默认数据库为 InspectionBrain/runtime/evaluation_lab/evaluations.sqlite3，可用 `--db /tmp/isolated-lab.sqlite` 指定独立路径。请不要指向其他应用的数据库。

## 四页工作流

1. **模型评测**：检查 `/api/version` 与 `/api/tags`，显示实际版本、模型列表、digest / details；选择模型、用例或手动文本、带时区 reference_time，再运行。输入修改后作为手动输入，不错误绑定原用例。
2. **批量评测**：选择用例，按同一 reference_time 顺序执行，保存每条记录与持久化进度。COMPLETED 表示循环完成，不表示每条 ACCEPTED；失败结果仍保留。单进程全局推理锁拒绝并发运行（HTTP 409），不会并行加载模型。
3. **统计**：按来源、模型、digest、配置、Prompt 和 Schema 分组，显示条件分母、延迟区间、类别表现、人工准确率、失败与安全违规。没有记录时为空，不预填演示指标。
4. **历史与标注**：按来源/类别筛选，查看每层详情，导出 JSON / CSV / Markdown；独立标注证据与七类语义维度。未评留空，必须明确确认和填写审阅标签。标签不是身份认证。

每次运行都有独立 evaluation_id；不会因文本相同而复用前次推理。annotation 为追加版本，绑定原文和显示候选 SHA256，统计仅采用最近一次明确人工确认的标注。模型输出不会写入 expected，也不会自动勾选正确。

## 分层与结果解释

原文 → build_evidence → Provider → 严格 JSON → Schema → 原 SemanticValidator → SafetyGuard → 不可执行草案。Lab 还复用独立工程 Evidence Constraint 检查，与完整 Validator 和人工 Evidence Consistency 分开展示。Native 请求传入完整 `format=SCHEMA`、`stream=false`、`think=false`，无工具。

- **ACCEPTED**：当前结构、证据及完整规则校验通过；不代表人工确认，更不代表现场事实或可执行。
- **NEEDS_CLARIFICATION**：通过检查但存在未解析时间、未知意图或“那个/记不清/也可能”等保守提示；不是完整中文歧义消解系统。
- **REJECTED**：模型响应的解析、结构、证据或安全合同不通过。
- **PROVIDER_ERROR**：服务/安装模型不可用、超时、HTTP 错误或响应截断；不自动 Mock，也不伪造 JSON。

SafetyGuard 对失败候选封装空草案，对通过候选重建草案；三个安全字段始终 false。候选中的违规字段和工具调用尝试另计，不让模型修改固定安全结果。Lab 不导入 OS 或任何机器人驱动，没有 approve / execute / motion 接口。

## 数据集与人工评测

12 条合成开发样本包含任务指定的 T1–T10，加上多设备数值绑定与条件约束。每条有 case_id、category、original_request、expected、must_preserve、must_not、annotation_status、annotator、notes；初始全部 pending / annotator=null。

这些期望独立维护，并非模型生成或已确认人工 Gold。Provider 请求只含原文、原规则证据、术语候选及约束，不包含 expected、参考答案或人工标注。使用者独立核查后，才可在记录页对 intents、equipment_relations、numeric_relations、negations、self_corrections、temporal_constraints、task_dependencies 标注 true / false / 未评。

| 指标 | 口径 |
|---|---|
| Request Success Rate | 完整响应 / 全部请求 |
| JSON Parse Rate | 成功解析 / 完整响应 |
| Schema Pass Rate | Schema 通过 / 成功解析 |
| Validator Acceptance Rate | 完整 Validator 接受 / Schema 通过 |
| Human Evidence Consistency | 已人工确认一致 / 已人工标注证据样本 |
| Semantic Accuracy | 正确维度 / 已人工标注维度（不含未评） |
| Engineering Evidence Constraint | 原文确定性约束通过 / 已解析样本；非人工指标 |
| Latency | 目录预检查、分析、推理、校验的端到端时间；不含落库，另显示 Provider 时间 |
| P50/P95 | nearest-rank，显示 N；N<30 提示小样本，非稳定性能结论 |
| Fallback Count | 实际自动回退次数；本 Lab 不自动回退，显式 RULES 不计回退 |
| Safety Violation Count | 解析候选或响应中违反固定权限/工具约束的数量 |

无分母显示 null。REAL LLM、MOCK、RULES 不混合统计；工程 HTTP 夹具另标 MOCK HTTP，不能计为真实效果。Mock / Rules 对照有明确标记的 JSON 序列化步骤，不冒充原生模型响应。

Ollama `*_duration` 为纳秒，存储原 ns 并除以 1,000,000 得 ms；prompt_eval_count / eval_count 保持 Token 计数。缺失或无效元数据为 null。原响应、解析候选、Schema/Validator 结果、digest、Prompt/Schema 版本及 SHA、原文、reference_time、配置和时间戳均存储；API Key 不读入页面或记录。

## 思维链与本地保护

不要求模型隐式思维链。已知 thinking/reasoning/reasoning_content 等字段与 think 标签在持久化前剔除；原文输入保持完整。界面“原始响应”是剔除思维链后的诊断响应，不保证字节等于传输原文；记录剔除前原响应 SHA256 与 redaction 标志。校验在剔除前执行，避免删除非法字段后错误接受模型结果。

Host / Origin / Sec-Fetch-Site 检查、POST 随机令牌、JSON 类型/大小限制、固定静态资源映射、CSP 和 textContent 渲染保护本地页面。前端只访问 Lab 同源后端，不直接访问 11434。无生产用户认证，不允许将页面或 11434 暴露公网；不上传真实台账、记录或凭据。JSON/CSV 可能包含用户原文，应由使用者管理访问；CSV 对公式前缀做转义。

## API 与复现

| 接口 | 用途 |
|---|---|
| GET /api/config、/api/dataset | 本地配置、CSRF 与独立用例 |
| POST /api/models/check | 后端检查实际模型目录，不接受任意 URL |
| POST /api/evaluate | 单条；provider / model / case_id 或 original_request / reference_time |
| POST /api/batches，GET /api/batches/id | 顺序批量与实际进度 |
| GET /api/records、/api/records/id | 查询、来源与类别筛选 |
| GET /api/statistics、/api/export | 分组指标与 JSON / CSV / Markdown |
| POST /api/annotations/id | 独立人工确认，追加记录 |

```bash
PYTHONPATH=InspectionBrain:. python3 -m unittest discover -s tests -p 'test_evaluation_lab*.py' -v
node --test tests/test_evaluation_lab_frontend.mjs
OLLAMA_MODEL=qwen3:4b-instruct python3 InspectionBrain/run_evaluation_smoke.py --output /tmp/fresh-qwen3-smoke.json
```

真实 smoke 覆盖 T1/T5/T3/T4/T8 五类，不提供 Mock 开关，不覆盖已存在的报告。服务或模型缺失返回 BLOCKED / exit 2；模型可达但工程校验失败为 FAIL / exit 1；全部五类通过当前工程合同才 PASS / exit 0。人工语义仍为 PENDING，不能因 Smoke PASS 就宣称准确率。

局限：一次只运行一个 Lab 进程；没有分布式队列、多人认证、分页或 ASR 入口。进程中断后的 RUNNING batch 在重启标 INTERRUPTED，不自动重放；已提交记录保留，尚未保存的单次推理不保证恢复。全机其他 Ollama 客户端不受本进程互斥锁控制。
