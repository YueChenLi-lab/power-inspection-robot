"""Invented fixtures, never field evidence. Dates fixed for reproducible examples."""
from datetime import datetime
from .validation import SOURCE, device_set, query_window

ALARMS = [{'device_id':'MOCK-CB-3','timestamp':'2026-10-27T09:00:00+08:00','code':'MOCK-ALARM'},
          {'device_id':'MOCK-TR-1','timestamp':'2026-10-28T10:00:00+08:00','code':'MOCK-REVIEW'}]
TEMPERATURES = [{'device_id':d,'timestamp':t,'temperature_c':v}
                for d in ('MOCK-CB-3','MOCK-TR-1')
                for t,v in [('2026-10-27T09:00:00+08:00',41.0),('2026-10-30T09:00:00+08:00',43.5)]]


def select(rows,payload):
    start,end=query_window(payload)
    ids=device_set(payload)
    return [{**r,'is_mock':True,'source':SOURCE} for r in rows if r['device_id'] in ids and
            (not start or datetime.fromisoformat(r['timestamp'])>=start) and
            (not end or datetime.fromisoformat(r['timestamp'])<end)]



def output(payload,records,summary):
    identity={'device_id':payload['device_id']} if 'device_id' in payload else {'device_ids':list(payload['device_ids'])}
    return {'is_mock':True,'source':SOURCE,**identity,'records':records,'summary':summary}
