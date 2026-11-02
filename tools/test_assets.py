"""Exact historical prerequisites, not fabricated replacements or broad skips."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXPORT='voice-evaluation.json'
RECORD='InspectionBrain/runtime/voice_lab/records/9bf3bee5bf3e48e3b60a3a33d6966bc5.json'
ASSETS={
    'test_domain_v2.DomainV2Tests.test_multi_intent_and_real_cases':EXPORT,
    'test_domain_v2.DomainV2Tests.test_real_data_rules_and_switch_are_separate':EXPORT,
    'test_round2_audit.ActualExportTests.test_actual_export_is_read_and_preserved':EXPORT,
    'test_round2_scoring.Round2ScoringTests.test_complex_query_does_not_claim_complete_answer_from_one_keyword':EXPORT,
    'test_round2_scoring.Round2ScoringTests.test_import_preserves_history_and_excludes_unbound_old_metrics':EXPORT,
    'test_scoring_workflow.HistorySemanticsTests.test_actual_record_without_reference_leakage':RECORD,
}


def apply_asset_policy(suite,root=ROOT):
    """Keep every test in the runner; report only exact missing prerequisites skipped."""
    import unittest
    missing=[]
    def visit(group):
        for test in group:
            if isinstance(test,unittest.TestSuite):visit(test);continue
            path=next((asset for name,asset in ASSETS.items() if test.id().endswith(name)),None)
            if path and not (root/path).is_file():
                reason='historical asset unavailable (not passed): '+path
                missing.append({'test':test.id(),'asset':path,'outcome':'skipped'})
                test.setUp=lambda reason=reason,t=test:t.skipTest(reason)
    visit(suite)
    return missing
