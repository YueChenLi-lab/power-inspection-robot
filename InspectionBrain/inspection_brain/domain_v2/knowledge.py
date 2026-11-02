"""Subquestion coverage guard around exact-source extraction, never invents evidence."""
import re
from ..electrical_knowledge.repository import undetermined


def answer_with_coverage(qa,analysis):
    query=analysis["term_normalized_text"]
    # A complex operational equipment question is not answered by one defect definition.
    subjects={t["term_id"] for t in analysis["normalization"]["recognized_terms"] if t["category"] in ("equipment","defect","metric")}
    compound=bool(re.search(r"同时|以及|并说明|特别关注|针对不同|重点检查",query)) or len(subjects)>1 and bool(re.search(r"影响|异常|状态|检查|关注",query))
    if not compound:return qa.answer(analysis)
    needs=[]
    for term in analysis["normalization"]["recognized_terms"]:
        key=term["term_id"]
        if key not in [n["term_id"] for n in needs]:
            needs.append({"term_id":key,"subject":term["standard_name"],"category":term["category"]})
    sections=[]
    citations=[]
    for need in needs:
        local=dict(analysis)
        local["intent"]="anomaly_procedure_explanation" if need["category"]=="defect" else "equipment_knowledge"
        local["normalization"]={**analysis["normalization"],"raw_text":need["subject"]+"是什么？",
                                "normalized_text":need["subject"]+"是什么？",
                                "recognized_terms":[t for t in analysis["normalization"]["recognized_terms"] if t["term_id"]==need["term_id"]]}
        # Search still enforces term/device requirements; label conceptual evidence explicitly.
        result=qa.answer(local)
        if result["citations"]:
            citations.extend(result["citations"])
        sections.append({**need,"status":result["status"],"answer":result["answer"],"citations":result["citations"],
                         "coverage":"concept_only_not_equipment_state" if result["citations"] else "missing"})
    missing=[n["subject"]+"的适用说明书/巡检规程" for n in sections if not n["citations"]]
    missing+= ["原问题的设备状态/综合检查/影响分析需要专门资料；概念定义不能覆盖整体"]
    result=undetermined("原问题包含多个信息需求，当前资料不足以完整回答。下列分项仅展示可追溯概念证据，并列出缺失资料；不能把局放定义当作开关柜综合检查答案。",missing)
    result.update(sections=sections,citations=list({c["chunk_id"]:c for c in citations}.values()),is_example=bool(citations),coverage_status="partial_or_missing")
    return result
