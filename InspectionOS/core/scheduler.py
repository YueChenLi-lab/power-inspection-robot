"""Priority/FIFO candidate snapshot, external preflight, then atomic fresh claim.

No network operation holds SQLite's BEGIN IMMEDIATE write lock. A fresh state,
revision, version and policy check prevents stale preflight results from claiming
cancelled/reviewed tasks. This is still one execution Worker, not a lease system.
"""
import time
import uuid
from InspectionOS.storage.repositories import decode, transition
from InspectionOS.runtime.retry_policy import retry_decision


class Scheduler:
    def __init__(self, manager, network):
        self.manager, self.network = manager, network

    def claim(self):
        db = self.manager.db
        # Phase 1: short preparation transaction; materialize candidate rows.
        with db.transaction() as c:
            for row in c.execute("SELECT * FROM missions WHERE status IN ('RETRY_WAIT','WAITING_NETWORK') ORDER BY created_at").fetchall():
                ready = (row['status'] == 'RETRY_WAIT' and row['retry_at'] <= time.time())
                if ready:
                    try: retry_spec=self.manager.registry.get(row['skill_id']).spec
                    except ValueError: retry_spec=None
                    policy=retry_decision(retry_spec,row,self.manager.safety)
                    if not policy.allowed:
                        transition(c,row['mission_id'],'WAITING_APPROVAL' if policy.needs_review else 'FAILED',
                                   kind='retry_revalidation_rejected',error=policy.reason,
                                   approved=0 if policy.needs_review else row['approved'],data={'retry_reason':policy.reason})
                        continue
                if ready or (row['status'] == 'WAITING_NETWORK' and self.network.online):
                    transition(c, row['mission_id'], 'QUEUED', kind='rescheduled')
            candidates = [dict(r) for r in c.execute(
                "SELECT * FROM missions WHERE status='QUEUED' ORDER BY priority DESC,created_at,rowid").fetchall()]

        for candidate in candidates:
            try:
                spec = self.manager.registry.get(candidate['skill_id']).spec
            except ValueError:
                spec = None
            needs_network = spec is not None and (not spec.offline_supported or spec.requires_network_authorization)
            network_error = None
            # Phase 2: no transaction and no connection mutex held here.
            if needs_network:
                try:
                    self.network.request('task-prerequisite')
                except ConnectionError as exc:
                    network_error = str(exc)

            # Phase 3: re-read; never claim using only the earlier snapshot.
            with db.transaction() as c:
                current = c.execute('SELECT * FROM missions WHERE mission_id=?', (candidate['mission_id'],)).fetchone()
                if current is None or current['status'] != 'QUEUED' or current['updated_at'] != candidate['updated_at']:
                    continue
                try:
                    actual_spec = self.manager.registry.get(current['skill_id']).spec
                except ValueError:
                    actual_spec = None
                if actual_spec is None or actual_spec != spec or current['skill_version'] != actual_spec.version:
                    transition(c, current['mission_id'], 'FAILED', error='registered skill unavailable or changed')
                    continue
                decision = self.manager.safety.decision(actual_spec, approved=current['approved'] == 1)
                if decision != 'ALLOW':
                    transition(c, current['mission_id'], 'WAITING_APPROVAL' if decision == 'APPROVAL' else 'FAILED', error='execution policy denied')
                    continue
                if network_error is not None:
                    transition(c, current['mission_id'], 'WAITING_NETWORK', kind='network_wait', data={'reason': network_error})
                    continue
                if actual_spec.requires_network_authorization and current['approved'] != 1:
                    transition(c, current['mission_id'], 'WAITING_APPROVAL', kind='network_authorization_required')
                    continue
                transition(c, current['mission_id'], 'RUNNING', attempts=current['attempts'] + 1,
                           data={'queue_seconds': max(0, time.time()-current['updated_at'])})
                execution = uuid.uuid4().hex
                c.execute('INSERT INTO skill_executions(execution_id,mission_id,skill_id,skill_version,attempt,status,started_at) VALUES (?,?,?,?,?,?,?)',
                          (execution, current['mission_id'], actual_spec.skill_id, actual_spec.version, current['attempts']+1, 'RUNNING', time.time()))
                mission = decode(current)
                mission.update(status='RUNNING', attempts=current['attempts']+1, execution_id=execution)
                return mission
        return None
