"""Explicit restart recovery under the same exclusive worker lock."""
import time
from InspectionOS.storage.repositories import transition
from .worker import worker_lock


class Recovery:
    def __init__(self,manager): self.manager=manager

    def recover(self):
        recovered=[]
        with worker_lock(self.manager.db.path), self.manager.db.transaction() as c:
            rows=c.execute("SELECT * FROM missions WHERE status IN ('RUNNING','CREATED','VALIDATING')").fetchall()
            for row in rows:
                mid=row['mission_id']
                if row['status'] in ('CREATED','VALIDATING'):
                    if row['status']=='CREATED': transition(c,mid,'VALIDATING',kind='recovery_validation')
                    transition(c,mid,'FAILED',kind='recovery_rejected',error='interrupted validation; submit a new request')
                else:
                    try: spec=self.manager.registry.get(row['skill_id']).spec
                    except ValueError: spec=None
                    if spec and spec.idempotent and spec.version==row['skill_version'] and row['attempts']<row['max_attempts']:
                        transition(c,mid,'RETRY_WAIT',kind='recovered_idempotent',retry_at=0,error='worker exit; result unknown')
                    elif spec and not spec.idempotent:
                        transition(c,mid,'WAITING_APPROVAL',kind='recovery_manual_review',approved=0,error='non-idempotent result unknown; review required')
                    else:
                        transition(c,mid,'FAILED',kind='recovery_exhausted',error='retry budget exhausted or skill unavailable')
                    c.execute("UPDATE skill_executions SET status='UNKNOWN',finished_at=?,error='worker exit; result unknown' WHERE mission_id=? AND status='RUNNING'",(time.time(),mid))
                recovered.append(mid)
        return recovered
