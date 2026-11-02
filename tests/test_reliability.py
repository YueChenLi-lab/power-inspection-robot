"""Follow-up contract regressions: shared retry policy, approval and claim races."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from InspectionOS.app import Application
from InspectionOS.runtime.retry_policy import retry_decision
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill
from InspectionOS.simulation.network_simulator import NetworkSimulator
from InspectionOS.storage.repositories import transition

PAYLOAD={'device_id':'MOCK-CB-3'}


class FailureSkill(AlarmQuerySkill):
    def execute(self,payload):raise RuntimeError('deliberate mock failure')


class ReliabilityTests(unittest.TestCase):
    def test_worker_recovery_share_retry_matrix(self):
        cases=[('safe',{},'RETRY_WAIT'),('no-retry',{'retryable':False},'FAILED'),
               ('non-idempotent',{'idempotent':False},'WAITING_APPROVAL'),
               ('unknown-effects',{'recovery_safe':False},'WAITING_APPROVAL'),
               ('exhausted',{},'FAILED'),('changed-version',{},'FAILED'),
               ('unresolved-approval',{'risk_level':'high'},'WAITING_APPROVAL')]
        for name,fields,expected in cases:
            for path in ('worker','recovery'):
                with self.subTest(case=name,path=path),tempfile.TemporaryDirectory() as d,Application(Path(d)/'db',operator_token='test-operator') as app:
                    skill=FailureSkill();skill.spec=replace(skill.spec,**fields)
                    # Registry composition is trusted; register a distinct test capability.
                    skill.spec=replace(skill.spec,skill_id='mock.failure')
                    app.registry.register(skill)
                    m=app.manager.create(skill.spec.skill_id,PAYLOAD,idempotency_key=name,max_attempts=1 if name=='exhausted' else 3)
                    if name=='unresolved-approval':app.manager.approve(m['mission_id'],actor='operator',token='test-operator')
                    if path=='worker':
                        original=app.worker.executor.execute
                        def fail(mission,cancelled):
                            if name=='changed-version':skill.spec=replace(skill.spec,version='2')
                            if name=='unresolved-approval':
                                with app.db.transaction() as c:c.execute('UPDATE missions SET approved=0 WHERE mission_id=?',(mission['mission_id'],))
                            raise RuntimeError('mock failure')
                        app.worker.executor.execute=fail
                        result=app.worker.run_once()
                    else:
                        app.scheduler.claim()
                        if name=='changed-version':skill.spec=replace(skill.spec,version='2')
                        if name=='unresolved-approval':
                            with app.db.transaction() as c:c.execute('UPDATE missions SET approved=0 WHERE mission_id=?',(m['mission_id'],))
                        app.recovery.recover();result=app.manager.get(m['mission_id'])
                    self.assertEqual(result['status'],expected)
                    data=json.loads(app.manager.events(m['mission_id'])[-1]['data'])
                    self.assertIn('retry_reason',data)
                    self.assertEqual(data['retry'],expected=='RETRY_WAIT')

    def test_cancelled_mission_is_not_recovered(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            m=app.manager.create('mock.alarm_query',PAYLOAD,idempotency_key='cancel')
            app.scheduler.claim();app.manager.cancel(m['mission_id'])
            self.assertEqual(app.recovery.recover(),[])
            self.assertEqual(app.manager.get(m['mission_id'])['status'],'CANCELLED')
            self.assertIsNone(app.worker.run_once())

    def test_strict_approval_types_repeated_and_terminal(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db',operator_token='test-operator') as app:
            high=AlarmQuerySkill();high.spec=replace(high.spec,skill_id='mock.high',risk_level='high');app.registry.register(high)
            for allow in (True,False,'false','true',1,None):
                m=app.manager.create('mock.high',PAYLOAD,idempotency_key=repr(allow))
                if type(allow) is bool:
                    app.manager.approve(m['mission_id'],actor='local-label',token='test-operator',allow=allow)
                    self.assertEqual(app.manager.get(m['mission_id'])['status'],'QUEUED' if allow else 'FAILED')
                    with self.assertRaises(ValueError):app.manager.approve(m['mission_id'],actor='local-label',token='test-operator',allow=allow)
                else:
                    before=len(app.manager.events(m['mission_id']))
                    with self.assertRaises(ValueError):app.manager.approve(m['mission_id'],actor='local-label',token='test-operator',allow=allow)
                    self.assertEqual(app.manager.get(m['mission_id'])['status'],'WAITING_APPROVAL')
                    self.assertEqual(len(app.manager.events(m['mission_id'])),before)
            for actor,token in [('', 'test-operator'),(' ', 'test-operator'),(2,'test-operator'),('x','')]:
                m=app.manager.create('mock.high',PAYLOAD,idempotency_key=repr((actor,token)))
                with self.assertRaises(PermissionError):app.manager.approve(m['mission_id'],actor=actor,token=token)
                self.assertEqual(app.manager.events(m['mission_id'])[-1]['kind'],'approval_authentication_rejected')
            m=app.manager.create('mock.high',PAYLOAD,idempotency_key='cancelled');app.manager.cancel(m['mission_id'])
            with self.assertRaises(ValueError):app.manager.approve(m['mission_id'],actor='x',token='test-operator')


class BlockingNetwork(NetworkSimulator):
    def __init__(self,participants=1):
        super().__init__();self.entered=threading.Event();self.release=threading.Event()
        self.barrier=threading.Barrier(participants);self.durations=[]
    def request(self,operation):
        start=time.perf_counter();self.entered.set();self.barrier.wait(timeout=3)
        if not self.release.wait(3):raise AssertionError('test must release network')
        self.durations.append(time.perf_counter()-start)
        return {'is_mock':True}


def scheduler_experiment(directory):
    """Measured lock-decoupling proof: another SQLite connection writes before release."""
    net=BlockingNetwork()
    with Application(Path(directory)/'db',network=net) as app,Application(Path(directory)/'db') as submitter:
        skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote',offline_supported=False);app.registry.register(skill)
        m=app.manager.create(skill.spec.skill_id,PAYLOAD,idempotency_key='remote')
        claims=[];errors=[]
        def claim():
            try:claims.append(app.scheduler.claim())
            except BaseException as exc:errors.append(repr(exc))
        worker=threading.Thread(target=claim);worker.start()
        if not net.entered.wait(2):raise AssertionError('preflight not entered')
        transaction_open=app.db.connection.in_transaction
        started=time.perf_counter()
        submitted=submitter.manager.create('mock.alarm_query',PAYLOAD,idempotency_key='while-waiting')
        submit_seconds=time.perf_counter()-started
        app.manager.cancel(m['mission_id'])
        still_blocked=worker.is_alive()
        net.release.set();worker.join(3)
        result={'network_wait_seconds':net.durations,'database_transaction_seconds':app.db.write_seconds,
                'submission_seconds':submit_seconds,'transaction_open_during_preflight':transaction_open,
                'submitted_before_network_release':still_blocked,'errors':errors,
                'cancelled_status':app.manager.get(m['mission_id'])['status'],
                'original_mission_claim_count':sum(r is not None and r['mission_id']==m['mission_id'] for r in claims)}
        assert not transaction_open and still_blocked and not errors and result['original_mission_claim_count']==0
        return result


class SchedulerTests(unittest.TestCase):
    def test_network_does_not_block_new_connection_writes_or_cancellation(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(scheduler_experiment(d)['cancelled_status'],'CANCELLED')

    def test_simultaneous_claim_no_duplicate(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db',network=BlockingNetwork(2)) as app:
            skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote',offline_supported=False);app.registry.register(skill)
            app.manager.create(skill.spec.skill_id,PAYLOAD,idempotency_key='one')
            claims=[];errors=[]
            def claim():
                try:claims.append(app.scheduler.claim())
                except BaseException as e:errors.append(repr(e))
            threads=[threading.Thread(target=claim) for _ in range(2)]
            for t in threads:t.start()
            self.assertTrue(app.network.entered.wait(2));app.network.release.set()
            for t in threads:t.join(3)
            self.assertEqual(errors,[]);self.assertEqual(sum(c is not None for c in claims),1)
            self.assertEqual(len(app.db.rows('SELECT * FROM skill_executions')),1)

    def test_approval_revoked_during_preflight_never_claims(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db',network=BlockingNetwork(),operator_token='test-operator') as app:
            skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote-high',risk_level='high',offline_supported=False);app.registry.register(skill)
            m=app.manager.create(skill.spec.skill_id,PAYLOAD,idempotency_key='high')
            app.manager.approve(m['mission_id'],actor='operator',token='test-operator')
            results=[];thread=threading.Thread(target=lambda:results.append(app.scheduler.claim()));thread.start()
            self.assertTrue(app.network.entered.wait(2))
            app.manager.revoke_approval(m['mission_id'],actor='operator',token='test-operator')
            app.network.release.set();thread.join(3)
            self.assertEqual(results,[None]);self.assertEqual(app.manager.get(m['mission_id'])['status'],'WAITING_APPROVAL')
