"""Deterministic text-only metrics with explicit numerators and denominators."""
import argparse
from datetime import datetime
import json
from pathlib import Path

from .routing import MockLegacyDispatcher, OfflineRouter
from .service import InspectionBrain


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def evaluate(fixture_path, brain=None):
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    brain = brain or InspectionBrain()
    now = datetime.fromisoformat(fixture["reference_time"])
    rows = []
    router = OfflineRouter(MockLegacyDispatcher(), brain, enabled=True)
    try:
        for case in fixture["cases"]:
            response = brain.ask(case["raw_text"], now=now, apply_homophones=case["apply_homophones"])
            analysis, result = response["analysis"], response["result"]
            normal = analysis["normalization"]
            raw_terms = {term.id for _, _, term, _ in brain.lexicon.matches(case["raw_text"])}
            actual_terms = {t["term_id"] for t in normal["recognized_terms"]}
            expected_terms = set(case["term_ids"])
            entities = [{k:e[k] for k in ("term_id", "device_number", "device_id")} for e in analysis["device_entities"]]
            source_checked = case["expected_document"] is not None
            citation_ok = source_checked and bool(result["citations"]) and any(c["document_id"] == case["expected_document"] for c in result["citations"]) and all(
                any(c["chunk_id"] == chunk.id and c["excerpt"] == chunk.text and c["content_sha256"] == chunk.content_sha256 for chunk in brain.repository.chunks)
                for c in result["citations"])
            motion_misfire = bool(response["executed_actions"] or response["hardware_commands_enabled"] or response["chassis_commands_enabled"] or
                                  normal["authorization_granted"] or (analysis["operation_proposal"] or {}).get("authorized"))
            routed = router.route(case["raw_text"]) if case["expected_route"] else None
            rows.append({"id": case["id"], "raw_text": case["raw_text"], "normalized_text": normal["normalized_text"],
                         "expected_normalized_text": case["normalized_text"],
                         "raw_term_ids": sorted(raw_terms), "normalized_term_ids": sorted(actual_terms),
                         "expected_term_ids": sorted(expected_terms), "intent": analysis["intent"],
                         "expected_intent": case["intent"], "entities": entities, "expected_entities": case["entities"],
                         "entity_types_correct": [e["term_id"] for e in entities] == [e["term_id"] for e in case["entities"]],
                         "device_numbers_correct": [e["device_number"] for e in entities] == [e["device_number"] for e in case["entities"]],
                         "device_ids_correct": [e["device_id"] for e in entities] == [e["device_id"] for e in case["entities"]],
                         "normalization_correct": normal["normalized_text"] == case["normalized_text"],
                         "raw_terms_correct": raw_terms == expected_terms, "terms_correct": actual_terms == expected_terms,
                         "entities_correct": entities == case["entities"], "intent_correct": analysis["intent"] == case["intent"],
                         "status_correct": case["status"] is None or case["status"] == result["status"],
                         "has_changes": bool(normal["changes"]),
                         "wrong_correction": bool(normal["changes"]) and normal["normalized_text"] != case["normalized_text"],
                         "motion_case": case["intent"] == "operation_proposal", "motion_misfire": motion_misfire,
                         "source_checked": source_checked, "citation_correct": citation_ok,
                         "abstention_checked": case["status"] == "undetermined",
                         "abstention_correct": result["status"] == "undetermined" and result.get("site_conclusion") is None,
                         "route_checked": routed is not None,
                         "route_correct": routed is None or (routed["route"] == case["expected_route"] and routed["raw_text"] == case["raw_text"]),
                         "operation_normalization_unchanged": not normal["operation_text_protected"] or normal["normalized_text"] == case["raw_text"]})
    finally:
        router.close()
    metrics = {
        "normalization_exact_accuracy": ratio(sum(r["normalization_correct"] for r in rows), len(rows)),
        "raw_term_set_accuracy": ratio(sum(r["raw_terms_correct"] for r in rows), len(rows)),
        "normalized_term_set_accuracy": ratio(sum(r["terms_correct"] for r in rows), len(rows)),
        "entity_and_number_exact_accuracy": ratio(sum(r["entities_correct"] for r in rows), len(rows)),
        "entity_type_accuracy_positive_cases": ratio(sum(r["entity_types_correct"] for r in rows if r["expected_entities"]), sum(bool(r["expected_entities"]) for r in rows)),
        "device_number_accuracy_numbered_cases": ratio(sum(r["device_numbers_correct"] for r in rows if any(e["device_number"] is not None for e in r["expected_entities"])), sum(any(e["device_number"] is not None for e in r["expected_entities"]) for r in rows)),
        "device_id_accuracy_explicit_id_cases": ratio(sum(r["device_ids_correct"] for r in rows if any(e["device_id"] for e in r["expected_entities"])), sum(any(e["device_id"] for e in r["expected_entities"]) for r in rows)),
        "intent_accuracy": ratio(sum(r["intent_correct"] for r in rows), len(rows)),
        "wrong_correction_rate_per_input": ratio(sum(r["wrong_correction"] for r in rows), len(rows)),
        "wrong_correction_rate_among_changed": ratio(sum(r["wrong_correction"] for r in rows), sum(r["has_changes"] for r in rows)),
        "motion_misfire_rate": ratio(sum(r["motion_misfire"] for r in rows if r["motion_case"]), sum(r["motion_case"] for r in rows)),
        "citation_correctness": ratio(sum(r["citation_correct"] for r in rows), sum(r["source_checked"] for r in rows)),
        "evidence_absent_abstention_accuracy": ratio(sum(r["abstention_correct"] for r in rows if r["abstention_checked"]), sum(r["abstention_checked"] for r in rows)),
        "mock_parallel_route_accuracy": ratio(sum(r["route_correct"] for r in rows if r["route_checked"]), sum(r["route_checked"] for r in rows)),
    }
    failed = [r["id"] for r in rows if not all(r[k] for k in (
        "normalization_correct", "terms_correct", "entities_correct", "intent_correct", "status_correct", "route_correct", "operation_normalization_unchanged"))
        or r["motion_misfire"] or (r["source_checked"] and not r["citation_correct"]) or
        (r["abstention_checked"] and not r["abstention_correct"])]
    return {"dataset_kind": fixture["dataset_kind"], "audio_samples": fixture["audio_samples"],
            "reference_time": fixture["reference_time"], "asr_wer": None, "asr_cer": None,
            "asr_quality_claim": "无真实语音样本，未评价ASR WER/CER改善", "metrics": metrics,
            "limitations": ["人工构造的小型回归集，非真实语音或现场分布", "术语指标为每句完整术语集合精确匹配",
                           "运动指标检查离线输出/授权标记与原文保护，不代表真机安全认证", "路由测试使用Mock旧分发器，不声称生产Gateway回归通过"],
            "failed_cases": failed, "comparisons": rows}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="tests/golden_cases.json")
    parser.add_argument("--output", default="reports/evaluation.json")
    args = parser.parse_args(argv)
    report = evaluate(args.fixtures)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"metrics": report["metrics"], "failed_cases": report["failed_cases"]}, ensure_ascii=False, indent=2))
    return 1 if report["failed_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
