from dataclasses import dataclass, asdict
import json
import uuid


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    correlation_id: str
    mission_id: str = ''
    skill_id: str = ''

    @classmethod
    def new(cls):return cls(uuid.uuid4().hex,uuid.uuid4().hex)
    def fields(self):return asdict(self)


def export_trace(db,trace_id):
    return db.rows('SELECT * FROM mission_events WHERE trace_id=? ORDER BY created_at,rowid',(trace_id,))
