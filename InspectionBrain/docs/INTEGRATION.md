# 未来路由与Mission接口

本文件是设计与离线模拟合同，未接入生产Gateway。

## 路由顺序

1. 原始ASR文本原样传入原有分发器，不先经过Brain规范化。
2. 原控制命令、停止、固定回复及原支持的状态问答保留旧路径、旧确认和旧返回值。
3. 原路径未匹配、feature flag开启时，仅将电力问答/资料/历史查询或计划草案副本传给Brain。
4. Brain未知、失败、不可用、超时或输出不合法时保留旧决策，不把纠错文本重新送旧控制解析器。
5. Brain的提案和草案只供人工审阅，没有授权转换操作。原文中的动作即使被否定/引用，也在模拟层保守保留原路径。

模拟入口`OfflineRouter`默认enabled=false；LegacyDispatcher是注入协议，本轮使用MockLegacyDispatcher。LegacyDecision.payload保留原对象，不改旧固定回复。已运行的Brain请求最多1个；超时只返回旧路径，后续Brain忙碌直接回退，不累积等待队列。默认本地Brain无网络或模型加载。

目前模拟采用线程隔离与有限等待；线程不能强制终止任意挂死的Python/原生provider。生产若接外部LLM必须采用可终止子进程或具有硬截止时间的独立服务，关闭/超时不能等待挂死provider。本轮没有任意LLM或生产路由集成。

## 权限与数据

Brain仅接受文本、文档和只读数据适配合同，不持有CAN socket、ROS publisher、导航lease、CSRF令牌、Gateway控制cookie或任意HTTP工具。`authorized`/`executable`字段固定false。未来对接实时只读数据必须附采样时间、时区、单位、来源、valid与设备版本；过期/未绑定设备/缺限值输出不可判定。

当前Mock台账匹配要求设备类型与编号都一致；编号和序号相互矛盾时无匹配。它不查询真实SQLite。未来真实台账/巡检库适配器只读实现EquipmentRegistry/InspectionRecords，必须解决身份歧义、查询范围和权限，并新增证据验证层；本轮所有数据查询仍拒绝现场结论。

## Mission Manager准备接口

MissionDraft包含schema_version、requested_text、devices、steps、unresolved与`draft_requires_review`。步骤仅为`review_inspection_requirements`和示例检查项，没有Navigate/drive执行调用。OfflineDraftSink不持久化、不授权；未来MissionDraftSink可保存草案，不能据“提交草案”自动创建运动租约。

真实Mission Manager必须另行检查设备、地图、几何、围栏、数据新鲜度、实测停车裕量与真实监督授权；沿用RobotNavigation和底盘最终检查。任何ASR热词、纠错结果、知识回答、示例数据或“计划已创建”都不能满足这些授权条件。

关闭feature flag只是回到原处理，不关闭机器人安全保护、不恢复旧运动、不改原回复。下一阶段集成应先只读旁路观察和回归，独立部署批准后才增加薄代理；本轮完成后停止。
