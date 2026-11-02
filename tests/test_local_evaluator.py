"""Controlled contract fixtures: never evidence of real Qwen inference quality."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain_v3.config import ProviderConfig
from brain_v3.providers import MockProvider,RulesFallbackProvider
from evaluation.dataset import load_dataset,select_cases
from evaluation.diagnosis import diagnose_report
from evaluation.runners.observation import observe
from evaluation.runners.local_evaluator import evaluate_run,build_config,pilot_is_healthy
from evaluation.metrics.evaluator import compare_reference,summarize
from evaluation.runners.reports import load_records


@contextmanager
def contract_server(mode='valid',delay=0):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            data={'version':'CONTRACT_FIXTURE'} if self.path=='/api/version' else {'models':[{'name':'fixture-model','digest':'fixture-digest','details':{'parameter_size':'fixture','quantization_level':'fixture'}}]}
            self.send(data)
        def send(self,data):
            self.send_response(200);self.end_headers()
            try:self.wfile.write(json.dumps(data,ensure_ascii=False).encode())
            except (BrokenPipeError,ConnectionResetError):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(data);time.sleep(delay)
            candidate=deepcopy(json.loads(data['messages'][1]['content'])['evidence'])
            candidate['structured_task_draft']['reasoning_source']='llm_candidate'
            if mode=='missing':candidate.pop('negations')
            if mode=='type':candidate['intents']='wrong-type'
            if mode=='extra':candidate['invented']='field'
            if mode=='enum':candidate['intents'][0]['type']='invalid-intent'
            if mode=='wrong_id':candidate['equipment_entities'][0]['device_number']='999'
            if mode=='invented_device':candidate['equipment_entities'].append({**candidate['equipment_entities'][0],'entity_id':'fake','device_number':'123'})
            if mode=='lost_negation':candidate['negations']=[]
            if mode=='unsafe':candidate['structured_task_draft']['authorized']=True
            content='{' if mode=='json' else json.dumps(candidate,ensure_ascii=False)
            self.send({'model':'fixture-model','done':True,'done_reason':'stop','message':{'content':content},'load_duration':1000000,'eval_count':20})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    config=ProviderConfig(provider='ollama',enabled=True,model='fixture-model',base_url=f'http://127.0.0.1:{server.server_port}')
    try:yield config,seen
    finally:server.shutdown();server.server_close();thread.join()


class DatasetTests(unittest.TestCase):
    def test_sixty_balanced_clocked_references_and_schema_enums(self):
        data,sha=load_dataset()
        from collections import Counter
        self.assertEqual(Counter(c['category'] for c in data['cases']),{k:10 for k in data['categories']})
        self.assertEqual(len(sha),64);self.assertEqual(len({c['original_request'] for c in data['cases']}),60)
        self.assertTrue(all(not c['annotation']['confirmed'] and c['reference_time'].endswith('+08:00') for c in data['cases']))
        self.assertEqual(select_cases(data,category='negation',limit=1)[0]['case_id'],'T3-001')
        self.assertEqual(len(select_cases(data,case_id='T4-001')),1)
        with self.assertRaises(ValueError):select_cases(data,limit=0)


class ContractTests(unittest.TestCase):
    def setUp(self):self.case=load_dataset()[0]['cases'][10] # explicit correction
    def test_invalid_json_structure_and_evidence_are_separate(self):
        modes={'json':'json','missing':'schema','type':'schema','extra':'schema','enum':'schema','wrong_id':'validator','invented_device':'validator','lost_negation':'validator','unsafe':'schema'}
        for mode,stage in modes.items():
            with self.subTest(mode=mode),contract_server(mode) as (config,seen):
                row=observe(config,self.case,fixture=True)
                self.assertEqual(row['failure_stage'],stage)
                self.assertEqual(row['source'],'CONTRACT_FIXTURE');self.assertEqual(row['real_model_call_attempts'],0)
                self.assertFalse(any(row['safety']['fixed_flags'].values()))
                self.assertIsNone(row['result']['structured_task_draft'])
    def test_native_trace_never_sends_gold_and_timeout_classified(self):
        with contract_server() as (config,seen):
            case=deepcopy(self.case);case['expected']['private_marker']='GOLD_NOT_SENT'
            row=observe(config,case,fixture=True)
            self.assertNotIn('GOLD_NOT_SENT',json.dumps(seen))
            self.assertEqual(row['http']['status'],200);self.assertTrue(row['validator']['valid'])
            self.assertEqual(row['ollama_metrics']['load_duration_ms'],1)
        with contract_server(delay=.2) as (config,seen):
            row=observe(replace(config,timeout_seconds=.1),self.case,fixture=True)
            self.assertEqual(row['diagnostics']['failure_kind'],'timeout')
    def test_offline_fallback_is_labelled_and_does_not_authorize(self):
        config=ProviderConfig(provider='rules')
        row=observe(config,self.case,mode='auto_fallback',provider=RulesFallbackProvider(),fixture=True)
        self.assertTrue(row['result']['fallback_success']);self.assertTrue(row['fallback_used'])
        self.assertEqual(row['source'],'CONTRACT_FIXTURE');self.assertFalse(row['result']['executable'])
    def test_unavailable_service_not_json_or_semantic_failure(self):
        with contract_server() as (config,seen):
            provider=__import__('evaluation.runners.observation',fromlist=['ObservedOllamaProvider']).ObservedOllamaProvider(config)
            from urllib.error import URLError
            with patch.object(provider.observed_opener.opener,'open',side_effect=URLError('fixture offline')):
                row=observe(config,self.case,provider=provider,fixture=True)
            self.assertEqual(row['failure_stage'],'provider');self.assertIsNone(row['schema_errors'])
    def test_guard_failure_has_its_own_stage(self):
        with patch('brain_v3.safety.SafetyGuard.seal',side_effect=RuntimeError('CONTRACT_FIXTURE guard failure')):
            row=observe(ProviderConfig(provider='mock'),self.case,fixture=True)
        self.assertEqual(row['failure_stage'],'safety');self.assertTrue(row['safety']['guard_invoked'])
        self.assertTrue(row['validator']['valid']);self.assertFalse(row['result']['executable'])
    def test_legacy_smoke_diagnosis_never_infers_from_zero_accepted(self):
        report=diagnose_report({'rows':[{'input':'PRIVATE_DO_NOT_ECHO','result':{'status':'provider_unavailable','error':'timeout'}},
                                       {'result':{'status':'validation_rejected','validation':{'valid':False,'errors':['original_request_changed']}}}]})
        self.assertEqual(report['rows'][0]['failure_stage'],'provider_or_response_contract')
        self.assertEqual(report['rows'][1]['failure_stage'],'validator')
        self.assertNotIn('PRIVATE_DO_NOT_ECHO',json.dumps(report))


class RunnerTests(unittest.TestCase):
    def test_mock_reports_warmup_and_resume_do_not_overwrite_journal(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=ProviderConfig(provider='mock');calls=[]
            def interrupt(config,case,**kwargs):
                calls.append(case['case_id'])
                if len(calls)==2:raise KeyboardInterrupt()
                return observe(config,case,**kwargs)
            folder,state,rows=evaluate_run(config=cfg,output_dir=d,limit=3,observer=interrupt)
            self.assertEqual(state['status'],'INTERRUPTED');self.assertEqual(len(rows),1)
            prior=(folder/'raw_results.jsonl').read_bytes()
            folder,state,rows=evaluate_run(config=cfg,resume=folder)
            self.assertEqual(state['status'],'COMPLETED');self.assertEqual(len(rows),3)
            self.assertTrue((folder/'raw_results.jsonl').read_bytes().startswith(prior))
            for f in ('metadata.json','raw_results.json','raw_results.jsonl','results.csv','metrics.json','evaluation_report.md','failures.json'):self.assertTrue((folder/f).is_file())
            self.assertEqual(json.loads((folder/'metrics.json').read_text())['real_model_call_attempts'],0)
            with self.assertRaises(ValueError):evaluate_run(config=replace(cfg,max_output_tokens=512),resume=folder)
            _,state,_=evaluate_run(config=cfg,output_dir=d,limit=1,warmup=True)
            self.assertEqual(state['completed'],1)
    def test_preflight_blocked_is_zero_calls_not_fake_ten_failures(self):
        with tempfile.TemporaryDirectory() as d:
            def never(*args,**kwargs):raise AssertionError('no model call after failed preflight')
            folder,state,rows=evaluate_run(config=ProviderConfig(provider='ollama',enabled=True,model='fixture'),output_dir=d,limit=10,
                                          service_probe=lambda:{'connected':False,'models':[],'version':None,'error':'fixture offline'},observer=never)
            self.assertEqual(state['status'],'BLOCKED');self.assertEqual(rows,[])
            report=json.loads((folder/'metrics.json').read_text());self.assertEqual(report['real_model_call_attempts'],0)
            self.assertIsNone(report['json_parse_rate']['value'])
            self.assertEqual(json.loads((folder/'failures.json').read_text())[0]['not_a_model_sample'],True)
    def test_fake_pilot_cannot_authorize_full_real_evaluation(self):
        with tempfile.TemporaryDirectory() as d:
            cfg=ProviderConfig(provider='mock');folder,state,_=evaluate_run(config=cfg,output_dir=d,limit=10)
            data,sha=load_dataset()
            with self.assertRaises(ValueError):pilot_is_healthy(folder,sha,ProviderConfig(provider='ollama'),{'models':[]})
    def test_cloud_endpoint_and_timeout_above_sixty_rejected(self):
        with patch.dict('os.environ',{'OLLAMA_BASE_URL':'http://remote.invalid:11434'},clear=True):
            with self.assertRaises(ValueError):build_config()
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError):build_config(timeout=120)
            self.assertEqual(build_config(timeout=60).timeout_seconds,60)
    def test_unconfirmed_references_do_not_become_semantic_accuracy(self):
        data,_=load_dataset();case=data['cases'][0]
        row=observe(ProviderConfig(provider='mock'),case)
        row['reference_checks']=compare_reference(row,case)
        report=summarize([row],[case])
        self.assertEqual(report['offline_or_contract_records'],1)
        self.assertIsNone(report['semantic_metrics']['intent_accuracy']['value'])
        self.assertIsNone(report['normal_draft_acceptance']['value'])
    def test_journal_corruption_rejected_without_silently_truncating(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'raw_results.jsonl';path.write_text('{broken')
            with self.assertRaises(ValueError):load_records(path)
            self.assertEqual(path.read_text(),'{broken')


class MetricFormulaTests(unittest.TestCase):
    def test_conditional_rates_and_fake_source_are_explicit(self):
        cases=load_dataset()[0]['cases'][:3]
        rows=[]
        with contract_server() as (config,seen):
            for case in cases:
                row=observe(config,case,fixture=True);row['reference_checks']=compare_reference(row,case);rows.append(row)
        # Controlled statistical fixtures remain labelled CONTRACT_FIXTURE. This
        # explicit test-only grouping is never used by the real CLI/report writer.
        rows[1]['schema_errors']=['$.negations:required'];rows[1]['validator']={'valid':False}
        rows[2]['diagnostics']['json_parse_success']=False
        report=summarize(rows,cases,metric_source='CONTRACT_FIXTURE')
        self.assertEqual(report['metric_source'],'CONTRACT_FIXTURE')
        self.assertEqual(report['model_response_rate']['value'],1)
        self.assertEqual(report['json_parse_rate']['value'],2/3)
        self.assertEqual(report['schema_pass_rate']['value'],.5)
        self.assertEqual(report['validator_acceptance_rate']['denominator'],1)
        self.assertEqual(report['real_model_call_attempts'],0)
        self.assertEqual(report['offline_or_contract_records'],3)
        self.assertIsNone(report['semantic_metrics']['intent_accuracy']['value'])
    def test_required_field_coverage_includes_nested_fields(self):
        from evaluation.metrics.evaluator import required_field_coverage
        from brain_v3.schema import SCHEMA
        case=load_dataset()[0]['cases'][0]
        candidate=observe(ProviderConfig(provider='mock'),case)['parsed_json']
        present,total=required_field_coverage(candidate,SCHEMA);self.assertEqual(present,total)
        candidate['structured_task_draft'].pop('original_request')
        present,total=required_field_coverage(candidate,SCHEMA);self.assertLess(present,total)


class SafetyAndPrivateOutputTests(unittest.TestCase):
    def test_existing_smoke_file_is_not_overwritten(self):
        from tools.brain_smoke import main
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'existing.json';path.write_text('ORIGINAL_PRIVATE_REPORT')
            with patch('sys.argv',['brain_smoke','--mock','--output',str(path)]):
                with self.assertRaises(SystemExit) as error:main()
            self.assertEqual(error.exception.code,2);self.assertEqual(path.read_text(),'ORIGINAL_PRIVATE_REPORT')
    def test_motion_proposal_keeps_independent_false_flags(self):
        case=next(c for c in load_dataset()[0]['cases'] if c['case_id']=='T6-004')
        record=observe(ProviderConfig(provider='mock'),case)
        self.assertFalse(any(record['safety']['fixed_flags'].values()))
        draft=record['result'].get('structured_task_draft')
        if draft:self.assertTrue(draft['human_confirmation_required']);self.assertFalse(draft['executable'])


class ExpectedOutcomeTests(unittest.TestCase):
    def test_expected_rejection_is_not_a_normal_acceptance_failure(self):
        cases=deepcopy(load_dataset()[0]['cases'][:2]);cases[1]['expected']['expected_decision']='reject_or_review'
        rows=[]
        with contract_server() as (config,seen):
            for case in cases:
                row=observe(config,case,fixture=True);rows.append(row)
        rows[1]['engine_status']='validation_rejected';rows[1]['failure_stage']='validator';rows[1]['validator']={'valid':False}
        for row,case in zip(rows,cases):row['reference_checks']=compare_reference(row,case)
        report=summarize(rows,cases,metric_source='CONTRACT_FIXTURE')
        self.assertEqual(report['normal_draft_acceptance']['denominator'],1)
        self.assertEqual(report['normal_draft_acceptance']['value'],1)
        self.assertEqual(rows[1]['reference_checks']['decision_note'],'expected_rejection_or_review')
        self.assertIsNone(report['expected_rejection_accuracy']['value']) # Human gold still pending.

    def test_bad_json_is_not_a_correct_expected_rejection(self):
        case=deepcopy(load_dataset()[0]['cases'][0]);case['expected']['expected_decision']='reject'
        case['annotation']={'confirmed':True,'status':'confirmed','source':'human_review','annotator':'CONTRACT_FIXTURE'}
        with contract_server('json') as (config,seen):row=observe(config,case,fixture=True)
        row['reference_checks']=compare_reference(row,case)
        report=summarize([row],[case],metric_source='CONTRACT_FIXTURE')
        self.assertEqual(row['reference_checks']['decision_note'],'structural_failure_not_expected_rejection')
        self.assertIsNone(report['expected_rejection_accuracy']['value'])
        self.assertEqual(report['json_parse_rate']['value'],0)

    def test_extra_numeric_relation_does_not_score_as_correct(self):
        case=deepcopy(next(c for c in load_dataset()[0]['cases'] if c['case_id']=='T4-006'))
        row=observe(ProviderConfig(provider='mock'),case)
        # A controlled scoring fixture, independently of Validator acceptance.
        case['expected']['numeric_relations']=[]
        self.assertFalse(compare_reference(row,case)['checks']['numeric_relation_accuracy'])


class AttemptJournalTests(unittest.TestCase):
    def test_interrupted_http_attempt_is_durable_and_remains_a_fixture(self):
        with tempfile.TemporaryDirectory() as d,contract_server() as (config,seen):
            def interrupt(config,case,**kwargs):
                from evaluation.runners.observation import ObservedOllamaProvider
                provider=ObservedOllamaProvider(config,on_attempt=kwargs['on_attempt'])
                with patch.object(provider.observed_opener.opener,'open',side_effect=KeyboardInterrupt()):
                    return observe(config,case,provider=provider,fixture=kwargs['fixture'])
            folder,state,rows=evaluate_run(config=config,output_dir=d,limit=1,observer=interrupt,fixture=True)
            self.assertEqual(state['status'],'INTERRUPTED');self.assertEqual(rows,[])
            first=(folder/'request_attempts.jsonl').read_bytes()
            metrics=json.loads((folder/'metrics.json').read_text())
            self.assertEqual(metrics['request_attempt_records'],1);self.assertEqual(metrics['incomplete_attempt_records'],1)
            self.assertEqual(metrics['real_model_call_attempts_including_warmup'],0)
            folder,state,rows=evaluate_run(config=config,resume=folder,fixture=True)
            self.assertEqual(state['status'],'COMPLETED');self.assertEqual(len(rows),1)
            self.assertTrue((folder/'request_attempts.jsonl').read_bytes().startswith(first))
            self.assertEqual(len(load_records(folder/'request_attempts.jsonl',identifier='attempt_id')),2)

    def test_failed_warmup_cannot_be_bypassed_by_resume(self):
        with tempfile.TemporaryDirectory() as d,contract_server('json') as (config,seen):
            folder,state,rows=evaluate_run(config=config,output_dir=d,limit=1,warmup=True,fixture=True)
            self.assertEqual(state['status'],'WARMUP_FAILED');original=(folder/'warmup.json').read_bytes()
            folder,state,rows=evaluate_run(config=config,resume=folder,fixture=True)
            self.assertEqual(state['status'],'WARMUP_FAILED');self.assertEqual(len(seen),1)
            self.assertEqual((folder/'warmup.json').read_bytes(),original)
