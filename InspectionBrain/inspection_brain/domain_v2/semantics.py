import re
from datetime import timedelta
from ..service import SHANGHAI
from ..intent import ElectricalIntentAnalyzer
from ..safety import operation_proposal
from .numbers import extract_numeric_slots
from .scopes import action_scopes

SOURCES={"inspection_history":["equipment_registry","inspection_records"],
         "temperature_comparison":["equipment_registry","thermometry_records","sampling_metadata"],
         "reinspection_recommendation":["inspection_records","applicable_rules","human_review"],
         "report_draft":["evidence_records","applicable_rules","human_review"],
         "equipment_status_query":["equipment_registry","live_equipment_status","alarm_records"],
         "inspection_plan_draft":["equipment_registry","inspection_procedure","mission_manager_future"],
         "temperature_alarm_query":["equipment_registry","thermometry_records","alarm_records","applicable_rules"]}
SOURCES["anomaly_procedure_explanation"]=["knowledge_documents","inspection_procedure"]
SOURCES.update(thermometry_history=["equipment_registry","thermometry_records","sampling_metadata"],
               temperature_anomaly_query=["equipment_registry","thermometry_records","applicable_rules"],
               temperature_measurement_query=["equipment_registry","equipment_measurements","sampling_metadata"])


class MultiIntentAnalyzer(ElectricalIntentAnalyzer):
    def analyze(self,text,*,now,apply_homophones=False):
        if now.tzinfo is not None:now=now.astimezone(SHANGHAI)
        analysis=super().analyze(text,now=now,apply_homophones=apply_homophones)
        scopes=action_scopes(text)
        query=analysis["normalization"]["normalized_text"]
        intents=[]
        def add(kind,reason):
            if kind not in [row["type"] for row in intents]:
                intents.append({"type":kind,"reason":reason,"required_data_sources":SOURCES.get(kind,analysis["required_data_sources"]),
                                "executable":False,"authorized":False})
        positives=[s for s in scopes if s["polarity"] in ("proposal","conditional")]
        if positives:add("operation_proposal","存在可能操作/条件操作；仅提案，不执行")
        if re.search(r"(?:制定|创建|拟定|安排|生成)[^，。；]{0,30}(?:巡检计划|巡检任务|巡检.*计划)|巡检计划.*草案",query):add("inspection_plan_draft","明确请求计划草案，区别于生成复检建议")
        if re.search(r"巡检记录|历史.*巡检|上次.*巡检",query):add("inspection_history","查询历史巡检记录")
        thermal = bool(re.search(r"测温|温度|油温",query))
        historical = bool(re.search(r"(?:测温|温度|油温)(?:的|结果)?(?:历史)?记录|历史(?:测温|温度|油温)",query))
        explanatory = bool(re.search(r"什么|一般|解释|规程|原理",query))
        if historical and not explanatory:add("thermometry_history","测温历史记录查询，不等于异常或告警查询")
        if thermal and (re.search(r"比较|对比",query) and not re.search(r"不要(?:比较|对比)|不(?:用|需)(?:比较|对比)",query) or re.search(r"最近[三二一四五六七八九十\d]+次测温",query)):
            add("temperature_comparison","识别测温需求前后出现的比较词，比较基准与目标时间分开")
        if thermal and not explanatory:
            if re.search(r"告警|报警",query):add("temperature_alarm_query","明确温度告警 / 报警查询")
            elif re.search(r"异常|过热|超温|超限|偏高",query):add("temperature_anomaly_query","温度异常查询，需要有效读数及适用规程")
            elif not historical and not any(i['type']=='temperature_comparison' for i in intents) and analysis['intent']=='temperature_alarm_query':
                add("temperature_measurement_query","当前测温 / 读数查询，没有告警请求")
        if re.search(r"(?:生成|给出|提供|制定|一份)[^。；]{0,20}复检建议",query):add("reinspection_recommendation","复检建议草案，需要记录/规程/人工复核")
        if re.search(r"(?:生成|整理|给出)[^。；]{0,60}报告",query):add("report_draft","报告草案不等于正式巡检结论")
        if re.search(r"(?:并说明|解释|说明).*(?:影响|异常|原理)",query):add("anomaly_procedure_explanation","综合问题中的解释需求须单独检索，不能靠一个关键词覆盖")
        if re.search(r"有没有.*异常|是否.*异常|运行情况|运行状态|是否存在异常|告警记录|位置|状态",query) and analysis["normalization"]["recognized_terms"]:
            if thermal and not explanatory:
                pass # Temperature queries were classified above; keep status and alarm distinct.
            else:add("equipment_status_query","设备状态/异常查询需要真实数据")
        if not intents:
            previous=analysis["intent"]
            if previous=="operation_proposal":
                # Negated/mentioned controls must not become affirmative proposals.
                if re.search(r"解释|什么|原理|含义",query):previous="anomaly_procedure_explanation"
                elif any(s["polarity"]=="prohibited" for s in scopes):previous="prohibited_operation"
                else:previous="unknown"
            add(previous,"单项领域问题或禁止约束")
        analysis["intent"]=intents[0]["type"]
        analysis["intents"]=intents
        analysis["required_data_sources"]=list(dict.fromkeys(source for row in intents for source in row["required_data_sources"]))
        analysis["action_scopes"]=scopes
        analysis["constraints"]=[s for s in scopes if s["polarity"] in ("prohibited","conditional")]
        analysis["conditional_clauses"]=[m.group(0) for m in re.finditer(r"(?:如果|若)[^。；]+",text)]
        analysis["operation_proposal"]=operation_proposal(text,[s["action"] for s in positives]) if positives else None
        analysis["numeric_entities"]=extract_numeric_slots(text)
        # A calendar week is a comparison baseline, never an implicit target window.
        analysis["comparison_constraints"] = None
        if "上周" in text:
            local = now.astimezone(SHANGHAI)
            monday = local.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=local.weekday())
            baseline = {"expression":"上周","start":(monday-timedelta(days=7)).isoformat(),"end":monday.isoformat(),
                        "resolved":True,"timezone":"Asia/Shanghai","end_exclusive":True,"role":"comparison_baseline"}
            target = dict(analysis["time_range"])
            if any(i['type']=='temperature_comparison' for i in intents):
                analysis["comparison_constraints"]={"operator":"compare","baseline":baseline,"target":target}
            if not target["expression"]:analysis["time_range"]=baseline
            analysis["uncertainties"]=[u for u in analysis["uncertainties"] if u!="未提供查询时间范围"]
            if not target['resolved'] and analysis["comparison_constraints"]:
                analysis["uncertainties"].append("待比较记录的目标时间范围未明确；上周只是比较基准，不默认本周")
        parts=[]
        part_candidates=analysis['normalization']['homophone_candidates']
        for match in re.finditer(r"(?:高压|变压器)?套管",text):
            candidate=next((c for c in part_candidates if c['source_span'][0]<=match.start()<c['source_span'][1]),None)
            owners=[e for e in analysis['device_entities'] if e['term_id'] not in ('bushing','hv_bushing') and e['span'][1]<=match.start() and match.start()-e['span'][1]<=20]
            owner=owners[-1] if owners else None
            parts.append({'standard_name':'套管','surface':match.group(),'source_span':[match.start(),match.end()],
                          'subtype_candidate':candidate['replacement'] if candidate else match.group(),
                          'verification_status':'candidate_requires_audio_review' if candidate else 'text_only',
                          'parent_device_number':owner.get('device_number') if owner else None,
                          'parent_term_id':owner['term_id'] if owner else None,'identity_verified':False})
        analysis['inspection_parts']=parts
        analysis['device_entities']=[e for e in analysis['device_entities'] if e['term_id'] not in ('bushing','hv_bushing')]
        analysis['measurement_methods']=['infrared_thermometry'] if '红外测温' in query else []
        analysis["uncertainties"]=[u for u in analysis["uncertainties"] if not u.startswith("未匹配已支持")]
        if analysis["numeric_entities"]:analysis["uncertainties"].append("数值/单位/编号仅做格式解析，未验证原音频及真实测量，禁止推测小数点或诊断")
        if re.search(r"时千伏",text):analysis["uncertainties"].append("时千伏电压等级未解析，不能猜成十千伏")
        if "****" in text:analysis["uncertainties"].append("输入含遮蔽字符，不能据参考文本擅自还原缺失术语")
        analysis["semantic_version"]="electrical-semantics-v2.3"
        analysis["information_needs"]=[{"subject":t["standard_name"],"term_id":t["term_id"],"category":t["category"]} for t in analysis["normalization"]["recognized_terms"]]
        return analysis
