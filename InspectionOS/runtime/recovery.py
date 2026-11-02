"""Explicit restart recovery under the same exclusive worker lock."""
import time
from InspectionOS.storage.repositories import transition
from .worker import worker_lock
from .retry_policy import retry_decision


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
                    policy=retry_decision(spec,row,self.manager.safety)
                    target='RETRY_WAIT' if policy.allowed else ('WAITING_APPROVAL' if policy.needs_review else 'FAILED')
                    kind='recovered_idempotent' if policy.allowed else ('recovery_manual_review' if policy.needs_review else 'recovery_rejected')
                    transition(c,mid,target,kind=kind,retry_at=0,
                               approved=0 if policy.needs_review else row['approved'],
                               error='worker exit; result unknown; '+policy.reason,
                               data={'retry':policy.allowed,'retry_reason':policy.reason,'result_uncertain':True})
                    c.execute("UPDATE skill_executions SET status='UNKNOWN',finished_at=?,error='worker exit; result unknown' WHERE mission_id=? AND status='RUNNING'",(time.time(),mid))
                recovered.append(mid)
        return recovered
