# Skill 合同

`SkillSpec` 定义 skill_id、name、description、input_schema、output_schema、timeout、retryable、idempotent、offline_supported、risk_level、version，并增加 execution_scope 和 requires_network_authorization、recovery_safe。Registry 拒绝重复 ID，未注册 ID 无法受理或执行；排队时绑定版本，领取时发现版本变化会失败。

`execute(payload: dict) -> dict` 为业务入口，Worker 不实现业务。可信注册元数据决定安全、超时和网络策略，用户 payload 不能覆盖元数据。输入输出均通过受支持的封闭 Schema 子集验证；不支持的 Schema 关键字会报错。

| Skill | 功能 | 结果边界 |
|---|---|---|
| mock.alarm_query | 按 Mock 设备及可选时间窗过滤告警 | 无记录不等于现场正常 |
| mock.temperature_query | 模拟红外记录及最近两条差值比较 | 不使用差值判断真实异常；不足两条明确返回不可比较 |
| mock.reinspection | 合并模拟告警与测温形成复核建议 | 不创建导航或运动动作 |

单设备使用 device_id，多设备使用 device_ids（非空、唯一且两者二选一）。设备 ID 仅接受 `MOCK-CB-3`、`MOCK-TR-1`。可选 start/end 必须可解析、含时区且 start < end。compare 为布尔值。输出要求 `is_mock=true`、`source=mock-fixture-v1`、对应设备身份头、records、summary。每条记录也带 Mock 来源。固定样本时间在 2026-10-27 至 2026-10-30，数据是人工构造测试夹具，不是现场记录。

执行截止时间由父进程控制；超时、取消或子进程意外退出会回收子进程。当前 Linux fork 模式不能用于加载任意不可信插件，也不假定具有网络访问隔离。


Registry.validate_output(skill_id, input_payload, output_payload) 先检查结构，再调用 Skill 的 validate_result。Mock 查询的业务层核对输出设备集合等于输入、每条记录属于允许设备、时间在 [start,end) 中、来源可信且告警/测温字段齐备。不同家族的业务钩子独立，不对所有 Skill 强加设备字段。测温多设备比较按设备分组。见[业务层拒绝测试](../tests/test_business_contracts.py)。
