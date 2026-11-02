"""Nearest-rank percentiles; no observations -> null, never an invented zero."""
import math


def distribution(values):
    values=sorted(values)
    if not values:return {'count':0,'mean':None,'p50':None,'p95':None,'p99':None}
    return {'count':len(values),'mean':sum(values)/len(values),
            **{name:values[max(0,math.ceil(p*len(values))-1)] for name,p in [('p50',.5),('p95',.95),('p99',.99)]}}


def snapshot(app,elapsed):
    missions=app.manager.list()
    executions=app.db.rows('SELECT * FROM skill_executions')
    events=app.db.rows('SELECT * FROM mission_events')
    import json
    queue=[json.loads(e['data'])['queue_seconds'] for e in events if e['after_state']=='RUNNING']
    completed=[m for m in missions if m['status'] in ('SUCCEEDED','FAILED','CANCELLED')]
    failed=sum(m['status']=='FAILED' for m in completed)
    durations=[e['duration'] for e in executions if e['duration'] is not None]
    network=app.network.records
    return {'mission_latency_seconds':distribution([m['updated_at']-m['created_at'] for m in completed]),
            'queue_seconds':distribution(queue),'skill_seconds':distribution(durations),
            'storage_read_seconds':distribution(app.db.read_seconds),
            'storage_write_seconds':distribution(app.db.write_seconds),
            'network_seconds':distribution([r['duration'] for r in network]),
            'throughput_per_second':len(completed)/elapsed if elapsed else None,
            'failed_tasks':failed,'terminal_tasks':len(completed),
            'failure_rate':failed/len(completed) if completed else None,
            'retry_count':sum(max(0,m['attempts']-1) for m in missions),
            'worker_utilization':sum(durations)/elapsed if elapsed else None,
            'network_timeout_rate':sum(r['timeout'] for r in network)/len(network) if network else None,
            'outbox_backlog':app.db.rows("SELECT count(*) n FROM outbox_events WHERE status='PENDING'")[0]['n'],
            'unconnected_stages':{'asr':None,'real_qwen3':None},
            'observation_seconds':elapsed}
