"""Independent append-only evaluations and versioned local human annotations."""
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid


def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(str(self.path),check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY,provider TEXT NOT NULL,category TEXT NOT NULL,created REAL NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS annotations(id TEXT PRIMARY KEY,evaluation_id TEXT NOT NULL REFERENCES evaluations(id),created REAL NOT NULL,payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
        ''')
        self.db.execute('PRAGMA foreign_keys=ON')

    def save(self,record):
        with self.lock,self.db:
            self.db.execute('INSERT INTO evaluations VALUES (?,?,?,?,?)',(record['evaluation_id'],record['source'],record['category'],time.time(),encode(record)))
        return record

    def get(self,eid):
        with self.lock:row=self.db.execute('SELECT payload FROM evaluations WHERE id=?',(eid,)).fetchone()
        if row is None:raise KeyError('evaluation not found')
        record=json.loads(row['payload']);record['annotation']=self.annotation(eid)
        return record

    def records(self,*,source=None,category=None):
        sql='SELECT id FROM evaluations WHERE 1=1';args=[]
        for key,val in [('provider',source),('category',category)]:
            if val:sql+=' AND '+key+'=?';args.append(val)
        with self.lock:ids=[r['id'] for r in self.db.execute(sql+' ORDER BY created DESC,rowid DESC',args)]
        return [self.get(i) for i in ids]

    def annotate(self,eid,payload):
        with self.lock,self.db:
            self.db.execute('INSERT INTO annotations VALUES (?,?,?,?)',(uuid.uuid4().hex,eid,time.time(),encode(payload)))
        return payload

    def annotation(self,eid):
        with self.lock:row=self.db.execute('SELECT payload FROM annotations WHERE evaluation_id=? ORDER BY created DESC,rowid DESC LIMIT 1',(eid,)).fetchone()
        return json.loads(row['payload']) if row else None

    def batch(self,bid):
        with self.lock:row=self.db.execute('SELECT payload FROM batches WHERE id=?',(bid,)).fetchone()
        if row is None:raise KeyError('batch not found')
        return json.loads(row['payload'])

    def save_batch(self,payload):
        with self.lock,self.db:self.db.execute('INSERT OR REPLACE INTO batches VALUES (?,?)',(payload['batch_id'],encode(payload)))

    def interrupt_batches(self):
        with self.lock:rows=self.db.execute('SELECT payload FROM batches').fetchall()
        for row in rows:
            batch=json.loads(row['payload'])
            if batch['status']=='RUNNING':batch.update(status='INTERRUPTED',error='server restarted; not automatically replayed');self.save_batch(batch)

    def close(self):
        with self.lock:self.db.close()
