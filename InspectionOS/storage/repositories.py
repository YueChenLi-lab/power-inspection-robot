"""SQL persistence helpers; caller owns transaction boundaries."""
import hashlib
import json
import logging
import time
import uuid
from InspectionOS.core.state_machine import validate_transition

LOG = logging.getLogger(__name__)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def decode(row):
    row = dict(row)
    for key in ('payload', 'result'):
        row[key] = json.loads(row[key]) if row[key] is not None else None
    return row


def event(c, mission, kind, before=None, after=None, data=None):
    eid = uuid.uuid4().hex
    row = dict(event_id=eid, mission_id=mission['mission_id'], trace_id=mission['trace_id'],
               correlation_id=mission['correlation_id'], skill_id=mission['skill_id'], kind=kind,
               before_state=before, after_state=after, data=data or {}, created_at=time.time())
    c.execute('INSERT INTO mission_events VALUES (?,?,?,?,?,?,?,?,?,?)',
              tuple(row[k] if k != 'data' else encode(row[k]) for k in row))
    c.execute('INSERT INTO outbox_events(event_id,payload) VALUES (?,?)',(eid,encode(row)))
    LOG.info('mission_event %s',encode(row))
    return row


def transition(c, mid, after, *, kind='state_change', data=None, **updates):
    current = c.execute('SELECT * FROM missions WHERE mission_id=?',(mid,)).fetchone()
    if current is None: raise KeyError(mid)
    current = dict(current)
    validate_transition(current['status'], after)
    allowed = {'result','error','attempts','retry_at','approved'}
    if not updates.keys() <= allowed: raise ValueError('unsupported persisted field')
    updates.update(status=str(after.value if hasattr(after,'value') else after), updated_at=time.time())
    c.execute('UPDATE missions SET '+','.join(k+'=?' for k in updates)+' WHERE mission_id=?',
              (*updates.values(),mid))
    event(c,current,kind,current['status'],updates['status'],data)
    return mid
