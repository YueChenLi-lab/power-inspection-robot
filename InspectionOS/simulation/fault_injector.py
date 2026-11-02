"""Fault hooks used only by local simulation and tests."""
import os
import sqlite3
import time
from dataclasses import replace
from InspectionOS.skills.mock.alarm_query import AlarmQuerySkill


class CrashDuringSkill(AlarmQuerySkill):
    """Test-only Skill: kill worker parent after execute() has begun."""
    spec=replace(AlarmQuerySkill.spec,skill_id='mock.crash',timeout=1)
    def execute(self,payload):
        import signal
        # Called only in a subprocess started by the experiment's worker.
        # SIGKILL represents abrupt power/process failure. No hardware access.
        os.kill(os.getppid(),signal.SIGKILL)
        return super().execute(payload)


def crash_after_claim(app):
    if app.scheduler.claim() is None:raise RuntimeError('no queued mission to crash')
    os._exit(73)


def storage_failure(db):db.connection.execute('PRAGMA query_only=ON')
def restore_storage(db):db.connection.execute('PRAGMA query_only=OFF')
