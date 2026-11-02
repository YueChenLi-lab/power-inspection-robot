"""Independent candidate verification against deterministic ORIGINAL evidence."""
from .schema import schema_errors
from .evidence import INTENT_CUES, NEGATIVE, CONDITIONAL, DRAFT_TYPES
import re


class SemanticValidator:
    def validate(self, candidate, evidence):
        errors = schema_errors(candidate)
        if errors:
            return {"valid": False, "errors": errors, "warnings": [], "requires_human_confirmation": True}
        text = evidence["original_request"]
        if candidate["original_request"] != text:
            errors.append("original_request_changed")
        spans = {s["span_id"]: s for s in candidate["source_spans"]}
        if len(spans) != len(candidate["source_spans"]):
            errors.append("duplicate_span_id")
        for s in spans.values():
            if not 0 <= s["start"] < s["end"] <= len(text) or text[s["start"]:s["end"]] != s["quote"]:
                errors.append("invalid_original_source_span:" + s["span_id"])
        # Anchor IDs in the provided original evidence; arbitrary re-numbering could
        # silently invert a correction relationship or target.
        expected_spans = {s["span_id"]: s for s in evidence["source_spans"]}
        for sid, original in expected_spans.items():
            if spans.get(sid) != original:
                errors.append("evidence_span_missing_or_changed:" + sid)
        def references(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    if k in ("source_span_ids", "scope_span_ids"):
                        for sid in v:
                            if sid not in spans:
                                errors.append("unknown_span_reference:" + sid)
                    else:
                        references(v)
            elif isinstance(value, list):
                for v in value:
                    references(v)
        references(candidate)
        # Do not proceed to relational checks if spans are invalid/missing.
        if errors:
            return {"valid": False, "errors": sorted(set(errors)), "warnings": [], "requires_human_confirmation": True}
        for field in ("equipment_entities", "metric_entities", "temporal_constraints", "self_corrections", "negations", "conditions"):
            # These are verifiable facts/relations, not free-form model assertions.
            expected = evidence[field]
            actual = candidate[field]
            if actual != expected:
                errors.append("original_evidence_relation_changed:" + field)
        ids = {}
        for field, id_field in (("equipment_entities", "entity_id"), ("metric_entities", "entity_id"),
                                ("temporal_constraints", "constraint_id"), ("intents", "intent_id"),
                                ("conditions", "condition_id")):
            for item in candidate[field]:
                ident = item[id_field]
                if ident in ids:
                    errors.append("duplicate_entity_or_intent_id:" + ident)
                ids[ident] = item
        active_devices = {e["entity_id"] for e in candidate["equipment_entities"] if e["status"] == "active"}
        active_metrics = {e["entity_id"] for e in candidate["metric_entities"] if e["status"] == "active"}
        times = {t["constraint_id"] for t in candidate["temporal_constraints"]}
        intent_ids = {i["intent_id"] for i in candidate["intents"]}
        for i in candidate["intents"]:
            if not set(i["entity_ids"]) <= active_devices or not set(i["metric_ids"]) <= active_metrics or not set(i["time_ids"]) <= times:
                errors.append("invalid_or_negated_intent_target:" + i["intent_id"])
            if not i["source_span_ids"]:
                errors.append("intent_without_original_evidence:" + i["intent_id"])
                continue
            quotes = [spans[s]["quote"] for s in i["source_span_ids"]]
            original_windows = [spans[s] for s in i["source_span_ids"]]
            for field, relation in (("equipment_entities", "entity_ids"), ("metric_entities", "metric_ids")):
                mentioned = {e["entity_id"] for e in candidate[field] if e["status"] == "active" and
                    any(any(w["start"] <= spans[s]["start"] < w["end"] for w in original_windows) for s in e["source_span_ids"])}
                if mentioned and not set(i[relation]) <= mentioned:
                    errors.append("intent_object_relation_conflicts_with_quote:" + i["intent_id"])
            if not any(re.search(INTENT_CUES[i["type"]], q) for q in quotes):
                errors.append("unsupported_intent:" + i["intent_id"])
            if i["request_kind"] in ("query", "task_draft") and i["type"] not in ("unknown", "inspection_plan_draft"):
                if all(NEGATIVE.search(q) for q in quotes):
                    errors.append("negative_request_made_affirmative:" + i["intent_id"])
            original = next((x for x in evidence["intents"] if x["intent_id"] == i["intent_id"] and x["type"] == i["type"]), None)
            if original and original["request_kind"] in ("negated_request", "conditional_task") and i["request_kind"] != original["request_kind"]:
                errors.append("negation_or_condition_lost:" + i["intent_id"])
            if i["type"] in DRAFT_TYPES and i["request_kind"] not in ("task_draft", "conditional_task", "negated_request"):
                errors.append("plan_is_not_a_query_or_execution:" + i["intent_id"])
            if i["type"] == "operation_proposal" and i["request_kind"] != "negated_request":
                # A quote spanning both a plan and a prohibited navigation is not
                # affirmative evidence. Only locally positive/conditional scopes count.
                from inspection_brain.domain_v2.scopes import action_scopes
                positive = [s for s in action_scopes(text) if s["polarity"] in ("proposal", "conditional")]
                if not positive:
                    errors.append("prohibited_operation_made_positive:" + i["intent_id"])
                if any(s["polarity"] == "conditional" for s in positive) and i["request_kind"] != "conditional_task":
                    errors.append("operation_condition_lost:" + i["intent_id"])
                if i["request_kind"] not in ("task_draft", "conditional_task"):
                    errors.append("operation_requires_draft:" + i["intent_id"])
            if i["request_kind"] == "conditional_task" and not candidate["conditions"]:
                errors.append("conditional_task_without_condition")
        # Clear multi-information needs cannot be silently dropped.
        for required in evidence["intents"]:
            if required["type"] != "unknown" and not any(i["type"] == required["type"] for i in candidate["intents"]):
                errors.append("missing_explicit_information_need:" + required["type"])
        if not set(evidence["required_data_sources"]) <= set(candidate["required_data_sources"]):
            errors.append("missing_required_data_source")
        for field in ("uncertainties", "clarification_requests"):
            if not set(evidence[field]) <= set(candidate[field]):
                errors.append("missing_review_requirement:" + field)
        for field in ("uncertainties", "clarification_requests"):
            if any(re.search(r"已(?:授权|执行|确定故障)|(?:确认|判定)(?:为|了)?(?:故障|过热)|现场(?:正常|故障已确认)", s) for s in candidate[field]):
                errors.append("unsupported_site_conclusion_or_authorization:" + field)
        for collection in (candidate["negations"], candidate["self_corrections"], candidate["conditions"]):
            for relation in collection:
                for key in ("target_ids", "rejected_ids", "accepted_ids", "scope_ids"):
                    if not set(relation.get(key, [])) <= ids.keys():
                        errors.append("unknown_relation_target:" + relation.get("relation_id", relation.get("condition_id", "")))
        edges = {i: set() for i in intent_ids}
        for dep in candidate["task_dependencies"]:
            before, after = dep["before_intent_id"], dep["after_intent_id"]
            if before not in intent_ids or after not in intent_ids or before == after:
                errors.append("invalid_task_dependency")
                continue
            edges[before].add(after)
            if dep["kind"] == "explicit_sequence" and not any(re.search(r"先|再|然后|之后", spans[s]["quote"]) for s in dep["source_span_ids"]):
                errors.append("sequence_without_original_evidence")
            if dep["kind"] == "data_prerequisite" and ids[after]["type"] not in ("temperature_comparison", "reinspection_recommendation", "report_draft"):
                errors.append("unsupported_data_dependency")
        visiting, visited = set(), set()
        def cycle(node):
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            found = any(cycle(child) for child in edges[node])
            visiting.remove(node); visited.add(node)
            return found
        if any(cycle(node) for node in edges):
            errors.append("dependency_cycle")
        for required in evidence["task_dependencies"]:
            if required not in candidate["task_dependencies"]:
                errors.append("explicit_dependency_missing")
        draft = candidate["structured_task_draft"]
        if draft["original_request"] != text or draft["task_dependencies"] != candidate["task_dependencies"]:
            errors.append("draft_provenance_or_dependencies_changed")
        targets = {e["entity_id"] for e in draft["target_equipment"]}
        expected_targets = {e["entity_id"] for e in candidate["equipment_entities"] if e["entity_kind"] == "device" and e["status"] == "active"}
        if targets != expected_targets:
            errors.append("draft_device_identity_or_target_changed")
        goals = {i["intent_id"] for i in candidate["intents"] if i["request_kind"] != "negated_request"}
        if set(draft["business_goals"]) != goals or set(draft["required_data"]) != set(candidate["required_data_sources"]):
            errors.append("draft_goal_or_data_mismatch")
        for key in ("preconditions", "evidence_requirements", "prohibitions"):
            if draft[key] != evidence["structured_task_draft"][key]:
                errors.append("unverified_draft_statement:" + key)
        warnings = ["设备唯一身份、数值及现场状况未核验；此结果仅为不可执行语义草案"]
        if candidate["self_corrections"]:
            warnings.append("自我修正须人工核对原音频；不构成设备执行授权")
        return {"valid": not errors, "errors": sorted(set(errors)), "warnings": warnings, "requires_human_confirmation": True}
