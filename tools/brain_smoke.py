"""Explicit real-model smoke / offline contract evaluation. No hardware imports."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"InspectionBrain"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.schema import schema_errors
from brain_v3.validator import SemanticValidator
from brain_v3.evidence import build_evidence
from tools.evidence_metrics import check_evidence

DATASET = json.loads((Path(__file__).resolve().parents[1]/"tests/fixtures/semantic_cases.json").read_text())
CASES = [c["text"] for c in DATASET["cases"]]


class TimedValidator(SemanticValidator):
    def validate(self, candidate, evidence):
        start = time.perf_counter()
        errors = schema_errors(candidate)
        schema_time = time.perf_counter()-start
        start = time.perf_counter()
        result = super().validate(candidate, evidence)
        self.timings = {"schema_seconds": schema_time, "evidence_semantic_seconds": time.perf_counter()-start,
                        "schema_valid": not errors}
        return result


def evaluate(config):
    engine = SemanticEngine(config=config)
    engine.validator = TimedValidator()
    rows = []
    for text in CASES:
        engine.validator.timings = {}
        result = engine.analyze(text, mode="v3_llm", now=datetime.fromisoformat("2026-11-02T12:00:00+08:00"))
        evidence=build_evidence(text,result['v2'],datetime.fromisoformat(result['reference_time']))
        parsed=result['model_candidate'] if result['model_candidate'] is not None else getattr(engine.provider,'last_candidate',None)
        diagnostics=getattr(engine.provider,'diagnostics',{})
        observed=result['model_candidate'] is not None or diagnostics.get('json_parse_success') is True
        rows.append({"evidence_check":check_evidence(parsed,evidence) if observed else None,
                     "diagnostics":dict(diagnostics),"parsed_candidate":parsed,"candidate_observed":observed,"input": text, "result": result, "timings": getattr(engine.validator, "timings", {}),
                     "provider_timings": getattr(engine.provider, "timings", {}),
                     "raw_response": getattr(engine.provider, "last_response", None)})
    return rows


def summarize(rows):
    from observability.metrics import distribution
    fields=[]
    for row,case in zip(rows,DATASET['cases']):
        r=row['result'];s=r.get('model_candidate');expected=case['expected']
        matched=False
        if s and not schema_errors(s):
            matched=([e['device_number'] for e in s['equipment_entities'] if e['status']=='active']==expected['active_numbers'] and
                     [e['device_number'] for e in s['equipment_entities'] if e['status']=='negated']==expected['negated_numbers'] and
                     any(t['start']==expected['week_start'] for t in s['temporal_constraints']) and
                     (not expected.get('requires_negation') or bool(s['negations'])) and
                     (not expected.get('requires_correction') or bool(s['self_corrections'])) and
                     (not expected.get('unresolved_target') or any(not t['resolved'] for t in s['temporal_constraints'])))
        fields.append(bool(matched))
    n=len(rows)
    parses=[r['diagnostics']['json_parse_success'] for r in rows if r.get('diagnostics',{}).get('json_parse_success') is not None]
    candidates=[r.get('parsed_candidate',r['result'].get('model_candidate')) for r in rows if r.get('candidate_observed',r['result'].get('model_candidate') is not None)]
    checks=[r['evidence_check'] for r in rows if r.get('evidence_check') is not None]
    rate=lambda values:sum(values)/len(values) if values else None
    from collections import Counter
    failures=Counter(r.get('diagnostics',{}).get('failure_kind') for r in rows if r.get('diagnostics',{}).get('failure_kind'))
    return {'samples':n,'dataset_role':DATASET['dataset_role'],'human_gold_accuracy':None,
            'json_parse_success_rate':rate(parses),'json_parse_observations':len(parses),
            'schema_pass_rate':rate([not schema_errors(c) for c in candidates]),'schema_observations':len(candidates),
            'validator_acceptance_rate':rate([(r['result'].get('validation') or {}).get('valid',False) for r in rows]),'validator_attempts':n,
            'synthetic_key_fields_match_rate':rate(fields),'fallback_count':sum(r['result']['fallback_used'] for r in rows),
            'evidence_constraint_pass_rate':rate([c['passed'] for c in checks]),'evidence_observations':len(checks),'failure_counts':dict(failures),
            'real_model_successes':sum(r['result']['model_candidate'] is not None and r['result']['provider']['is_real_llm'] for r in rows),
            'latency_seconds':distribution([r['result']['total_seconds'] for r in rows])}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    config = ProviderConfig(provider="mock") if a.mock else ProviderConfig.from_environment()
    if not a.mock and (config.provider != "ollama" or not config.enabled):
        p.error("真实smoke要求BRAIN_V3_PROVIDER=ollama且BRAIN_V3_ENABLE_LLM=true")
    rows = evaluate(config)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit private diagnostics export; caller must choose a non-public path.
    a.output.write_text(json.dumps({"mock_http": False, "summary": summarize(rows), "rows": rows}, ensure_ascii=False, indent=2))
    print(json.dumps({"samples": len(rows), "accepted": sum(r["result"]["status"] == "validated_candidate" for r in rows),
                      "real_model_requested": not a.mock}))
    return 0 if all(r["result"]["status"] == "validated_candidate" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
