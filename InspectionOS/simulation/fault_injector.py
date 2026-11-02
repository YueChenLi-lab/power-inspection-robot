"""Deliberately small fault hooks. Crash is only used in a test subprocess."""
import os
import sqlite3


def crash_after_claim(app):
    if app.scheduler.claim() is None: raise RuntimeError('no queued mission to crash')
    os._exit(73)


def storage_failure(db):
    """Read-only connection mode reproduces a real SQLite write error."""
    db.connection.execute('PRAGMA query_only=ON')


def restore_storage(db):db.connection.execute('PRAGMA query_only=OFF')
