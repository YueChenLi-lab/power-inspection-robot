from datetime import datetime
from ..service import InspectionBrain, DEFAULT_DATA, SHANGHAI
from ..terminology import Lexicon
from ..electrical_knowledge import DocumentRepository, KnowledgeQA
from ..electrical_knowledge.repository import undetermined
from .normalization import DomainNormalizer
from .semantics import MultiIntentAnalyzer
from .spoken import SpokenTextCleaner
from .knowledge import answer_with_coverage


class ElectricalBrainV2(InspectionBrain):
    def __init__(self,data_dir=DEFAULT_DATA,**kwargs):
        super().__init__(data_dir,**kwargs)
        path=data_dir/"electrical_terms_v2.json"
        self.lexicon=Lexicon(path)
        self.normalizer=DomainNormalizer(self.lexicon,path)
        self.analyzer=MultiIntentAnalyzer(self.normalizer)
        self.repository=DocumentRepository(data_dir/"knowledge",self.lexicon)
        self.qa=KnowledgeQA(kwargs.get("retriever") or self.repository,kwargs.get("provider"))
        self.cleaner=SpokenTextCleaner()

    def ask(self,text,*,now=None,apply_homophones=False,accepted_candidate_ids=(),rejected_candidate_ids=()):
        result=super().ask(text,now=now or datetime.now(SHANGHAI),apply_homophones=apply_homophones)
        analysis=result["analysis"]
        normal=analysis["normalization"]
        cleaned=self.cleaner.clean(normal["normalized_text"],normal,accepted=accepted_candidate_ids,rejected=rejected_candidate_ids)
        analysis.update(raw_transcript=text,term_normalized_text=normal["normalized_text"],
                        cleanup_source_text=cleaned["cleanup_source_text"],
                        cleaned_display_text=cleaned["cleaned_display_text"],
                        correction_candidates=cleaned["correction_candidates"],
                        correction_trace=normal["changes"]+cleaned["correction_trace"],
                        lexicon_version=self.normalizer.version,lexicon_sha256=self.normalizer.sha256)
        kinds=[row["type"] for row in analysis["intents"]]
        if analysis["intent"] in ("equipment_knowledge","anomaly_procedure_explanation"):
            result["result"]=answer_with_coverage(self.qa,analysis)
        if analysis["intent"] in ("equipment_status_query","temperature_comparison","reinspection_recommendation","report_draft","thermometry_history","temperature_anomaly_query","temperature_measurement_query"):
            result["result"]=undetermined("需要真实设备身份、有效测量/历史记录及适用规程；当前只能列出信息需求，不能判断异常或生成正式结论。",analysis["required_data_sources"])
        elif analysis["intent"]=="prohibited_operation":
            result["result"]={**undetermined("已保留禁止执行约束，没有肯定操作请求；本模块无硬件执行能力。"),"status":"prohibition_preserved"}
        if len(kinds)>1 and "operation_proposal" not in kinds and "inspection_plan_draft" not in kinds:
            result["result"]=undetermined("已拆解多个业务需求；真实记录与规程未接入，各项分析/建议均需证据和人工复核。",analysis["required_data_sources"])
            result["result"]["subresults"]=[{"intent":row["type"],"status":"needs_evidence","required_data_sources":row["required_data_sources"]} for row in analysis["intents"]]
            if any(word in text for word in ("并说明","什么影响","原理")):
                result["result"]["knowledge_coverage"]=answer_with_coverage(self.qa,analysis)
        result["domain_version"]="v2"
        if "mission_draft" in result["result"]:
            result["result"]["mission_draft"].update(constraints=analysis["constraints"],numeric_verification=analysis["numeric_entities"])
        return result
