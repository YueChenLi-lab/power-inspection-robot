"""Lab engineering fixtures; no real Qwen success is claimed by these tests."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain_v3.config import ProviderConfig
from brain_v3.schema import SCHEMA
from evaluation_lab.service import EvaluationService,BusyError,safe_raw
from evaluation_lab.storage import Store
from evaluation_lab.metrics import aggregate

REFERENCE='2026-11-02T12:00:00+08:00'


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.requests=[];self.mode='valid';self.delay=0
        self.entered=threading.Event();outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,value):
                body=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_GET(self):
                if self.path=='/api/version':self.send({'version':'mock-http-v1'})
                elif self.path=='/api/tags':self.send({'models':[{'name':'fixture-model','digest':'fixture-digest','details':{'family':'fixture'}}]})
                else:self.send_error(404)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));outer.requests.append(body);outer.entered.set();time.sleep(outer.delay)
                c=deepcopy(json.loads(body['messages'][1]['content'])['evidence']);c['structured_task_draft']['reasoning_source']='llm_candidate'
                if outer.mode=='missing':c.pop('negations')
                if outer.mode=='enum':c['intents'][0]['type']='bad_enum'
                if outer.mode=='evidence':c['source_spans'][0]['quote']='forged'
                if outer.mode=='unsafe':c['structured_task_draft']['authorized']=True
                if outer.mode=='reasoning':c['thinking']='HIDDEN_COT_MUST_NOT_BE_SAVED'
                content='{' if outer.mode=='json' else json.dumps(c,ensure_ascii=False)
                response={'done':outer.mode!='truncated','done_reason':'length' if outer.mode=='truncated' else 'stop',
                          'model':'fixture-model','message':{'content':content,'thinking':'HIDDEN_COT_MUST_NOT_BE_SAVED'},
                          'total_duration':3_000_000,'load_duration':2_000_000,'prompt_eval_duration':500_000,'eval_duration':500_000,
                          'prompt_eval_count':100,'eval_count':20}
                self.send(response)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config=ProviderConfig(provider='ollama',enabled=True,base_url=f'http://127.0.0.1:{self.server.server_port}',model='fixture-model')
        self.store=Store(Path(self.temp.name)/'lab.db');self.service=EvaluationService(self.store,self.config,test_fixture=True)

    def tearDown(self):
        for t in self.service.batch_threads:t.join(5)
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.close();self.temp.cleanup()

    def run_case(self,case='T1',**kwargs):
        return self.service.evaluate({'case_id':case,'provider':'ollama','model':'fixture-model','reference_time':REFERENCE,**kwargs})

    def test_native_pipeline_and_ns_conversion(self):
        r=self.run_case()
        self.assertEqual(r['source'],'MOCK HTTP');self.assertEqual(r['outcome'],'ACCEPTED')
        self.assertEqual(self.requests[0]['format'],SCHEMA);self.assertFalse(self.requests[0]['think'])
        prompt=self.requests[0]['messages'][1]['content']
        for key in ('must_preserve','must_not','annotation_status','expected','annotator'):self.assertNotIn('"'+key+'"',prompt)
        self.assertTrue(r['parse_result']['passed']);self.assertTrue(r['schema_result']['passed']);self.assertTrue(r['validator_result']['valid'])
        self.assertEqual(r['token_metrics']['total_duration_ms'],3)
        self.assertEqual(r['token_metrics']['eval_count'],20)
        self.assertEqual(r['model_version'],'fixture-digest')
        self.assertNotIn('HIDDEN_COT',json.dumps(self.store.get(r['evaluation_id'])))
        self.assertTrue(r['reasoning_redacted'])
        self.assertFalse(any(r['safety_result'][k] for k in ('authorized','executable','hardware_commands_enabled')))

    def test_engineering_invalid_layers(self):
        for mode in ('json','missing','enum','evidence','unsafe','truncated'):
            with self.subTest(mode=mode):
                self.mode=mode;r=self.run_case()
                self.assertEqual(r['outcome'],'PROVIDER_ERROR' if mode=='truncated' else 'REJECTED')
                self.assertFalse(r['safety_result']['executable'])
                self.assertIsNone(r['task_draft'])
                if mode=='unsafe':self.assertTrue(r['safety_result']['candidate_violation'])
                if mode=='evidence':self.assertTrue(r['schema_result']['passed']);self.assertFalse(r['evidence_result']['passed'])

    def test_unavailable_model_timeout_no_fallback(self):
        r=self.run_case(model='not-installed');self.assertEqual(r['outcome'],'PROVIDER_ERROR');self.assertEqual(len(self.requests),0)
        self.delay=.2;self.service.config=replace(self.config,timeout_seconds=.1)
        r=self.run_case();self.assertEqual(r['request_result']['failure_kind'],'timeout');self.assertFalse(r['fallback_used'])
        with patch.object(self.service.catalog,'check',return_value={'connected':False,'models':[],'version':None,'error':'fixture unavailable'}):
            r=self.run_case();self.assertEqual(r['outcome'],'PROVIDER_ERROR')

    def test_source_grouping_human_annotation_and_persistence(self):
        real=self.run_case()
        for provider in ('mock','rules'):self.run_case(provider=provider)
        groups=self.service.statistics()['groups'];self.assertEqual({g['source'] for g in groups},{'MOCK HTTP','MOCK','RULES'})
        for g in groups:self.assertIsNone(g['metrics']['semantic_accuracy']['value']);self.assertIsNone(g['metrics']['human_evidence_consistency']['value'])
        self.service.annotate(real['evaluation_id'],{'confirmed':True,'annotator':'independent-reviewer','evidence_consistent':False,'semantic_dimensions':{'intents':True,'negations':False,'numeric_relations':None}})
        m=next(g['metrics'] for g in self.service.statistics()['groups'] if g['source']=='MOCK HTTP')
        self.assertEqual(m['semantic_accuracy']['value'],.5);self.assertEqual(m['human_evidence_consistency']['value'],0)
        self.assertEqual(m['semantic_accuracy']['denominator'],2)
        old=self.store.get(real['evaluation_id']);self.assertEqual(old['outcome'],'ACCEPTED')
        reopened=Store(self.store.path)
        try:self.assertIsNotNone(reopened.get(real['evaluation_id'])['annotation'])
        finally:reopened.close()
        for payload in ({'confirmed':'true','annotator':'x','evidence_consistent':True}, {'confirmed':True,'annotator':'x','semantic_dimensions':{'intents':'true'}}):
            with self.assertRaises(ValueError):self.service.annotate(real['evaluation_id'],payload)

    def test_conditional_denominators_and_missing_metrics(self):
        self.run_case()
        self.mode='json';self.run_case()
        self.mode='missing';self.run_case()
        self.run_case(model='not-installed')
        m=self.service.statistics()['groups'][0]['metrics']
        # Installed model digest has three complete responses; missing model is a separate config group.
        installed=next(g['metrics'] for g in self.service.statistics()['groups'] if g['model_version']=='fixture-digest')
        self.assertEqual(installed['request_success_rate']['denominator'],3)
        self.assertEqual(installed['json_parse_rate']['value'],2/3)
        self.assertEqual(installed['schema_pass_rate']['value'],.5)
        self.assertEqual(installed['validator_acceptance_rate']['denominator'],1)
        self.assertEqual(sum(b['count'] for b in installed['latency']['histogram']),3)

    def test_batch_serial_busy_and_export_filters(self):
        self.delay=.1
        batch=self.service.start_batch({'case_ids':['T1','T5'],'provider':'ollama','model':'fixture-model','reference_time':REFERENCE})
        self.assertTrue(self.entered.wait(2))
        with self.assertRaises(BusyError):self.run_case()
        for thread in self.service.batch_threads:thread.join(5)
        done=self.store.batch(batch['batch_id']);self.assertEqual(done['status'],'COMPLETED');self.assertEqual(done['completed'],2)
        self.assertEqual(len(self.store.records(category='禁止事项')),1)
        for kind in ('json','csv','markdown'):
            body,mime=self.service.export(kind,source='MOCK HTTP');self.assertTrue(body);self.assertIn('fixture-model',body.decode('utf-8-sig'))
        self.assertEqual(len(json.loads(self.service.export('json',category='禁止事项')[0])['records']),1)

    def test_ambiguous_case_and_annotation_independence(self):
        r=self.run_case('T8');self.assertEqual(r['outcome'],'NEEDS_CLARIFICATION')
        self.assertTrue(all(c['annotation_status']=='pending' and c['annotator'] is None for c in self.service.cases))
        with self.assertRaises(ValueError):self.service.evaluate({'case_id':'T1','original_request':'modified','provider':'mock'})
        with self.assertRaises(ValueError):self.service.evaluate({'original_request':'test','provider':'mock','expected':{'gold':True}})

    def test_reasoning_redaction_and_csv_formula(self):
        self.mode='reasoning';r=self.run_case();self.assertEqual(r['outcome'],'REJECTED')
        self.assertNotIn('HIDDEN_COT',json.dumps(self.store.get(r['evaluation_id'])))
        self.service.evaluate({'provider':'mock','original_request':'=2+2'})
        data=self.service.export('csv')[0].decode('utf-8-sig');self.assertIn("'=2+2",data)
        self.assertNotIn('secret',safe_raw('<think>secret</think>{broken')[0])
