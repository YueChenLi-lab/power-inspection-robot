"""Separate semantic annotations and development-only, SHA-deduplicated metrics."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .schema import schema_errors

DIMENSIONS = ("intents", "equipment_relations", "temporal_constraints", "numeric_negation_relations",
              "negations", "self_corrections", "conditions", "task_dependencies")


def signature(semantic):
    spans = {s["span_id"]: s["quote"] for s in semantic["source_spans"]}
    entities = {e["entity_id"]: e for e in semantic["equipment_entities"]+semantic["metric_entities"]}
    intents = {i["intent_id"]: i["type"] for i in semantic["intents"]}
    def descriptor(ident):
        e = entities[ident]
        return (e["equipment_category"], e["device_number"], e["status"]) if "device_number" in e else (e["kind"], e["normalized_value"], e["normalized_unit"], e["status"])
    return {
        "intents": sorted([[i["type"], i["request_kind"]] for i in semantic["intents"]]),
        "equipment_relations": [[e["equipment_category"], e["device_number"], e["status"],
                                 list(descriptor(e["part_of"])) if e["part_of"] else None] for e in semantic["equipment_entities"]],
        "temporal_constraints": [[t["role"], t["expression"], t["start"], t["end"], t["resolved"]] for t in semantic["temporal_constraints"]],
        "numeric_negation_relations": [[m["kind"], m["normalized_value"], m["normalized_unit"], m["status"]] for m in semantic["metric_entities"] if m["kind"] != "indicator"],
        "negations": [[n["kind"], [spans[s] for s in n["scope_span_ids"]]] for n in semantic["negations"]],
        "self_corrections": [[r["kind"], [list(descriptor(s)) for s in r["rejected_ids"]], [list(descriptor(s)) for s in r["accepted_ids"]]] for r in semantic["self_corrections"]],
        "conditions": [[c["expression"], sorted(intents[i] for i in c["scope_ids"])] for c in semantic["conditions"]],
        "task_dependencies": [[intents[d["before_intent_id"]], intents[d["after_intent_id"]], d["kind"]] for d in semantic["task_dependencies"]],
    }


def v2_signature(result):
    """Report absent relationship semantics as 'unresolved', never as correct active."""
    a = result["analysis"]
    text = a["normalization"]["raw_text"]
    revision = bool(re.search(r"不是|不对|更正为|改为", text))
    draft_types = {"inspection_plan_draft", "reinspection_recommendation", "report_draft", "operation_proposal"}
    periods = []
    if a.get("comparison_constraints"):
        for role, key in (("target", "target"), ("comparison_baseline", "baseline")):
            p = a["comparison_constraints"][key]
            periods.append([role, p.get("expression"), p.get("start"), p.get("end"), p.get("resolved", False)])
    elif a["time_range"].get("expression"):
        p = a["time_range"]
        periods.append(["target", p["expression"], p.get("start"), p.get("end"), p.get("resolved", False)])
    # Adapt existing v2 scope metadata fairly; do not count its different JSON
    # representation as missing comprehension. No new correction relationships.
    scoped_conditions = a.get("conditional_clauses", [])
    intent_kinds = {i["type"]: "conditional_task" if i["type"] in draft_types and scoped_conditions else
                    "task_draft" if i["type"] in draft_types else "negated_request" if i["type"] == "prohibited_operation" else
                    "clarification" if i["type"] == "unknown" else "query" for i in a["intents"]}
    prohibitions = []
    for scope in a.get("constraints", []):
        if scope["polarity"] != "prohibited":
            continue
        start, end = scope["source_span"]
        whole_clause = next((m.group() for m in re.finditer(r"[^，。；！？,;!?]+", text) if m.start() <= start < m.end()), scope["scope_text"])
        item = ["prohibition", [whole_clause]]
        if item not in prohibitions:prohibitions.append(item)
    return {
        "intents": sorted([[i["type"], intent_kinds[i["type"]]] for i in a["intents"]]),
        "equipment_relations": [[e["equipment_category"], e["device_number"], "unresolved" if revision else "active", None] for e in a["device_entities"]],
        "temporal_constraints": periods,
        "numeric_negation_relations": [[m["kind"], m["normalized_value"], m["normalized_unit"], "unresolved" if revision else "active"] for m in a["numeric_entities"]],
        "negations": prohibitions, "self_corrections": [],
        "conditions": [[c, sorted(i["type"] for i in a["intents"] if intent_kinds[i["type"]] == "conditional_task")] for c in scoped_conditions],
        "task_dependencies": [],
    }


def score_semantics(prediction, annotation):
    # Unlike an ASR reference, this is a separately authored semantic expectation.
    required = {"annotation_version", "annotation_source", "confirmed", "annotator", "original_sha256", "expected"}
    if not isinstance(annotation, dict) or not required <= annotation.keys() or annotation.get("confirmed") is not True or not annotation.get("annotator"):
        return {"eligible": False, "reason": "未确认独立人工语义标注", "dimensions": None}
    if annotation["annotation_source"] not in ("human_audio", "human_transcript", "handwritten_synthetic"):
        return {"eligible": False, "reason": "不允许模型/ASR输出作为语义金标准", "dimensions": None}
    expected = annotation["expected"]
    if not isinstance(expected, dict) or not expected or not set(expected) <= set(DIMENSIONS):
        return {"eligible": False, "reason": "语义标注维度无效", "dimensions": None}
    dimensions = {}
    for field, gold in expected.items():
        if not isinstance(gold, list):
            return {"eligible": False, "reason": "语义标注须为结构化数组", "dimensions": None}
        def count(rows):
            return Counter(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
        pred, actual = count(prediction[field]), count(gold)
        matched = sum((pred & actual).values())
        dimensions[field] = {"exact_match": pred == actual, "correct": matched, "predicted": sum(pred.values()),
                             "expected": sum(actual.values()), "precision": matched/sum(pred.values()) if pred else None,
                             "recall": matched/sum(actual.values()) if actual else None}
    return {"eligible": True, "reason": None, "dimensions": dimensions, "all_annotated_dimensions_exact": all(m["exact_match"] for m in dimensions.values())}


def evaluate_result(result, annotation):
    original_hash = hashlib.sha256(result["original_request"].encode()).hexdigest()
    if annotation and annotation.get("confirmed") is True and annotation.get("original_sha256") != original_hash:
        return {"eligible": False, "reason": "语义标注不属于本次原文；转写版本变化后须重新核实", "v2": None, "v3": None}
    selected = result.get("v3") if (result.get("validation") or {}).get("valid") else result.get("fallback")
    if not selected or "semantic" not in selected:
        return {"eligible": False, "reason": "没有通过校验的v3/回退语义", "v2": None, "v3": None}
    v3 = score_semantics(signature(selected["semantic"]), annotation)
    return {"eligible": v3["eligible"], "reason": v3["reason"],
            "v2": score_semantics(v2_signature(result["v2"]), annotation), "v3": v3,
            "asr_cer_improvement_claimed": False, "prediction_origin": selected["structured_task_draft"]["reasoning_source"]}


def development_manifest(storage):
    storage = Path(storage)
    records = [json.loads(p.read_text()) for p in sorted((storage/"records").glob("*.json"))]
    by_hash = {}
    for path in sorted((storage/"audio").glob("*.json")):
        a = json.loads(path.read_text()); asr = a.get("asr", {})
        wav = path.with_suffix(".wav")
        if not wav.is_file() or not a.get("sha256"):
            continue
        actual_hash = hashlib.sha256(wav.read_bytes()).hexdigest()
        if actual_hash != a["sha256"]:
            raise ValueError("历史音频SHA256不一致：" + path.name)
        row = by_hash.setdefault(actual_hash, {"sample_id": "audio-"+actual_hash, "audio_sha256": actual_hash,
            "audio_ids": [], "transcript_variants": [], "historical_record_ids": [], "historical_lexicon_versions": [],
            "dataset_role": "development_regression_NOT_blind_test",
            "semantic_annotation": {"annotation_version": "semantic-gold-v1", "annotation_source": "human_audio",
                                    "confirmed": False, "annotator": "", "original_sha256": None, "expected": None}})
        row["audio_ids"].append(a["audio_id"])
        if asr.get("status") == "ok" and asr.get("text"):
            variant = {"original_request": asr["text"], "original_sha256": hashlib.sha256(asr["text"].encode()).hexdigest(),
                       "engine": asr.get("engine"), "model_id": asr.get("model_id"), "model_version": asr.get("model_version")}
            if variant not in row["transcript_variants"]:
                row["transcript_variants"].append(variant)
    for r in records:
        row = by_hash.get((r.get("audio") or {}).get("sha256"))
        if row:
            row["historical_record_ids"].append(r["record_id"])
            version = (r.get("brain", {}).get("analysis", {})).get("lexicon_version")
            if version and version not in row["historical_lexicon_versions"]:
                row["historical_lexicon_versions"].append(version)
    samples = list(by_hash.values())
    return {"schema_version": "semantic-development-manifest-v1", "historical_records_read": len(records),
            "unique_audio_sha256_count": len(samples), "unique_audio_with_transcript_count": sum(bool(s["transcript_variants"]) for s in samples),
            "confirmed_semantic_gold_count": 0, "samples": samples,
            "notes": ["已有数据仅作开发回归；需独立人工语义标注，未见音频盲测另建", "不复制音频，不将ASR输出自动作为标准答案，不计算虚构语义或ASR改善率"]}


def runtime_summary(records):
    hashes = {r["provenance"]["audio_sha256"] for r in records if r["provenance"].get("audio_sha256") and r["input_source"] == "asr"}
    candidates = [r["result"] for r in records if r["result"].get("model_candidate") is not None]
    real = [r for r in candidates if r["provider"]["is_real_llm"]]
    attempts = [r["result"] for r in records if r["result"]["fallback_used"]]
    return {"analysis_run_count": len(records), "unique_asr_audio_sha256_count": len(hashes),
            "manual_run_count": sum(r["input_source"] != "asr" for r in records),
            "candidate_count": len(candidates), "schema_valid_count": sum(not schema_errors(r["model_candidate"]) for r in candidates),
            "real_llm_candidate_count": len(real), "mock_candidate_count": sum(r["provider"]["provider"] == "mock" for r in candidates),
            "validator_rejection_count": sum(not r["validation"]["valid"] for r in candidates),
            "fallback_attempt_count": len(attempts), "fallback_success_count": sum(r["fallback_success"] for r in attempts),
            "real_llm_mean_inference_seconds": sum(r["llm_inference_seconds"] for r in real)/len(real) if real else None,
            "semantic_accuracy": None, "semantic_accuracy_reason": "运行记录未绑定已确认的独立人工语义标注；不会以转写充当金标准"}


def comparison_summary(rows):
    """Development scores by labelled dataset; unknown gold never gets a denominator."""
    groups = {}
    for row in rows:
        if row.get("skipped"):
            continue
        result = row["result"]
        key = (row["dataset_role"], result["provider"]["provider"], result["provider"].get("model_version"),
               result["configuration_sha256"], result["lexicon_sha256"])
        # Multiple transcriptions/runs of one audio do not add independent samples.
        sample_key = row.get("audio_sha256") or row["sample_id"]
        groups.setdefault(key, {})[sample_key] = row
    summary = []
    for key, samples in groups.items():
        rows_in_group = list(samples.values())
        confirmed = [r for r in rows_in_group if r["metrics"]["eligible"]]
        candidates = [r["result"] for r in rows_in_group if r["result"]["model_candidate"] is not None]
        actual = [r for r in candidates if r["provider"]["is_real_llm"]]
        scored = {}
        for version in ("v2", "v3"):
            scored[version] = {}
            for field in DIMENSIONS:
                values = [r["metrics"][version]["dimensions"][field] for r in confirmed
                          if field in (r["metrics"][version].get("dimensions") or {})]
                if not values:
                    scored[version][field] = None
                    continue
                correct, predicted, expected = (sum(m[k] for m in values) for k in ("correct", "predicted", "expected"))
                scored[version][field] = {"annotated_samples":len(values), "exact_samples":sum(m["exact_match"] for m in values),
                    "exact_accuracy":sum(m["exact_match"] for m in values)/len(values),
                    "precision":correct/predicted if predicted else None, "recall":correct/expected if expected else None}
        summary.append({"dataset_role":key[0], "provider":key[1], "model_version":key[2],
                        "configuration_sha256":key[3], "lexicon_sha256":key[4],
                        "unique_development_samples":len(samples), "confirmed_semantic_samples":len(confirmed),
                        "schema_valid_candidates":sum(not schema_errors(r["model_candidate"]) for r in candidates),
                        "candidate_count":len(candidates), "real_llm_candidate_count":len(actual),
                        "real_llm_mean_seconds":sum(r["llm_inference_seconds"] for r in actual)/len(actual) if actual else None,
                        "fallback_attempts":sum(r["result"]["fallback_used"] for r in rows_in_group),
                        "fallback_successes":sum(r["result"]["fallback_success"] for r in rows_in_group), "dimensions":scored,
                        "asr_cer_improvement_claimed":False, "generalization_claimed":False})
    return summary
