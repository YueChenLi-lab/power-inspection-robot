from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.ollama import OllamaProvider
from brain_v3.providers import MockProvider
from brain_v3.validator import SemanticValidator

NOW = datetime.fromisoformat('2026-11-02T12:00:00+08:00')


class OllamaTests(unittest.TestCase):
    def setUp(self):
        outer = self
        self.mutate = lambda x: x
        self.content = None
        self.delay = 0
        self.envelope = None
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                outer.request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                outer.path = self.path
                evidence = json.loads(outer.request['messages'][1]['content'])['evidence']
                evidence['structured_task_draft']['reasoning_source'] = 'llm_candidate'
                content = outer.content if outer.content is not None else json.dumps(outer.mutate(evidence))
                body = json.dumps(outer.envelope if outer.envelope is not None else {'model':'mock-http-not-real-qwen','done':True,'message':{'content':content}}).encode()
                time.sleep(outer.delay)
                try:
                    self.send_response(200); self.end_headers(); self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError): pass
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config = ProviderConfig(provider='ollama',enabled=True,base_url=f'http://127.0.0.1:{self.server.server_port}',model='qwen3:4b-instruct')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def analyze(self,text,mode='v3_llm',config=None):
        self.provider=OllamaProvider(config or self.config)
        return SemanticEngine(provider=self.provider,config=config or self.config).analyze(text,mode=mode,now=NOW)

    def test_t1_t2_t3_http_schema_and_original(self):
        cases=['查询3号断路器的上周告警。','不是2号断路器，是3号断路器。查询上周告警，但不要启动机器人。','查询3号断路器上周的红外测温记录，比较最近两次测温结果。']
        for text in cases:
            r=self.analyze(text)
            self.assertEqual(r['status'],'validated_candidate',r['error'])
            self.assertEqual(self.path,'/api/chat');self.assertIn('$defs',self.request['format'])
            self.assertEqual(r['original_request'],text)
            self.assertFalse(r['executable'])
            sem=r['v3']['semantic']
            self.assertEqual([e['device_number'] for e in sem['equipment_entities'] if e['status']=='active'],['3'])
            self.assertTrue(any(t['start']=='2026-10-26T00:00:00+08:00' for t in sem['temporal_constraints']))
            self.assertIsNotNone(self.provider.last_response)
        self.assertTrue(sem['task_dependencies'])

    def test_t4_invalid_json_and_schema(self):
        for content in ('{','{"x":1,"x":2}','[]'):
            self.content=content
            self.assertEqual(self.analyze('查询3号断路器告警')['status'],'provider_unavailable')
        self.content=None
        for change in (lambda c:c.pop('negations'),lambda c:c.update(extra=True),lambda c:c.update(intents='bad'),lambda c:c['intents'][0].update(type='navigate')):
            def mutate(c):change(c);return c
            self.mutate=mutate
            self.assertEqual(self.analyze('查询3号断路器告警')['status'],'validation_rejected')

    def test_t5_semantic_conflicts(self):
        changes=[lambda c:c['equipment_entities'][0].update(device_number='2'),
                 lambda c:c['temporal_constraints'][0].update(start='2026-11-02T00:00:00+08:00'),
                 lambda c:c['structured_task_draft'].update(executable=True),
                 lambda c:c.update(negations=[])]
        for change in changes:
            def mutate(c):change(c);return c
            self.mutate=mutate
            self.assertEqual(self.analyze('查询3号断路器上周告警，但不要启动机器人')['status'],'validation_rejected')

    def test_timeout_fallback_is_explicit(self):
        self.delay=.2
        config=ProviderConfig(provider='ollama',enabled=True,base_url=self.config.base_url,model=self.config.model,timeout_seconds=.1)
        r=self.analyze('查询3号断路器告警','auto_fallback',config)
        self.assertTrue(r['fallback_success'])
        self.assertEqual(r['structured_task_draft']['reasoning_source'],'rules_v2')
        self.assertIsNone(r['model_candidate'])

    def test_disabled_and_environment_compatibility(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{'BRAIN_V3_PROVIDER':'ollama'},clear=True):
            c=ProviderConfig.from_environment()
            self.assertEqual(c.model,'qwen3:4b-instruct');self.assertEqual(c.timeout_seconds,60)
            self.assertFalse(c.enabled)
        self.assertEqual(ProviderConfig().provider,'rules')

    def test_invalid_envelope_truncation_and_tool_calls_rejected(self):
        for body in ([],{'done':False,'message':{'content':'{}'}}, {'done':True,'message':[]},
                     {'done':True,'message':{'content':'{}','tool_calls':[{'name':'move'}]}}):
            self.envelope=body
            result=self.analyze('查询3号断路器告警')
            self.assertEqual(result['status'],'provider_unavailable')
            self.assertIn('json_parse_seconds',self.provider.timings)
