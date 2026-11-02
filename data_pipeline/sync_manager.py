"""At-least-once delivery. Receiver deduplicates stable event IDs durably."""
import json
import sqlite3
from InspectionOS.storage.repositories import encode


class MockRemote:
    def __init__(self,path):
        self.connection=sqlite3.connect(path)
        self.connection.execute('CREATE TABLE IF NOT EXISTS inbox(event_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        self.connection.commit()
        self.fail_after_commit=False

    def receive(self,event_id,payload):
        encoded=encode(payload)
        prior=self.connection.execute('SELECT payload FROM inbox WHERE event_id=?',(event_id,)).fetchone()
        if prior and prior[0]!=encoded: raise ValueError('event ID reused with different payload')
        with self.connection:
            self.connection.execute('INSERT OR IGNORE INTO inbox VALUES (?,?)',(event_id,encoded))
        if self.fail_after_commit: raise ConnectionError('simulated ACK lost after durable receive')

    def count(self):return self.connection.execute('SELECT count(*) FROM inbox').fetchone()[0]
    def close(self):self.connection.close()


class SyncManager:
    def __init__(self,db,network,remote):self.db,self.network,self.remote=db,network,remote

    def sync(self,limit=100):
        sent,failed=0,0
        rows=self.db.rows("SELECT * FROM outbox_events WHERE status='PENDING' ORDER BY rowid LIMIT ?",(limit,))
        for row in rows:
            error=None
            try:
                self.network.request('outbox-send')
                self.remote.receive(row['event_id'],json.loads(row['payload']))
            except ConnectionError as exc:error=str(exc)
            with self.db.transaction() as c:
                c.execute('UPDATE outbox_events SET attempts=attempts+1,status=?,last_error=? WHERE event_id=?',
                          ('PENDING' if error else 'SENT',error,row['event_id']))
            if error:failed+=1
            else:sent+=1
        return {'sent':sent,'failed':failed,'pending':self.db.rows("SELECT count(*) n FROM outbox_events WHERE status='PENDING'")[0]['n']}
