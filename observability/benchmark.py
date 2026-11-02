"""Real local measurements of MOCK work; request concurrency != worker count."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
from InspectionOS.app import Application
from InspectionOS.brain_adapter import BrainAdapter
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill
from InspectionOS.simulation.network_simulator import NetworkSimulator
from observability.metrics import snapshot


def run(output,n=20):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='benchmark-',dir=output))
    runs=[]
    for concurrency in (1,4,8):
        for latency in (0,.005,.02):
            label=f'c{concurrency}-l{latency}'
            with Application(folder/(label+'.db'),network=NetworkSimulator(latency=latency,timeout=.01)) as app:
                s=AlarmQuerySkill();s.spec=replace(s.spec,skill_id='mock.remote',offline_supported=False);app.registry.register(s)
                started=time.perf_counter()
                def submit(i):return app.manager.create('mock.remote',{'device_id':'MOCK-CB-3'},idempotency_key=f'bench-{i}')
                # Submissions run concurrently with the single worker, allowing queue growth.
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures=[pool.submit(submit,i) for i in range(n)]
                    while not all(f.done() for f in futures) or any(m['status']=='QUEUED' for m in app.manager.list()):
                        app.worker.run_once()
                    for f in futures:f.result()
                before={m['status']:sum(x['status']==m['status'] for x in app.manager.list()) for m in app.manager.list()}
                app.network.latency=0
                app.worker.drain(limit=n)
                elapsed=time.perf_counter()-started
                metrics=snapshot(app,elapsed)
                rows=app.db.rows('SELECT * FROM mission_events ORDER BY rowid')
                (folder/(label+'-events.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
                runs.append({'concurrency':concurrency,'workers':1,'network_latency':latency,'n':n,'before_recovery':before,
                             'after_recovery':{m['status']:sum(x['status']==m['status'] for x in app.manager.list()) for m in app.manager.list()},'metrics':metrics})
    with Application(folder/'semantic.db') as app:
        adapter=BrainAdapter(app.manager)
        for i in range(5):adapter.submit_text('查询3号断路器的上周告警。',idempotency_key=f'sem-{i}')
        app.worker.drain()
        semantic_records=adapter.recorder.records
    from tools.brain_smoke import evaluate, summarize
    from brain_v3.config import ProviderConfig
    comparison=[]
    for provider in ('mock','rules'):
        measured=evaluate(ProviderConfig(provider=provider))
        comparison.append({'provider':provider,'is_real_llm':False,'summary':summarize(measured)})
    report={'model_comparison':comparison,'real_model_comparison':None,'is_mock':True,'real_model_tested':False,'asr_tested':False,'runs':runs,'semantic_spans':semantic_records}
    (folder/'measurements.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    from observability.report import charts
    charts(report,folder)
    print(json.dumps({'run':str(folder),'measurements':len(runs),'all_tasks_completed':all(r['after_recovery']=={'SUCCEEDED':n} for r in runs)}))
    return folder


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--tasks',type=int,default=20);a=p.parse_args()
    if a.tasks<1:p.error('tasks must be positive')
    run(a.output,a.tasks)


if __name__=='__main__':main()
