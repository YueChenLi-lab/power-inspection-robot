"""E1–E7 reproducible fault lab, with actual outcomes and durable raw events."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from InspectionOS.app import Application
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill
from InspectionOS.simulation.network_simulator import NetworkSimulator
from InspectionOS.storage.database import CapacityError
from data_pipeline.sync_manager import MockRemote, SyncManager

PAYLOAD={'device_id':'MOCK-CB-3'}


def run_scenario(number,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    db=folder/'local.db'
    net=NetworkSimulator(seed=11)
    app=Application(db,network=net)
    remote=MockRemote(str(folder/'remote.db'))
    conditions={};expected='';steps=[]
    def create(key,skill='mock.alarm_query'):
        return app.manager.create(skill,PAYLOAD,idempotency_key=key)
    try:
        if number=='E1':
            conditions={'latency':.02,'timeout':.01,'seed':11}
            net.latency=.02;net.timeout=.01
            skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote',offline_supported=False)
            app.registry.register(skill)
            m=create('latency','mock.remote');app.worker.run_once()
            actual=app.manager.get(m['mission_id'])['status'];expected='WAITING_NETWORK'
            steps=['Register simulated remote-dependent skill','Inject latency above timeout','Run worker']
            passed=actual==expected and net.records[-1]['timeout']
        elif number=='E2':
            net.online=False;conditions={'online':False}
            skill=AlarmQuerySkill();skill.spec=replace(skill.spec,skill_id='mock.remote',offline_supported=False)
            app.registry.register(skill)
            local=create('local');cloud=create('cloud','mock.remote');app.worker.drain()
            actual={m['idempotency_key']:m['status'] for m in app.manager.list()};expected={'local':'SUCCEEDED','cloud':'WAITING_NETWORK'}
            steps=['Disconnect simulated network','Submit local and remote tasks','Drain available work']
            passed=actual==expected
        elif number=='E3':
            net.online=False;conditions={'disconnect_then_recover':True,'ack_loss':True}
            create('buffered');app.worker.drain()
            sync=SyncManager(app.db,net,remote);offline=sync.sync()
            net.online=True;remote.fail_after_commit=True;lost_ack=sync.sync()
            remote.fail_after_commit=False;recovered=sync.sync()
            actual={'offline':offline,'lost_ack':lost_ack,'recovered':recovered,'receiver_unique_events':remote.count()}
            expected='No loss; pending=0; receiver count equals local event count after ACK-loss retry'
            steps=['Complete local task offline','Fail sync','Restore network with ACK loss','Retry sync with same event IDs']
            passed=recovered['pending']==0 and remote.count()==len(app.db.rows('SELECT * FROM mission_events')) and offline['failed']>0
        elif number=='E4':
            conditions={'duplicate_submissions':2}
            a=create('same');b=create('same');app.worker.drain();create('same');app.worker.drain()
            actual={'same_id':a['mission_id']==b['mission_id'],'missions':len(app.manager.list()),'executions':len(app.db.rows('SELECT * FROM skill_executions'))}
            expected={'same_id':True,'missions':1,'executions':1};passed=actual==expected
            steps=['Submit same key twice','Complete','Resubmit completed key']
        elif number in ('E5','E6'):
            conditions={'process_exit':'SIGKILL inside mock Skill' if number=='E6' else 'worker object discarded after durable claim'}
            if number=='E6':
                from .fault_injector import CrashDuringSkill
                app.registry.register(CrashDuringSkill())
            m=create('crash','mock.crash' if number=='E6' else 'mock.alarm_query')
            if number=='E6':
                script='from InspectionOS.app import Application; from InspectionOS.simulation.fault_injector import CrashDuringSkill; a=Application(__import__("sys").argv[1]); a.registry.register(CrashDuringSkill()); a.worker.run_once()'
                run=subprocess.run([sys.executable,'-c',script,str(db)],capture_output=True,text=True)
                if run.returncode!=-9:raise RuntimeError(run.stderr)
            else:app.scheduler.claim()
            app.close();app=Application(db,network=net)
            if number=='E6':
                safe=AlarmQuerySkill();safe.spec=replace(safe.spec,skill_id='mock.crash');app.registry.register(safe)
            recovered=app.recovery.recover();app.worker.drain()
            actual={'recovered':len(recovered),'status':app.manager.get(m['mission_id'])['status'],
                    'execution_statuses':[e['status'] for e in app.db.rows('SELECT status FROM skill_executions ORDER BY rowid')]}
            expected={'recovered':1,'status':'SUCCEEDED','execution_statuses':['UNKNOWN','SUCCEEDED']}
            steps=['Persist RUNNING and execution-start','Exit unexpectedly','Reopen database','Explicit recovery under lock','Drain']
            passed=actual==expected
        elif number=='E7':
            conditions={'max_missions':1,'policy':'admission cap; protect audit, not fill disk'};app.db.max_missions=1
            create('first');app.worker.drain();before=len(app.db.rows('SELECT * FROM mission_events'))
            try:create('over-cap');blocked=False
            except CapacityError:blocked=True
            actual={'blocked':blocked,'audit_retained':len(app.db.rows('SELECT * FROM mission_events'))==before,'missions':len(app.manager.list())}
            expected={'blocked':True,'audit_retained':True,'missions':1};passed=actual==expected
            steps=['Set deterministic mission capacity','Complete first mission','Attempt second admission','Verify evidence retained']
        else:raise ValueError(number)
        events=app.db.rows('SELECT * FROM mission_events ORDER BY rowid')
        (folder/'events.jsonl').write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events))
        (folder/'network.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in net.records))
        report={'experiment':number,'conditions':conditions,'steps':steps,'expected':expected,'actual':actual,'passed':bool(passed),
                'raw_logs':['events.jsonl','network.jsonl'],'is_mock':True}
        (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        return report
    finally:app.close();remote.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    # Each invocation gets a fresh run, never mixes old DB state into results.
    a.output.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='fault-run-',dir=a.output))
    results=[run_scenario('E'+str(i),folder/('E'+str(i))) for i in range(1,8)]
    (folder/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps({'run':str(folder),'passed':sum(r['passed'] for r in results),'total':len(results)}))
    return 0 if all(r['passed'] for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
