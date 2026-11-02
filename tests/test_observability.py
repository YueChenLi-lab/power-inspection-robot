import tempfile
from pathlib import Path
import unittest
from InspectionOS.app import Application
from InspectionOS.brain_adapter import BrainAdapter
from observability.metrics import distribution,snapshot
from observability.tracing import export_trace


class ObservabilityTests(unittest.TestCase):
    def test_percentiles_and_missing_measurements(self):
        self.assertIsNone(distribution([])['mean'])
        self.assertEqual(distribution(range(1,101))['p95'],95)
        self.assertEqual(distribution([1,2,3])['p99'],3)

    def test_brain_end_to_end_trace_persistence(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            adapter=BrainAdapter(app.manager)
            mission=adapter.submit_text('查询3号断路器的上周告警。',idempotency_key='query')
            app.worker.drain()
            completed=app.manager.get(mission['mission_id'])
            self.assertEqual(completed['status'],'SUCCEEDED')
            self.assertEqual(len(completed['result']['records']),1)
            events=export_trace(app.db,mission['trace_id'])
            self.assertTrue(events)
            for e in events:
                self.assertEqual(e['mission_id'],mission['mission_id']);self.assertEqual(e['correlation_id'],mission['correlation_id'])
                self.assertEqual(e['skill_id'],'mock.alarm_query')
            metrics=snapshot(app,1)
            self.assertEqual(metrics['terminal_tasks'],1);self.assertIsNone(metrics['unconnected_stages']['asr'])
            self.assertTrue(adapter.recorder.records)

    def test_adapter_rejects_motion_ambiguity_and_forgery(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            adapter=BrainAdapter(app.manager)
            for text in ('前进3米','查询3号断路器最近的告警','查询3号断路器告警并启动机器人','查询2号断路器上周告警'):
                with self.subTest(text=text),self.assertRaises((ValueError,PermissionError)):
                    adapter.submit_text(text,idempotency_key=text)
            result=adapter.engine.analyze('查询3号断路器上周告警')
            result['structured_task_draft']['authorized']=True
            with self.assertRaises(PermissionError):adapter.submit_result(result,idempotency_key='fake')
