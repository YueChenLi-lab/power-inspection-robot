"""SQLite is canonical; JSONL is an export, never an audit replacement."""
import json
import os
from pathlib import Path
import threading
import time
from InspectionOS.storage.repositories import encode
from .integrity import verify


class BatchWriter:
    def __init__(self,db,buffer):self.db,self.buffer=db,buffer;self.lock=threading.RLock()

    def flush(self,limit=100):
        with self.lock:
            rows=self.buffer.peek(limit)
            if not rows:return 0
            with self.db.transaction() as c:
                self.db.check_capacity(c,sum(len(encode(r).encode()) for r in rows))
                for r in rows:
                    if not verify(r['payload'],r['sha256']):raise ValueError('buffer evidence integrity failed')
                    prior=c.execute('SELECT sha256 FROM evidence WHERE evidence_id=?',(r['evidence_id'],)).fetchone()
                    if prior and prior['sha256']!=r['sha256']:raise ValueError('evidence ID conflict')
                    c.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?,?)',
                              (r['evidence_id'],r['trace_id'],r['kind'],r['source'],encode(r['payload']),r['sha256'],r['created_at']))
                    c.execute('INSERT OR IGNORE INTO evidence_outbox(event_id,payload) VALUES (?,?)',(r['evidence_id'],encode(r)))
            self.buffer.acknowledge(rows)
            return len(rows)

    def export_jsonl(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        # Never overwrite a previous evidence export.
        with path.open('x',encoding='utf-8') as f:
            for row in self.db.rows('SELECT * FROM evidence ORDER BY created_at,rowid'):
                row['payload']=json.loads(row['payload']);f.write(encode(row)+'\n')
            f.flush();os.fsync(f.fileno())
        return path


def compare_writes(directory,count=100):
    from InspectionOS.storage.database import Database
    from .buffer import Buffer
    from .collector import Collector
    measurements=[]
    for size in (1,20,100):
        db=Database(Path(directory)/f'batch-{size}.db')
        buf=Buffer(count);collector=Collector(buf);writer=BatchWriter(db,buf)
        started=time.perf_counter()
        for i in range(count):
            collector.collect('task_log',{'is_mock':True,'index':i},trace_id='storage-benchmark',source='synthetic')
            if len(buf)>=size:writer.flush(size)
        writer.flush(count)
        elapsed=time.perf_counter()-started
        measurements.append({'batch_size':size,'records':count,'seconds':elapsed,'records_per_second':count/elapsed})
        db.close()
    return measurements
