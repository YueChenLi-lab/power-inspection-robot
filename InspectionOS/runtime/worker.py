"""One worker per DB enforced by an OS lock; no business logic here."""
from contextlib import contextmanager
import fcntl
import time
from InspectionOS.storage.repositories import encode, transition
from .executor import Executor, ExecutionCancelled


@contextmanager
def worker_lock(path):
    with open(str(path)+'.worker.lock','a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('another worker/recovery holds this database') from None
        try: yield
        finally: fcntl.flock(handle,fcntl.LOCK_UN)


class Worker:
    def __init__(self,manager,scheduler):
        self.manager,self.scheduler=manager,scheduler
        self.executor=Executor(manager.registry)

    def run_once(self):
        with worker_lock(self.manager.db.path): return self._run_once()

    def _run_once(self):
        mission=self.scheduler.claim()
        if mission is None: return None
        started=time.perf_counter()
        try:
            result=self.executor.execute(mission,lambda:self.manager.get(mission['mission_id'])['status']=='CANCELLED')
            error=None
        except Exception as exc:
            result=None;error=type(exc).__name__+': '+str(exc)
        duration=time.perf_counter()-started
        spec=self.manager.registry.get(mission['skill_id']).spec
        with self.manager.db.transaction() as c:
            current=c.execute('SELECT * FROM missions WHERE mission_id=?',(mission['mission_id'],)).fetchone()
            c.execute('UPDATE skill_executions SET status=?,finished_at=?,duration=?,output=?,error=? WHERE execution_id=?',
                      ('SUCCEEDED' if result is not None else 'FAILED',time.time(),duration,encode(result) if result is not None else None,error,mission['execution_id']))
            if current['status']=='CANCELLED':
                # Durable cancellation wins over a result racing with cancel.
                c.execute("UPDATE skill_executions SET status='CANCELLED' WHERE execution_id=?",(mission['execution_id'],))
            elif result is not None:
                transition(c,mission['mission_id'],'SUCCEEDED',kind='completed',result=encode(result),error=None)
            else:
                retry=spec.retryable and spec.idempotent and mission['attempts']<mission['max_attempts']
                transition(c,mission['mission_id'],'RETRY_WAIT' if retry else ('WAITING_APPROVAL' if not spec.idempotent else 'FAILED'),kind='execution_failed',
                           error=error,retry_at=time.time()+.05*2**(mission['attempts']-1),data={'error':error,'retry':retry})
        return self.manager.get(mission['mission_id'])

    def drain(self,limit=100):
        results=[]
        for _ in range(limit):
            result=self.run_once()
            if result is None: break
            results.append(result)
        return results
