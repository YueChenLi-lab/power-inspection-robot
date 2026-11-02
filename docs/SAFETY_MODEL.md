# 安全模型与审批

Brain SafetyGuard 约束语义输出；OS SafetySupervisor 约束模拟任务执行，两者独立。Schema 合法或模型说“已批准”都不能授权任务。

| 请求 | 策略 |
|---|---|
| 已注册、低风险、mock scope 的三个查询/建议 Skill | 可执行模拟业务 |
| 高风险 mock scope | WAITING_APPROVAL，需独立本地操作员凭据 |
| motion 风险或非 mock scope | 始终 DENY，即使提供审批 |
| 未注册 Skill | 拒绝受理 |
| 模型动作或带真实授权的草案 | 适配层拒绝 |

可信注册方必须正确设置 risk_level / execution_scope；本系统不分析任意 Python 函数的真实副作用。不能把任意硬件函数标为低风险后声称获得沙箱保护。仓库只提供 Mock 执行能力，没有机器人驱动。

审批入口是 `MissionManager.approve(mid, actor=..., token=..., allow=...)`，token 由应用组合根独立注入 `operator_token`，默认为禁用审批。凭据不能放入自然语言、payload、数据库、日志或提交文件；测试里的固定字符串只用于本地单元测试。成功批准、拒绝和认证失败尝试均写审批与事件记录。即使认证成功，policy DENY 仍不可覆盖。

需要网络授权的 Skill 在离线时等待网络，恢复后仍需独立审批，不因恢复而放宽安全。当前审批是本地进程信任边界，不是具有身份管理、权限撤销和远程认证的生产服务。Supervisor 不代表整机安全认证，现场底层停车逻辑也未在此仓库实现或修改。
