"""Unified evidence envelope. Caller must retry explicit backpressure errors."""
from copy import deepcopy
import time
import uuid
from .integrity import checksum

KINDS={'transcript','task_log','mock_alarm','mock_temperature','state_change','skill_result','recovery'}


class Collector:
    def __init__(self,buffer):self.buffer=buffer

    def collect(self,kind,payload,*,trace_id,source):
        if kind not in KINDS or not trace_id or not source:raise ValueError('evidence metadata required')
        if kind.startswith('mock_') and payload.get('is_mock') is not True:raise ValueError('Mock label required')
        payload=deepcopy(payload)
        row={'evidence_id':uuid.uuid4().hex,'trace_id':trace_id,'kind':kind,'source':source,
             'payload':payload,'sha256':checksum(payload),'created_at':time.time()}
        self.buffer.put(row)
        return row['evidence_id']

    def ingest_mission(self,manager,mid):
        mission=manager.get(mid)
        self.collect('task_log',{'mission_id':mid,'status':mission['status']},trace_id=mission['trace_id'],source='InspectionOS')
        for e in manager.events(mid):
            self.collect('recovery' if e['kind'].startswith('recover') else 'state_change',e,trace_id=mission['trace_id'],source='mission_events')
        if mission['result'] is not None:
            self.collect('skill_result',mission['result'],trace_id=mission['trace_id'],source='mock-fixture-v1')
