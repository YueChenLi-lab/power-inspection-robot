from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from evaluation_lab.app import Server
from evaluation_lab.service import EvaluationService
from evaluation_lab.storage import Store


class LabHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'db');self.service=EvaluationService(self.store)
        self.server=Server(self.service,0);self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.close();self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        default={'Content-Type':'application/json','X-Evaluation-Token':self.server.token};default.update(headers or {})
        conn.request('GET' if body is None else 'POST',path,body=json.dumps(body) if body is not None else None,headers=default)
        response=conn.getresponse();status=response.status;data=response.read();mime=response.getheader('Content-Type');csp=response.getheader('Content-Security-Policy');conn.close()
        return status,json.loads(data) if mime.startswith('application/json') else data,csp

    def test_real_http_application_pages_record_statistics_and_export(self):
        for path in ('/','/app.js','/style.css'):
            status,data,csp=self.request(path);self.assertEqual(status,200);self.assertTrue(data);self.assertIn("frame-ancestors 'none'",csp)
        self.assertEqual(self.request('/api/config')[1]['csrf_token'],self.server.token)
        self.assertEqual(len(self.request('/api/dataset')[1]['cases']),12)
        status,r,_=self.request('/api/evaluate',{'provider':'mock','case_id':'T1'})
        self.assertEqual(status,200);self.assertEqual(r['source'],'MOCK');self.assertEqual(r['outcome'],'ACCEPTED')
        eid=r['evaluation_id'];self.assertEqual(self.request('/api/records/'+eid)[1]['evaluation_id'],eid)
        self.assertEqual(len(self.request('/api/records?category=manual')[1]['records']),0)
        self.assertEqual(self.request('/api/statistics')[1]['groups'][0]['source'],'MOCK')
        for kind in ('json','csv','markdown'):self.assertEqual(self.request('/api/export?format='+kind)[0],200)
        data={'confirmed':True,'annotator':'local-review-label','evidence_consistent':True,'semantic_dimensions':{'intents':True}}
        self.assertEqual(self.request('/api/annotations/'+eid,data)[0],200)
        self.assertEqual(self.request('/api/statistics')[1]['groups'][0]['metrics']['semantic_accuracy']['value'],1)

    def test_local_only_csrf_and_no_control_routes(self):
        self.assertEqual(self.request('/api/config',headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.request('/api/config',headers={'Origin':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.request('/api/evaluate',{'provider':'mock','case_id':'T1'},headers={'X-Evaluation-Token':'wrong'})[0],403)
        for path in ('/api/execute','/api/approve','/api/robot/move'):
            self.assertEqual(self.request(path,{})[0],404)
        self.assertEqual(self.request('/api/models/check',{'base_url':'http://attacker.invalid'})[0],400)
        self.assertEqual(self.request('/api/evaluate',{'provider':'mock','original_request':'ok','expected':{'gold':True}})[0],400)

    def test_request_errors_and_persisted_failed_model_run(self):
        self.assertEqual(self.request('/api/evaluate',{'provider':'unknown','original_request':'test'})[0],400)
        self.assertEqual(self.request('/api/evaluate',{'provider':'mock','original_request':' '})[0],400)
        self.assertEqual(self.request('/api/records/not-found')[0],404)
        self.assertEqual(self.request('/api/export?format=unsupported')[0],400)

    def test_repository_launcher_serves_functional_request_and_stops(self):
        import re,signal,subprocess,sys
        root=Path(__file__).resolve().parents[1]
        process=subprocess.Popen([sys.executable,str(root/'InspectionBrain/run_evaluation_lab.py'),'--port','0','--db',str(Path(self.temp.name)/'launcher.sqlite')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            line=process.stdout.readline();match=re.search(r'port (\d+)',line)
            self.assertIsNotNone(match,line)
            port=int(match.group(1));conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            conn.request('GET','/api/config');config=json.loads(conn.getresponse().read());conn.close()
            conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
            conn.request('POST','/api/evaluate',json.dumps({'provider':'mock','case_id':'T1'}),{'Content-Type':'application/json','X-Evaluation-Token':config['csrf_token']})
            response=conn.getresponse();record=json.loads(response.read());conn.close()
            self.assertEqual(response.status,200);self.assertEqual(record['source'],'MOCK');self.assertFalse(record['safety_result']['executable'])
            process.send_signal(signal.SIGINT);output,_=process.communicate(timeout=5);self.assertEqual(process.returncode,0,output)
        finally:
            if process.poll() is None:process.terminate();process.communicate(timeout=5)
