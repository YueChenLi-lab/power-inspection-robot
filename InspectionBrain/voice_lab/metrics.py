"""Deterministic text metrics; manual paste never counts as an ASR measurement."""
from collections import Counter
import hashlib
import re
from datetime import datetime
import unicodedata
from inspection_brain.service import SHANGHAI
from inspection_brain.domain_v2.numbers import extract_numeric_slots, equivalent_value


def scoring_text(text):
    return "".join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith("P"))


def character_error(reference, hypothesis, *, strict=False):
    if not strict:
        reference, hypothesis = scoring_text(reference), scoring_text(hypothesis)
    previous = list(range(len(hypothesis)+1))
    for i, expected in enumerate(reference, 1):
        row = [i]
        for j, actual in enumerate(hypothesis, 1):
            row.append(min(row[-1]+1, previous[j]+1, previous[j-1]+(expected != actual)))
        previous = row
    return {"edits": previous[-1], "reference_characters": len(reference),
            "cer": previous[-1]/len(reference) if reference else None}


def match_counts(expected, actual):
    correct = sum((expected & actual).values())
    total, predicted = sum(expected.values()), sum(actual.values())
    return {"correct": correct, "expected": total, "predicted": predicted,
            "extra": sum((actual-expected).values()), "missing": sum((expected-actual).values()),
            "accuracy": correct/total if total else None,
            "precision": correct/predicted if predicted else None}


def numbered_entities(analysis):
    return Counter((e["term_id"], e.get("device_number"), e.get("device_id"))
                   for e in analysis["device_entities"] if e.get("device_number") is not None or e.get("device_id"))


def evaluate(reference, original, enhanced, brain, raw_analysis, enhanced_analysis, confirmed):
    if not confirmed or not scoring_text(reference):
        return {"eligible": False, "reason": "未确认有效人工标准文本", "before": None, "after": None}
    ref_analysis = brain.analyzer.analyze(reference, now=datetime.now(SHANGHAI))
    ref_terms = Counter(t.id for _, _, t, _ in brain.lexicon.matches(reference))
    expected_devices = numbered_entities(ref_analysis)
    results = []
    def slots(text):
        return Counter(value for slot in extract_numeric_slots(text) if slot["kind"] in ("measurement","phase")
                       and (value:=equivalent_value(slot)) is not None)
    expected_slots=slots(reference)
    for text, analysis in ((original, raw_analysis), (enhanced, enhanced_analysis)):
        actual_terms = Counter(t.id for _, _, t, _ in brain.lexicon.matches(text))
        terms=match_counts(ref_terms, actual_terms)
        terms["recall"]=terms["accuracy"]
        results.append({"characters": character_error(reference, text),
                        "strict_characters":character_error(reference,text,strict=True),
                        "terms": terms,"alias_equivalent_terms":dict(terms),
                        "numeric_slots":match_counts(expected_slots,slots(text)),
                        "device_numbers": match_counts(expected_devices, numbered_entities(analysis))})
    return {"eligible": True, "before": results[0], "after": results[1],
            "metric_version":"voice-metrics-v2.1",
            "policy": "strict_characters逐字计算含标点/空白；characters保留旧兼容口径。术语别名按ID等价；数值仅等价单位换算，不猜小数。"}


def audio_hash(row):
    value = (row.get('audio') or {}).get('sha256')
    return value if isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) else None


def confirmed_record(row):
    return (row.get('reference_confirmed') is True and bool(scoring_text(row.get('reference_text','')))
            and row['metrics']['eligible'] and row.get('reference_binding',{}).get('status') in ('question_confirmed','custom_confirmed'))


def sample_statistics(records, audios=()):
    hashes = {h for row in records if (h:=audio_hash(row))}
    hashes.update(h for audio in audios if (h:=audio_hash({'audio':audio})))
    real = [r for r in records if r['input_source']=='asr' and (r.get('audio') or {}).get('asr',{}).get('status')=='ok' and r.get('raw_asr_text')]
    confirmed = {h for row in real if confirmed_record(row) and (h:=audio_hash(row))}
    return {'record_count':len(records),'unique_audio_sha256_count':len(hashes),
            'confirmed_reference_unique_audio_count':len(confirmed),
            'independent_test_sample_count':len({h for row in real if (h:=audio_hash(row))}),
            'analysis_run_count':len({r.get('analysis_run_id') or r['record_id'] for r in records}),
            'manual_record_count':sum(r['input_source']=='manual' for r in records),
            'policy':'独立语音样本按原 WAV SHA256 去重；录音ID、重新识别、规则版本与评分修订不增加独立样本。manual不计入真实ASR。分析次数按analysis_run_id，旧记录按record_id。'}


def unique_scored_rows(rows):
    latest = {}
    for row in sorted(rows,key=lambda r:(r['created_at'],r['record_id'])):
        if row['input_source']=='asr':
            key=audio_hash(row)
            if key is None:continue # Missing provenance cannot prove an independent audio sample.
        else:
            key=hashlib.sha256((row['input_source']+':'+row['original_transcript']).encode()).hexdigest()
        latest[key]=row
    return list(latest.values())


def aggregate(records):
    groups = {}
    for source in ("asr", "manual", "windows_external", "sensevoice_asr"):
        runs = [row for row in records if (row["input_source"] == source or source=="sensevoice_asr" and row["input_source"]=="asr" and (row.get("audio") or {}).get("asr",{}).get("engine")=="sensevoice") and confirmed_record(row)]
        rows = unique_scored_rows(runs)
        scores = {}
        for stage in ("before", "after"):
            metric="strict_characters"
            chars = sum(row["metrics"][stage].get(metric,row["metrics"][stage]["characters"])["reference_characters"] for row in rows)
            edits = sum(row["metrics"][stage].get(metric,row["metrics"][stage]["characters"])["edits"] for row in rows)
            summary = {"reference_characters": chars, "edits": edits, "cer": edits/chars if chars else None}
            for name in ("terms", "device_numbers", "numeric_slots"):
                counts = {key: sum(row["metrics"][stage].get(name,{}).get(key,0) for row in rows)
                          for key in ("correct", "expected", "predicted", "extra", "missing")}
                counts["accuracy"] = counts["correct"]/counts["expected"] if counts["expected"] else None
                counts["precision"] = counts["correct"]/counts["predicted"] if counts["predicted"] else None
                summary[name] = counts
            scores[stage] = summary
        changes=Counter("improved" if row["metrics"]["after"]["strict_characters"]["cer"]<row["metrics"]["before"]["strict_characters"]["cer"] else "worse" if row["metrics"]["after"]["strict_characters"]["cer"]>row["metrics"]["before"]["strict_characters"]["cer"] else "unchanged" for row in rows)
        groups[source] = {"confirmed_runs": len(runs), "scored_unique_samples":len(rows),
                          "selected_record_ids":[r['record_id'] for r in rows],
                          "selection_policy":"每个音频SHA256只使用最新已确认评分；版本/配置对照见分组。manual按来源+原始文本去重，不代表音频样本。",
                          "change_counts":dict(changes),**scores}
    groups["legacy_records_excluded"]=sum("reference_binding" not in r for r in records)
    return groups


def grouped_comparison(records):
    buckets={}
    for row in records:
        asr=(row.get("audio") or {}).get("asr",{})
        if row["input_source"]=="windows_external":asr={"model_id":row.get("external_asr_engine") or "self_reported_unknown","model_version":row.get("external_asr_version") or "self_reported_unknown"}
        if row["input_source"]=="manual":asr={"model_id":"manual_text","model_version":"not_asr"}
        key=(row["input_source"],asr.get("model_id","none"),asr.get("model_version","unknown"),
             row.get("brain",{}).get("analysis",{}).get("lexicon_version","legacy-v1"),row.get("apply_homophones",False),
             row.get('brain',{}).get('analysis',{}).get('lexicon_sha256'),row.get('provenance',{}).get('analysis_config_hash'),
             row.get('brain',{}).get('analysis',{}).get('semantic_version'))
        buckets.setdefault(key,[]).append(row)
    return [{"source":key[0],"model_id":key[1],"model_version":key[2],"lexicon_version":key[3],"apply_homophones":key[4],
             "lexicon_sha256":key[5],"analysis_config_hash":key[6],"semantic_version":key[7],
             "statistics":sample_statistics(rows),"aggregate":aggregate(rows)} for key,rows in buckets.items()]
