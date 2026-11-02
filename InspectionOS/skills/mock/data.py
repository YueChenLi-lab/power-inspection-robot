"""Invented fixtures, never field evidence. Dates fixed for reproducible examples."""
from datetime import datetime

ALARMS = [{'device_id':'MOCK-CB-3','timestamp':'2026-10-27T09:00:00+08:00','code':'MOCK-ALARM'},
          {'device_id':'MOCK-TR-1','timestamp':'2026-10-28T10:00:00+08:00','code':'MOCK-REVIEW'}]
TEMPERATURES = [{'device_id':d,'timestamp':t,'temperature_c':v}
                for d in ('MOCK-CB-3','MOCK-TR-1')
                for t,v in [('2026-10-27T09:00:00+08:00',41.0),('2026-10-30T09:00:00+08:00',43.5)]]


def select(rows,payload):
    start=datetime.fromisoformat(payload['start']) if payload.get('start') else None
    end=datetime.fromisoformat(payload['end']) if payload.get('end') else None
    if start and start.tzinfo is None or end and end.tzinfo is None: raise ValueError('time bounds require timezone')
    if start and end and start>=end: raise ValueError('invalid time interval')
    return [dict(r) for r in rows if r['device_id']==payload['device_id'] and
            (not start or datetime.fromisoformat(r['timestamp'])>=start) and
            (not end or datetime.fromisoformat(r['timestamp'])<end)]


def output(payload,records,summary):
    return {'is_mock':True,'source':'mock-fixture-v1','device_id':payload['device_id'],'records':records,'summary':summary}
