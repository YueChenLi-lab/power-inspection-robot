"""Thin instrumentation around the existing Native Provider / SemanticEngine."""
from datetime import datetime
import hashlib
import json
import time
from urllib.error import HTTPError

from brain_v3.engine import SemanticEngine
from brain_v3.ollama import OllamaProvider,PROMPT_VERSION
from brain_v3.providers import MockProvider,RulesFallbackProvider
from brain_v3.schema import schema_errors,SCHEMA
from brain_v3.validator import SemanticValidator
from brain_v3.safety import SafetyGuard
from brain_v3 import SCHEMA_VERSION,ENGINE_VERSION
from brain_v3.diagnostics import CapturingValidator,safe_raw,scrub_model,token_metrics,violation
from tools.evidence_metrics import check_evidence


class ObservedOpener:
    def __init__(self,opener,on_attempt=None):self.opener=opener;self.http={};self.on_attempt=on_attempt
    def open(self,request,**kwargs):
        self.http={'attempted':True,'status':None}
        if self.on_attempt is not None:self.http['attempt_id']=self.on_attempt()
        try:
            response=self.opener.open(request,**kwargs)
            self.http['status']=response.getcode()
            return response
        except HTTPError as exc:self.http['status']=exc.code;raise


class ObservedOllamaProvider(OllamaProvider):
    def __init__(self,config,on_attempt=None):
        super().__init__(config);self.observed_opener=ObservedOpener(self.opener,on_attempt);self.opener=self.observed_opener
    def generate(self,request):
        self.observed_opener.http={'attempted':False,'status':None}
        return super().generate(request)


class TimedCapture(CapturingValidator):
    def validate(self,candidate,evidence):
        start=time.perf_counter();issues=schema_errors(candidate)
        self.schema_seconds=time.perf_counter()-start
        start=time.perf_counter();result=super().validate(candidate,evidence)
        self.validator_seconds=time.perf_counter()-start
        return result


class ObservedGuard(SafetyGuard):
    def __init__(self):self.invoked=False;self.failed=False;self.elapsed=None;self.result=None
    def seal(self,*args):
        self.invoked=True;start=time.perf_counter()
        try:self.result=super().seal(*args);return self.result
        except Exception:self.failed=True;raise
        finally:self.elapsed=time.perf_counter()-start


def observe(config,case,*,mode=None,provider=None,fixture=False,on_attempt=None):
    mode=mode or ('v2_rules' if config.provider=='rules' else 'v3_llm')
    if provider is None:
        provider=ObservedOllamaProvider(config,on_attempt) if config.provider=='ollama' else MockProvider() if config.provider=='mock' else RulesFallbackProvider()
    engine=SemanticEngine(config=config,provider=provider);capture=TimedCapture();engine.validator=capture
    guard=ObservedGuard();engine.guard=guard
    started=time.perf_counter()
    result=engine.analyze(case['original_request'],mode=mode,now=datetime.fromisoformat(case['reference_time']))
    elapsed=time.perf_counter()-started
    real=config.provider=='ollama' and not fixture
    source='CONTRACT_FIXTURE' if fixture else 'REAL_OLLAMA' if real else config.provider.upper()
    candidate=result.get('model_candidate')
    diagnostics=dict(getattr(provider,'diagnostics',{}))
    if diagnostics.get('json_parse_success') is True:candidate=getattr(provider,'last_candidate',candidate)
    candidate_observed=result.get('model_candidate') is not None or diagnostics.get('json_parse_success') is True
    evidence=getattr(capture,'evidence',None)
    # Invalid-object JSON never reaches Engine's Validator. Schema still records it.
    issues=schema_errors(candidate) if candidate_observed else None
    validation=result.get('validation') or {}
    safe=guard.result
    if mode=='v2_rules':candidate=getattr(capture,'candidate',None);evidence=getattr(capture,'evidence',None);candidate_observed=candidate is not None;issues=schema_errors(candidate) if candidate_observed else None;validation=getattr(capture,'result',{})
    independent=check_evidence(candidate,evidence) if candidate_observed and evidence is not None else None
    unsafe=violation(candidate)
    raw=getattr(provider,'last_response',None)
    raw_hash=hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw,str) else None
    clean_raw,raw_redacted=safe_raw(raw)
    clean_candidate,candidate_redacted=scrub_model(candidate)
    clean_result,result_redacted=scrub_model(result)
    http=dict(getattr(getattr(provider,'observed_opener',None),'http',{}))
    complete=diagnostics.get('complete_response')
    if source!='REAL_OLLAMA' and not fixture:complete=None
    if guard.failed:failure='safety'
    elif result['status'] in ('validated_candidate','v2_only'):failure=None
    elif issues:failure='schema'
    elif result['status']=='validation_rejected':failure='validator'
    elif diagnostics.get('failure_kind')=='json_parse_failure':failure='json'
    else:failure='provider'
    final_flags={k:result[k] for k in ('authorized','executable','hardware_commands_enabled')}
    record={'case_id':case['case_id'],'category':case['category'],'source':source,'original_request':case['original_request'],
            'reference_time':case['reference_time'],'timestamp':datetime.now().astimezone().isoformat(),
            'provider':config.provider,'model_requested':config.model,'model_reported':result['provider'].get('model'),
            'configuration_sha256':config.sha256,'schema_version':SCHEMA_VERSION,'prompt_version':PROMPT_VERSION,'engine_version':ENGINE_VERSION,
            'http':http,'diagnostics':diagnostics,'raw_response':clean_raw,'raw_response_sha256_before_redaction':raw_hash,
            'parsed_json':clean_candidate,'candidate_observed':candidate_observed,'schema_errors':issues,
            'validator':validation,'engineering_evidence_check':independent,'failure_stage':failure,
            'engine_status':result['status'],'error':result.get('error'),'result':clean_result,
            'safety':{'fixed_flags':final_flags,'candidate_violation':unsafe,'guard_invoked':guard.invoked,
                      'guard_status':safe.get('status') if safe else None,'final_draft_present':result.get('structured_task_draft') is not None},
            'latency_seconds':elapsed,'stage_seconds':{'provider_and_json':getattr(provider,'timings',{}),
                      'schema':getattr(capture,'schema_seconds',None),'evidence_semantic_inclusive_schema':getattr(capture,'validator_seconds',None),'safety_guard':guard.elapsed},
            'ollama_metrics':token_metrics(getattr(provider,'response_metadata',{})),
            'reasoning_redacted':raw_redacted or candidate_redacted or result_redacted,
            'real_model_call_attempts':int(real and http.get('attempted',False)),
            'fallback_used':result['fallback_used'],'expected_decision':case['expected']['expected_decision']}
    # No model prediction, reference answer or annotations are added to future prompts.
    return record
