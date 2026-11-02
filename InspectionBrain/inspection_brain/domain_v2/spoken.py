"""Display-only cleanup with explicit confirmation for ambiguous restarts."""
import re
from .normalization import candidate_id
from .numbers import parse_number


class SpokenTextCleaner:
    def clean(self,text,normalization,*,accepted=(),rejected=()):
        protected=normalization["operation_text_protected"]
        projection=[];offset=0
        for change in normalization["changes"]:
            if change["original"]=="主变" and change["kind"]=="exact_alias":
                a=change["span"][0]+offset
                projection.append({"span":[a,a+len(change["replacement"])],"replacement":"主变","original":change["replacement"],
                                   "kind":"display_alias_projection","stage":"term_normalized_text","reason":"可读文本保留原口语别名；专业标准名称仍在术语规范化字段","confidence_level":"deterministic_alias"})
            offset+=len(change["replacement"])-len(change["original"])
        for row in reversed(projection):
            a,b=row["span"];text=text[:a]+row["replacement"]+text[b:]
        cleanup_source=text
        candidates=[];automatic=[]
        def add(match,replacement,kind,automatic_allowed=False):
            span=[match.start(),match.end()]
            candidates.append({"id":candidate_id(kind,span,replacement),"surface":match.group(),"replacement":replacement,
                               "source_span":span,"span":span,"kind":kind,"stage":"display_alias_projection_text",
                               "reason":"可能的口语重复/重启；缺音频置信度，需人工确认" if not automatic_allowed else "确定的只读语法/填充整理",
                               "confidence_level":"candidate_only" if not automatic_allowed else "deterministic_display",
                               "automatic_allowed":automatic_allowed,"display_confirmation_allowed":not protected})
        for m in re.finditer(r"([0-9零〇一二三四五六七八九十]+号)的(?=主变|变压器|开关柜)",text):add(m,m.group(1),"redundant_particle",True)
        for m in re.finditer(r"(?P<n>[零一二三四五六七八九十\d]+)号柜开关(?P<again>[零一二三四五六七八九十\d]+)号开关柜",text):
            if parse_number(m.group("n"))==parse_number(m.group("again")):add(m,m.group("n")+"号开关柜","sentence_restart")
        for m in re.finditer(r"变压器管套管变压器套管",text):add(m,"变压器套管","sentence_restart")
        for m in re.finditer(r"(?P<word>变压器套管|变压器|开关柜|油温|巡检记录|绕组温度)(?:\s*[，,]\s*)?(?P=word)",text):add(m,m.group("word"),"adjacent_repeat")
        for m in re.finditer(r"(?:^|(?<=[，。；,;]))(?:嗯+|呃+)[，,\s]*",text):add(m,"","filler",True)
        for m in re.finditer(r"(?P<first>主变压器|变压器|开关柜)[，,\s]*(?:不对|说错了)[，,\s]*(?:是|应该是)(?P<second>主变压器|变压器|开关柜)",text):add(m,m.group("second"),"explicit_self_correction")
        # Unapplied context-confirmable term candidates can be confirmed for display only.
        for original in normalization["homophone_candidates"]:
            if original["applied"] or not original["display_confirmation_allowed"]:continue
            surface=original["surface"]
            positions=list(re.finditer(re.escape(surface),text,re.IGNORECASE))
            if len(positions)==1:
                row=dict(original); row.update(kind="confirmed_term_display",stage="display_alias_projection_text",
                                             span=[positions[0].start(),positions[0].end()],source_span=[positions[0].start(),positions[0].end()],automatic_allowed=False)
                candidates.append(row)
        edits=[]
        for row in candidates:
            row["decision"]="rejected" if row["id"] in rejected else "confirmed_display_only" if row["id"] in accepted else "pending"
            should_apply=not protected and row["id"] not in rejected and (row["automatic_allowed"] or row["id"] in accepted)
            a,b=row["span"]
            row["applied"]=bool(should_apply and not any(a<prev["span"][1] and b>prev["span"][0] for prev in edits))
            if row["applied"]:edits.append(row)
        cleaned=text
        for row in sorted(edits,key=lambda r:r["span"][0],reverse=True):
            a,b=row["span"];cleaned=cleaned[:a]+row["replacement"]+cleaned[b:]
        trace=projection+[dict(row) for row in edits]
        if not protected:
            # Only insert punctuation; preserve every semantic word, negation and value.
            punctuated=re.sub(r"(?<=[^，。；\s])(同时|如果|最终|并说明)",r"，\1",cleaned)
            if punctuated!=cleaned:trace.append({"kind":"clause_separator","original":cleaned,"replacement":punctuated,"source_span":[0,len(cleaned)],"stage":"cleaned_display_text","reason":"仅插入标点","confidence_level":"display_only"})
            cleaned=punctuated
        return {"cleanup_source_text":cleanup_source,"cleaned_display_text":cleaned,"correction_candidates":candidates,"correction_trace":trace,
                "display_only":True,"authorization_granted":False}
