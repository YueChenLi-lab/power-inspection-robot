"""Single-worker priority/FIFO scheduler; claims and execution-start are atomic."""
import time
import uuid
from InspectionOS.storage.repositories import decode, transition


class Scheduler:
    def __init__(self, manager, network): self.manager,self.network=manager,network

    def claim(self):
        db=self.manager.db
        with db.transaction() as c:
            for row in c.execute("SELECT * FROM missions WHERE status IN ('RETRY_WAIT','WAITING_NETWORK') ORDER BY created_at").fetchall():
                if row['status']=='RETRY_WAIT' and row['retry_at']<=time.time() or row['status']=='WAITING_NETWORK' and self.network.online:
                    transition(c,row['mission_id'],'QUEUED',kind='rescheduled')
            rows=c.execute("SELECT * FROM missions WHERE status='QUEUED' ORDER BY priority DESC,created_at,rowid").fetchall()
            for row in rows:
                mission=decode(row)
                spec=self.manager.registry.get(row['skill_id']).spec
                if row['skill_version'] != spec.version:
                    transition(c,row['mission_id'],'FAILED',error='registered version changed');continue
                decision=self.manager.safety.decision(spec,approved=bool(row['approved']))
                if decision!='ALLOW':
                    transition(c,row['mission_id'],'WAITING_APPROVAL' if decision=='APPROVAL' else 'FAILED',error='execution policy denied');continue
                if not spec.offline_supported or spec.requires_network_authorization:
                    try: self.network.request('task-prerequisite')
                    except ConnectionError as exc:
                        transition(c,row['mission_id'],'WAITING_NETWORK',kind='network_wait',data={'reason':str(exc)})
                        continue
                # A policy check is not a network authorization service. Configured
                # network authorization requires separately issued approval as well.
                if spec.requires_network_authorization and not row['approved']:
                    transition(c,row['mission_id'],'WAITING_APPROVAL',kind='network_authorization_required');continue
                transition(c,row['mission_id'],'RUNNING',attempts=row['attempts']+1,
                           data={'queue_seconds':max(0,time.time()-row['updated_at'])})
                execution=uuid.uuid4().hex
                c.execute('INSERT INTO skill_executions(execution_id,mission_id,skill_id,skill_version,attempt,status,started_at) VALUES (?,?,?,?,?,?,?)',
                          (execution,row['mission_id'],spec.skill_id,spec.version,row['attempts']+1,'RUNNING',time.time()))
                mission.update(status='RUNNING',attempts=row['attempts']+1,execution_id=execution)
                return mission
        return None
