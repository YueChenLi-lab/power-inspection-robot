from dataclasses import replace
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from InspectionOS.app import Application
from InspectionOS.core.skill_registry import SkillRegistry
from InspectionOS.core.state_machine import validate_transition
from InspectionOS.runtime.worker import worker_lock
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill
from InspectionOS.skills.mock.temperature_query import TemperatureQuerySkill
from InspectionOS.skills.mock.reinspection import ReinspectionSkill

PAYLOAD={'device_id':'MOCK-CB-3'}


class Slow(AlarmQuerySkill):
    spec=replace(AlarmQuerySkill.spec,skill_id='mock.slow',timeout=.04)
    def execute(self,payload):time.sleep(.2);return super().execute(payload)


class Bad(AlarmQuerySkill):
    spec=replace(AlarmQuerySkill.spec,skill_id='mock.bad')
    def execute(self,payload):return {'is_mock':False}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'tasks.db'
        self.app=Application(self.path,operator_token='test-only-operator')
    def tearDown(self):self.app.close();self.temp.cleanup()
    def create(self,skill='mock.alarm_query',key='one',**kwargs):
        return self.app.manager.create(skill,PAYLOAD,idempotency_key=key,**kwargs)

    def test_three_skills_and_data_provenance(self):
        for cls in (AlarmQuerySkill,TemperatureQuerySkill,ReinspectionSkill):
            m=self.app.manager.create(cls.spec.skill_id,{**PAYLOAD,'compare':True},idempotency_key=cls.spec.skill_id)
            r=self.app.worker.run_once()
            self.assertEqual(r['status'],'SUCCEEDED');self.assertTrue(r['result']['is_mock'])
            self.assertEqual(r['result']['source'],'mock-fixture-v1')
            self.assertTrue(r['result']['records'])
        self.assertEqual(len(self.app.db.rows('SELECT * FROM skill_executions')),3)
        self.assertEqual(len(self.app.db.rows('SELECT * FROM mission_events')),len(self.app.db.rows('SELECT * FROM outbox_events')))

    def test_priority_fifo_idempotency_and_completed_no_reexecution(self):
        a=self.create(key='a');b=self.create(key='b',priority=5);c=self.create(key='c',priority=5)
        self.assertEqual(self.create(key='a')['mission_id'],a['mission_id'])
        with self.assertRaises(ValueError):self.create(key='a',priority=1)
        self.assertEqual([r['mission_id'] for r in self.app.worker.drain()],[b['mission_id'],c['mission_id'],a['mission_id']])
        self.assertEqual(self.create(key='a')['status'],'SUCCEEDED');self.assertIsNone(self.app.worker.run_once())

    def test_state_machine_and_transaction_rollback(self):
        for before,after in [('CREATED','SUCCEEDED'),('CANCELLED','QUEUED'),('WAITING_APPROVAL','RUNNING')]:
            with self.assertRaises(ValueError):validate_transition(before,after)
        from unittest.mock import patch
        with patch('InspectionOS.storage.repositories.event',side_effect=sqlite3.OperationalError('injected write failure')):
            with self.assertRaises(sqlite3.OperationalError):self.create()
        self.assertEqual(self.app.manager.list(),[])
        self.assertEqual(self.app.db.rows('SELECT * FROM mission_events'),[])
        self.assertEqual(self.app.db.rows('SELECT * FROM outbox_events'),[])

    def test_unknown_and_invalid_contract_rejected(self):
        with self.assertRaises(ValueError):self.create('unregistered')
        with self.assertRaises(ValueError):self.app.manager.create('mock.alarm_query',{'device_id':'3','authorized':True},idempotency_key='bad')
        with self.assertRaises(ValueError):self.app.registry.register(AlarmQuerySkill())
        self.app.registry.register(Bad());self.create('mock.bad',max_attempts=1)
        self.assertEqual(self.app.worker.run_once()['status'],'FAILED')

    def test_independent_approval_and_motion_always_denied(self):
        high=AlarmQuerySkill();high.spec=replace(high.spec,skill_id='mock.high',risk_level='high')
        motion=AlarmQuerySkill();motion.spec=replace(motion.spec,skill_id='mock.motion',risk_level='motion')
        hardware=AlarmQuerySkill();hardware.spec=replace(hardware.spec,skill_id='hardware',execution_scope='hardware')
        for s in (high,motion,hardware):self.app.registry.register(s)
        m=self.create('mock.high');self.assertEqual(m['status'],'WAITING_APPROVAL')
        self.assertIsNone(self.app.worker.run_once())
        with self.assertRaises(PermissionError):self.app.manager.approve(m['mission_id'],actor='llm',token='I approve')
        self.app.manager.approve(m['mission_id'],actor='operator',token='test-only-operator')
        self.assertEqual(self.app.worker.run_once()['status'],'SUCCEEDED')
        self.assertEqual(len(self.app.db.rows('SELECT * FROM approvals')),1)
        for s in ('mock.motion','hardware'):
            self.assertEqual(self.create(s,key=s)['status'],'FAILED')
        self.assertIsNone(self.app.worker.run_once())

    def test_timeout_bounded_retry_and_cancellation(self):
        self.app.registry.register(Slow());m=self.create('mock.slow',max_attempts=2)
        self.assertEqual(self.app.worker.run_once()['status'],'RETRY_WAIT')
        time.sleep(.06)
        r=self.app.worker.run_once();self.assertEqual(r['status'],'FAILED');self.assertEqual(r['attempts'],2)
        m=self.create(key='cancel');self.assertTrue(self.app.manager.cancel(m['mission_id']))
        self.assertIsNone(self.app.worker.run_once());self.assertFalse(self.app.manager.cancel(m['mission_id']))

    def test_nonidempotent_not_retried_and_recovery_review(self):
        skill=Slow();skill.spec=replace(skill.spec,idempotent=False)
        self.app.registry.register(skill);m=self.create('mock.slow')
        self.assertEqual(self.app.worker.run_once()['status'],'FAILED')
        other=self.create('mock.slow',key='uncertain');self.app.scheduler.claim()
        self.app.recovery.recover()
        self.assertEqual(self.app.manager.get(other['mission_id'])['status'],'WAITING_APPROVAL')

    def test_restart_and_exclusive_worker(self):
        m=self.create();self.app.scheduler.claim()
        with worker_lock(self.app.db.path):
            with self.assertRaises(RuntimeError):self.app.recovery.recover()
            with self.assertRaises(RuntimeError):self.app.worker.run_once()
        self.app.close();self.app=Application(self.path)
        self.assertEqual(self.app.recovery.recover(),[m['mission_id']])
        self.assertEqual(self.app.worker.run_once()['status'],'SUCCEEDED')
        self.assertEqual([e['kind'] for e in self.app.manager.events(m['mission_id'])].count('recovered_idempotent'),1)
