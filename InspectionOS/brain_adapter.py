"""Fail-closed Brain -> MOCK runtime boundary. No model permission is trusted."""
from datetime import datetime
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'InspectionBrain'))
from brain_v3.engine import SemanticEngine
from brain_v3.evidence import build_evidence
from brain_v3.config import ProviderConfig
from brain_v3.validator import SemanticValidator
from brain_v3.schema import schema_errors
from inspection_brain.service import SHANGHAI
from observability.tracing import TraceContext
from observability.instrumentation import Recorder


class MeasuredValidator(SemanticValidator):
    def __init__(self,recorder,context):self.recorder,self.context=recorder,context
    def validate(self,candidate,evidence):
        with self.recorder.span('schema',self.context):schema_errors(candidate)
        with self.recorder.span('evidence_semantic_validator',self.context):
            # Original validator includes its own schema check; documented inclusive timing.
            return super().validate(candidate,evidence)


class BrainAdapter:
    def __init__(self,manager,config=None,provider=None,recorder=None):
        self.manager=manager
        self.engine=SemanticEngine(config=config or ProviderConfig(),provider=provider)
        self.recorder=recorder or Recorder()

    def submit_text(self,text,*,idempotency_key,mode='v2_rules',now=None):
        ctx=TraceContext.new();now=now or datetime.now(SHANGHAI)
        self.engine.validator=MeasuredValidator(self.recorder,ctx)
        start=time.perf_counter()
        with self.recorder.span('semantic_total',ctx):result=self.engine.analyze(text,mode=mode,now=now)
        if result.get('llm_inference_seconds') is not None:
            self.recorder.records.append({**ctx.fields(),'stage':'llm_provider','seconds':result['llm_inference_seconds'],'error':result['error']})
        return self.submit_result(result,idempotency_key=idempotency_key,context=ctx)

    def submit_result(self,result,*,idempotency_key,context=None):
        context=context or TraceContext.new()
        text=result['original_request']
        now=datetime.fromisoformat(result['reference_time'])
        v2=self.engine.brain.ask(text,now=now)
        evidence=build_evidence(text,v2,now)
        if result.get('status')=='v2_only':candidate=evidence
        else:
            selected=result.get('fallback') if result.get('fallback_success') else result.get('v3')
            if not selected:raise ValueError('no accepted semantic result')
            candidate=selected['semantic']
        validation=SemanticValidator().validate(candidate,evidence)
        if not validation['valid']:raise ValueError('semantic handoff rejected: '+','.join(validation['errors']))
        draft=result.get('structured_task_draft')
        if not draft or any(draft.get(k) is not False for k in ('authorized','executable','hardware_commands_enabled')):
            raise PermissionError('Brain draft must remain unprivileged')
        if candidate['conditions']:raise ValueError('conditional task needs clarification')
        if any(i['type']=='operation_proposal' and i['request_kind']!='negated_request' for i in candidate['intents']):
            raise PermissionError('motion/operation request forbidden')
        devices=[e for e in candidate['equipment_entities'] if e['entity_kind']=='device' and e['status']=='active']
        if len(devices)!=1:raise ValueError('one explicit mock device required')
        mapping={('circuit_breaker','3'):'MOCK-CB-3',('transformer','1'):'MOCK-TR-1',('main_transformer','1'):'MOCK-TR-1'}
        device=mapping.get((devices[0]['term_id'],devices[0]['device_number']))
        if not device:raise ValueError('no explicit MOCK registry mapping')
        types={i['type'] for i in candidate['intents'] if i['request_kind']!='negated_request'}
        allowed={'temperature_alarm_query','thermometry_history','temperature_measurement_query','temperature_comparison','reinspection_recommendation'}
        if not types or types-allowed:raise ValueError('unsupported intent; no partial execution')
        if 'reinspection_recommendation' in types:skill='mock.reinspection'
        elif types & {'thermometry_history','temperature_comparison','temperature_measurement_query'}:skill='mock.temperature_query'
        else:skill='mock.alarm_query'
        payload={'device_id':device}
        periods=candidate['temporal_constraints']
        if any(not t['resolved'] for t in periods):raise ValueError('unresolved time; clarification required')
        if len(periods)>1:raise ValueError('multiple time windows not supported by v0.1 mock contract')
        if periods:payload.update(start=periods[0]['start'],end=periods[0]['end'])
        if 'temperature_comparison' in types:payload['compare']=True
        # The new mission is a mock-only read request. The Brain draft is never
        # changed into executable=true and real equipment identity stays unverified.
        mission=self.manager.create(skill,payload,idempotency_key=idempotency_key,source='brain-adapter:mock-only',
                                    trace_id=context.trace_id,correlation_id=context.correlation_id)
        for record in self.recorder.records:
            if record['trace_id']==context.trace_id:
                record.update(mission_id=mission['mission_id'],skill_id=skill)
        return mission
