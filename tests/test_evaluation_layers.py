from copy import deepcopy
from datetime import datetime
import unittest
from brain_v3.engine import SemanticEngine
from brain_v3.providers import MockProvider
from brain_v3.validator import SemanticValidator
from brain_v3.schema import schema_errors
from tools.evidence_metrics import check_evidence
from tools.brain_smoke import summarize


class EvaluationLayerTests(unittest.TestCase):
    def setUp(self):
        self.result=SemanticEngine(provider=MockProvider()).analyze('不是2号断路器，是3号断路器。查询上周告警，但不要启动机器人。',mode='v3_llm',now=datetime.fromisoformat('2026-11-02T12:00:00+08:00'))
        self.evidence=self.result['model_candidate']

    def row(self,candidate,parse=True):
        result=deepcopy(self.result);result['model_candidate']=candidate
        result['validation']=SemanticValidator().validate(candidate,self.evidence)
        return {'input':result['original_request'],'result':result,'diagnostics':{'json_parse_success':parse},
                'parsed_candidate':candidate,'candidate_observed':True,'evidence_check':check_evidence(candidate,self.evidence)}

    def test_schema_pass_does_not_imply_evidence_pass(self):
        for mutation in (lambda c:c['source_spans'][0].update(quote='伪造文本'),
                         lambda c:c['equipment_entities'][1].update(device_number='2'),
                         lambda c:c.update(negations=[]),
                         lambda c:c['temporal_constraints'][0].update(start='2026-11-02T00:00:00+08:00'),
                         lambda c:c.update(self_corrections=[])):
            candidate=deepcopy(self.evidence);mutation(candidate)
            self.assertEqual(schema_errors(candidate),[])
            report=summarize([self.row(candidate)])
            self.assertEqual(report['schema_pass_rate'],1)
            self.assertEqual(report['evidence_constraint_pass_rate'],0)
            self.assertEqual(report['validator_acceptance_rate'],0)
            self.assertIsNone(report['human_gold_accuracy'])

    def test_evidence_metric_is_independent_of_full_validator(self):
        c=deepcopy(self.evidence);c['structured_task_draft']['preconditions'].append('unverified new precondition')
        self.assertEqual(schema_errors(c),[])
        report=summarize([self.row(c)])
        self.assertEqual(report['evidence_constraint_pass_rate'],1)
        self.assertEqual(report['validator_acceptance_rate'],0)
        self.assertEqual(summarize([self.row(self.evidence)])['evidence_constraint_pass_rate'],1)

    def test_json_schema_and_unavailable_separation(self):
        report=summarize([self.row({'unexpected':'legal JSON'})])
        self.assertEqual(report['json_parse_success_rate'],1)
        self.assertEqual(report['schema_pass_rate'],0)
        report=summarize([])
        self.assertIsNone(report['json_parse_success_rate']);self.assertIsNone(report['schema_pass_rate'])
        self.assertIsNone(report['evidence_constraint_pass_rate']);self.assertIsNone(report['human_gold_accuracy'])
