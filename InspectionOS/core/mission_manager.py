import time
import uuid
from InspectionOS.storage.database import CapacityError
from InspectionOS.storage.repositories import decode, encode, event, fingerprint, transition
from .state_machine import TERMINAL, State


class MissionManager:
    def __init__(self, db, registry, safety): self.db,self.registry,self.safety=db,registry,safety

    def create(self, skill_id, payload, *, idempotency_key, source='local-api', priority=0,
               trace_id=None, correlation_id=None, max_attempts=3):
        if not isinstance(idempotency_key,str) or not idempotency_key: raise ValueError('idempotency key required')
        if type(priority) is not int or type(max_attempts) is not int or not 1<=max_attempts<=5: raise ValueError('invalid scheduling policy')
        spec=self.registry.get(skill_id).spec
        self.registry.validate_input(skill_id,payload)
        key=fingerprint({'skill_id':skill_id,'version':spec.version,'payload':payload,'priority':priority,'max_attempts':max_attempts})
        with self.db.transaction() as c:
            prior=c.execute('SELECT * FROM missions WHERE idempotency_key=?',(idempotency_key,)).fetchone()
            if prior:
                if prior['fingerprint']!=key: raise ValueError('idempotency key reused with different request')
                return decode(prior)
            self.db.check_capacity(c,len(encode(payload).encode()))
            if c.execute('SELECT count(*) FROM missions').fetchone()[0]>=self.db.max_missions:
                raise CapacityError('mission admission limit; existing audit retained')
            now=time.time()
            row=dict(mission_id=uuid.uuid4().hex,trace_id=trace_id or uuid.uuid4().hex,
                     correlation_id=correlation_id or uuid.uuid4().hex,skill_id=skill_id,mission_type=skill_id,
                     payload=encode(payload),status='CREATED',priority=priority,created_at=now,updated_at=now,
                     idempotency_key=idempotency_key,source=source,max_attempts=max_attempts,skill_version=spec.version,fingerprint=key)
            c.execute('INSERT INTO missions ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
            event(c,row,'created',after='CREATED')
            transition(c,row['mission_id'],'VALIDATING')
            decision=self.safety.decision(spec)
            target={'ALLOW':'QUEUED','APPROVAL':'WAITING_APPROVAL','DENY':'FAILED'}[decision]
            transition(c,row['mission_id'],target,error='policy denied' if decision=='DENY' else None)
        return self.get(row['mission_id'])

    def get(self, mid):
        rows=self.db.rows('SELECT * FROM missions WHERE mission_id=?',(mid,))
        if not rows: raise KeyError(mid)
        return decode(rows[0])

    def list(self): return [decode(r) for r in self.db.rows('SELECT * FROM missions ORDER BY created_at, rowid')]
    def events(self, mid): return self.db.rows('SELECT * FROM mission_events WHERE mission_id=? ORDER BY created_at,rowid',(mid,))

    def cancel(self, mid):
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM missions WHERE mission_id=?',(mid,)).fetchone()
            if row is None: raise KeyError(mid)
            if State(row['status']) in TERMINAL: return False
            transition(c,mid,'CANCELLED',kind='cancelled')
            return True

    def approve(self, mid, *, actor, token, allow=True):
        if type(allow) is not bool:
            raise ValueError('allow must be bool')
        try:
            self.safety.authenticate_operator(actor,token)
        except PermissionError:
            with self.db.transaction() as c:
                row=c.execute('SELECT * FROM missions WHERE mission_id=?',(mid,)).fetchone()
                if row:
                    c.execute('INSERT INTO approvals VALUES (?,?,?,?,?)',(uuid.uuid4().hex,mid,'unauthenticated','rejected',time.time()))
                    event(c,row,'approval_authentication_rejected')
            raise
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM missions WHERE mission_id=?',(mid,)).fetchone()
            if row is None: raise KeyError(mid)
            if row['status']!='WAITING_APPROVAL': raise ValueError('mission not awaiting independent review')
            spec=self.registry.get(row['skill_id']).spec
            decision=self.safety.decision(spec,approved=True)
            c.execute('INSERT INTO approvals VALUES (?,?,?,?,?)',(uuid.uuid4().hex,mid,actor,'allow' if allow else 'deny',time.time()))
            transition(c,mid,'QUEUED' if allow and decision=='ALLOW' else 'FAILED',kind='operator_review',
                       data={'actor':actor,'allow':allow},approved=int(allow and decision=='ALLOW'))
        return self.get(mid)

    def revoke_approval(self, mid, *, actor, token):
        """Local operator can revoke queued/waiting authorization, never a running side effect."""
        self.safety.authenticate_operator(actor, token)
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM missions WHERE mission_id=?',(mid,)).fetchone()
            if row is None: raise KeyError(mid)
            if row['status'] not in ('QUEUED','WAITING_NETWORK','RETRY_WAIT'):
                raise ValueError('only pending missions can have approval revoked')
            c.execute('INSERT INTO approvals VALUES (?,?,?,?,?)',(uuid.uuid4().hex,mid,actor,'revoked',time.time()))
            transition(c,mid,'WAITING_APPROVAL',kind='approval_revoked',approved=0,data={'actor':actor})
        return self.get(mid)
