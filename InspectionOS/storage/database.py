"""Serialized local SQLite transactions. No implicit recovery on open."""
from contextlib import contextmanager
import sqlite3
import threading
from pathlib import Path
import time

DDL = '''
CREATE TABLE IF NOT EXISTS missions (
 mission_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, correlation_id TEXT NOT NULL,
 skill_id TEXT NOT NULL, mission_type TEXT NOT NULL, payload TEXT NOT NULL,
 status TEXT NOT NULL, priority INTEGER NOT NULL, created_at REAL NOT NULL,
 updated_at REAL NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
 retry_at REAL NOT NULL DEFAULT 0, result TEXT, error TEXT, approved INTEGER NOT NULL DEFAULT 0,
 skill_version TEXT NOT NULL, fingerprint TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mission_events (
 event_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(mission_id),
 trace_id TEXT NOT NULL, correlation_id TEXT NOT NULL, skill_id TEXT NOT NULL,
 kind TEXT NOT NULL, before_state TEXT, after_state TEXT, data TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
 approval_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(mission_id),
 actor TEXT NOT NULL, decision TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS skill_executions (
 execution_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES missions(mission_id),
 skill_id TEXT NOT NULL, skill_version TEXT NOT NULL, attempt INTEGER NOT NULL,
 status TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL, duration REAL,
 output TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS outbox_events (
 event_id TEXT PRIMARY KEY REFERENCES mission_events(event_id), payload TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT);
CREATE TABLE IF NOT EXISTS evidence (
 evidence_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, kind TEXT NOT NULL,
 source TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS queue_order ON missions(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS event_mission ON mission_events(mission_id, created_at);
'''


class CapacityError(RuntimeError):
    pass


class Database:
    def __init__(self, path, *, max_missions=100000, max_bytes=256*1024*1024):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.max_missions, self.max_bytes = max_missions, max_bytes
        self.write_seconds = []
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.executescript(DDL)

    @contextmanager
    def transaction(self):
        with self.lock:
            started = time.perf_counter()
            self.connection.execute('BEGIN IMMEDIATE')
            try:
                yield self.connection
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise
            finally:
                self.write_seconds.append(time.perf_counter()-started)

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.connection.execute(sql, args).fetchall()]

    def check_capacity(self, connection, incoming_bytes=0):
        # Admission protection, not a filesystem quota. Keep space for audit/terminal events.
        pages = connection.execute('PRAGMA page_count').fetchone()[0]
        size = connection.execute('PRAGMA page_size').fetchone()[0]
        if pages*size + incoming_bytes > self.max_bytes:
            raise CapacityError('storage admission limit reached; audit records retained')

    def close(self):
        with self.lock:
            self.connection.close()
