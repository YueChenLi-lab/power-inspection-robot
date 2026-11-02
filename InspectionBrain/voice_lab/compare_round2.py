"""Compare new text pipelines against the actual export, without inventing references."""
from datetime import datetime
import json
from pathlib import Path
from inspection_brain.domain_v2.service import ElectricalBrainV2
from inspection_brain.service import SHANGHAI
from .metrics import evaluate


def main():
    root=Path(__file__).resolve().parents[1]
    source=root.parent/"voice-evaluation.json"
    data=json.loads(source.read_text())
    brain=ElectricalBrainV2();now=datetime.now(SHANGHAI)
    rows=[]
    for old in data["records"]:
        modes={}
        for enabled in (False,True):
            result=brain.ask(old["original_transcript"],now=now,apply_homophones=enabled)
            a=result["analysis"]
            enhanced=a["term_normalized_text"]
            after=brain.analyzer.analyze(enhanced,now=now)
            metrics=evaluate(old["reference_text"],old["original_transcript"],enhanced,brain,a,after,old["reference_confirmed"])
            modes["homophones_on" if enabled else "homophones_off"]={"analysis":a,"result":result["result"],"diagnostic_text_metrics":metrics,
                                                                     "official_score_eligible":False,"reason":"旧题目绑定未核实；仅保留既有确认标记做诊断，不修改历史统计"}
        rows.append({"record_id":old["record_id"],"input_source":old["input_source"],"raw_asr_text":old["raw_asr_text"],
                     "reference_confirmed":old["reference_confirmed"],"old_metrics":old["metrics"],
                     "old_intent":old["brain"]["analysis"]["intent"],"modes":modes})
    report={"source":str(source),"source_kind":"manual_development_samples","real_electrical_audio":0,
            "asr_improvement":None,"reference_confirmation_not_inferred":True,"lexicon_version":brain.normalizer.version,
            "lexicon_sha256":brain.normalizer.sha256,"records":rows}
    (root/"reports/round2_comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    lines=["# 第二轮增强前后对照", "", "9条实际manual记录用于规则开发，没有真实电力音频；不推断参考确认，不宣称ASR改善。只有原先已确认的一条计算诊断CER，错配题目绑定在重新确认前不进入正式新汇总。", "", "|条目|旧意图|第二轮意图（同音开）|自动应用的专业词纠正|待确认/数值风险|", "|---|---|---|---|---|"]
    for index,row in enumerate(rows,1):
        analysis=row["modes"]["homophones_on"]["analysis"]
        terms="；".join(c["original"]+"→"+c["replacement"] for c in analysis["normalization"]["changes"] if c["kind"]=="context_homophone") or "无"
        pending=sum(not c["applied"] for c in analysis["normalization"]["homophone_candidates"])
        kinds="、".join(i["type"] for i in analysis["intents"])
        lines.append(f"|{index}|{row['old_intent']}|{kinds}|{terms}|术语候选{pending}；数值槽位{len(analysis['numeric_entities'])}均未现场核验|")
    confirmed=next(row for row in rows if row["reference_confirmed"])
    lines += ["", "唯一确认样本的新口径诊断（不是ASR成绩，未据参考猜测小数或确认整理候选）："]
    for mode,value in confirmed["modes"].items():
        m=value["diagnostic_text_metrics"]
        before=m["before"]["strict_characters"];after=m["after"]["strict_characters"]
        state="改善" if after["cer"]<before["cer"] else "变差" if after["cer"]>before["cer"] else "无变化"
        lines.append(f"- {mode}：严格CER {before['edits']}/{before['reference_characters']}={before['cer']:.2%} → {after['edits']}/{after['reference_characters']}={after['cer']:.2%}，{state}。数值槽位召回率 {m['after']['numeric_slots']['accuracy']}；未修复错误数字。")
    lines += ["", "工程行为改善已由回归确认：状态查询不再unknown、否定导航不覆盖计划草案、禁止倒闸不产生肯定提案、综合问题不以局放定义冒充完整答案。词库自动纠正仅在开关启用和有上下文时发生；高风险项仍待确认。", "", "这批已见数据不能用于泛化结论。另有16条合成挑战，与9条真实规则开发样本分开；下一轮需单独录制未见电力音频及人工核实标准文本。"]
    (root/"reports/ROUND2_COMPARISON.md").write_text("\n".join(lines)+"\n")
    print('Saved real manual comparison; no ASR improvement claim.')


if __name__=="__main__":main()
