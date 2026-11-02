# 第二轮电力词库增量清单

总数50；原28个ID及不同设备类型保持独立，新增22个。另给原条目补context_keywords/risk_level/correction_policy等字段。v1词库文件未覆盖，v2默认供新页面使用。

|变更|term_id|标准名|类别|新增混淆候选|风险 / 策略|
|---|---|---|---|---|---|
|补混淆|current_transformer|电流互感器|equipment|电流护管护感器|medium / context_readonly_opt_in|
|补混淆|winding_temperature|绕组温度|metric|绕阻温度|low / context_readonly_opt_in|
|补混淆|asset_registry|设备台账|business|设备抬杠|low / context_readonly_opt_in|
|新增|switching_state|分合闸|business|分和闸|high / candidate_only|
|新增|relay_protection|继电保护|equipment|祭奠保护|medium / context_readonly_opt_in|
|新增|ct_secondary_circuit|电流互感器二次回路|equipment|电流护管护感器二次回路|medium / context_readonly_opt_in|
|新增|human_review|人工复核|business|人工复合|low / context_readonly_opt_in|
|新增|onload_tap_changer|有载分接开关|equipment|由窄分接开关|high / candidate_only|
|新增|insulator_flashover|绝缘子污闪|defect|绝缘子钨闪|medium / context_readonly_opt_in|
|新增|pollution_flashover|污闪|defect|钨闪|medium / context_readonly_opt_in|
|新增|switching_operation|倒闸操作|business|道闸操作|high / candidate_only|
|新增|sf6|六氟化硫|business|6伏化流、6氟化硫|high / candidate_only|
|新增|sf6_pressure|六氟化硫气体压力|metric|6伏化流气体压力、6氟化硫气体压力|high / candidate_only|
|新增|phase_a_joint|A相接头|equipment|a箱接头、A箱接头|high / candidate_only|
|新增|phase_b_joint|B相接头|equipment|b箱接头、B箱接头|high / candidate_only|
|新增|phase_a|A相|metric|a箱、A箱|high / candidate_only|
|新增|phase_b|B相|metric|b箱、B箱|high / candidate_only|
|新增|cooling_fan|冷却风机|equipment|无|low / context_readonly_opt_in|
|新增|busbar_joint_rise|母线接头温升|metric|无|high / candidate_only|
|新增|busbar_joint|母线接头|equipment|无|medium / context_readonly_opt_in|
|新增|transformer_bushing|变压器套管|equipment|无|medium / context_readonly_opt_in|
|新增|hv_joint|高压侧接头|equipment|无|high / candidate_only|
|新增|zero_sequence_current|零序电流|metric|无|high / candidate_only|
|新增|supply_reliability|供电可靠性|business|无|low / context_readonly_opt_in|
|新增|grounding_switch|接地刀闸|equipment|无|high / candidate_only|

A/B相接头与A/B相各自独立；继电保护装置、二次回路、冷却风机、套管等不合并不同设备类型。倒闸/分合闸等高风险候选不产生执行授权。

时千伏、未知小数点、赵帕以及供电可****性不按参考文本自动补齐。数字/单位风险另由数值模块输出。
