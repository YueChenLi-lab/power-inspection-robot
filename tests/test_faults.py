from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from InspectionOS.app import Application
from InspectionOS.simulation.network_simulator import NetworkSimulator
from InspectionOS.simulation.scenario_runner import run_scenario
from InspectionOS.simulation.fault_injector import storage_failure, restore_storage
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill


class FaultTests(unittest.TestCase):
    def test_e1_e7(self):
        for i in range(1,8):
            with self.subTest(experiment=i),tempfile.TemporaryDirectory() as d:
                r=run_scenario('E'+str(i),d);self.assertTrue(r['passed'],r)

    def test_loss_sequence_reproducible_and_network_restore(self):
        a=NetworkSimulator(seed=3,loss=.4);b=NetworkSimulator(seed=3,loss=.4)
        for net in (a,b):
            for _ in range(10):
                try:net.request('x')
                except ConnectionError:pass
        self.assertEqual([r['error'] for r in a.records],[r['error'] for r in b.records])
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'local.db',network=NetworkSimulator(online=False)) as app:
            skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote',offline_supported=False)
            app.registry.register(skill)
            m=app.manager.create('mock.remote',{'device_id':'MOCK-CB-3'},idempotency_key='r')
            self.assertIsNone(app.worker.run_once());self.assertEqual(app.manager.get(m['mission_id'])['status'],'WAITING_NETWORK')
            app.network.online=True
            self.assertEqual(app.worker.run_once()['status'],'SUCCEEDED')

    def test_real_sqlite_failure_is_not_success_and_resumes(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            storage_failure(app.db)
            with self.assertRaises(sqlite3.OperationalError):app.manager.create('mock.alarm_query',{'device_id':'MOCK-CB-3'},idempotency_key='fail')
            self.assertEqual(app.manager.list(),[])
            restore_storage(app.db)
            m=app.manager.create('mock.alarm_query',{'device_id':'MOCK-CB-3'},idempotency_key='ok')
            storage_failure(app.db)
            with self.assertRaises(sqlite3.OperationalError):app.worker.run_once()
            restore_storage(app.db)
            self.assertEqual(app.manager.get(m['mission_id'])['status'],'QUEUED')
            self.assertEqual(app.worker.run_once()['status'],'SUCCEEDED')
