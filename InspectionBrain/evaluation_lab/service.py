"""Compose existing Brain layers. No InspectionOS, robot, tools or ASR imports."""
import csv
from dataclasses import replace
from datetime import datetime
import io
import hashlib
import json
import math
import os
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request
from urllib.error import HTTPError, URLError
import uuid

from brain_v3 import SCHEMA_VERSION, ENGINE_VERSION
from brain_v3.config import ProviderConfig
from brain_v3.engine import SemanticEngine
from brain_v3.evidence import build_evidence
from brain_v3.ollama import OllamaProvider, PROMPT_VERSION, SYSTEM_PROMPT
from brain_v3.providers import strict_json
from brain_v3.schema import schema_errors, SCHEMA
from brain_v3.validator import SemanticValidator
from brain_v3.safety import SafetyGuard
from inspection_brain.service import SHANGHAI
from tools.evidence_metrics import check_evidence
from .dataset import load_cases
from .metrics import aggregate
from .annotation import annotate


class BusyError(RuntimeError):pass


def local_config():
    config=ProviderConfig(provider='ollama',enabled=True,
                          base_url=os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434'),
                          model=os.environ.get('OLLAMA_MODEL',''),
                          timeout_seconds=float(os.environ.get('OLLAMA_TIMEOUT','60')))
    if urlsplit(config.base_url).hostname not in ('localhost','127.0.0.1','::1'):
        raise ValueError('Evaluation Lab v0.1 permits loopback Ollama only')
    return config


class OllamaCatalog:
    def __init__(self,config):
        self.config=config;self.provider=OllamaProvider(config)

    def get(self,path):
        if path not in ('/api/version','/api/tags'):raise ValueError('unsupported catalog operation')
        request=Request(self.config.base_url.rstrip('/')+path,headers={'Accept':'application/json'})
        with self.provider.opener.open(request,timeout=min(3,self.config.timeout_seconds)) as r:
            raw=r.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('catalog response too large')
        body=strict_json(raw)
        if not isinstance(body,dict):raise ValueError('invalid catalog response')
        return body

    def check(self):
        try:
            version=self.get('/api/version').get('version')
            models=self.get('/api/tags').get('models')
            if not isinstance(version,str) or not isinstance(models,list):raise ValueError('invalid Ollama metadata')
            rows=[]
            for row in models:
                if not isinstance(row,dict) or not isinstance(row.get('name'),str):continue
                rows.append({'name':row['name'],'digest':row.get('digest') if isinstance(row.get('digest'),str) else None,
                             'modified_at':row.get('modified_at') if isinstance(row.get('modified_at'),str) else None,
                             'size':row.get('size') if type(row.get('size')) is int else None,
                             'details':{k:v for k,v in (row.get('details') or {}).items() if k in ('format','family','parameter_size','quantization_level') and isinstance(v,str)} if isinstance(row.get('details'),dict) else {}})
            return {'connected':True,'version':version,'models':rows,'error':None}
        except (OSError,ValueError,KeyError) as exc:
            if isinstance(exc,HTTPError):kind='http_error';message=f'Ollama目录HTTP错误 {exc.code}'
            elif isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError):kind='timeout';message='Ollama目录检查超时'
            elif isinstance(exc,(ValueError,KeyError)):kind='catalog_response_failure';message='Ollama目录响应无效'
            else:kind='transport_failure';message='Ollama服务连接失败，请检查本机服务'
            return {'connected':False,'version':None,'models':[],'failure_kind':kind,'error':message+'；未切换为Mock'}


class CapturingValidator(SemanticValidator):
    def validate(self,candidate,evidence):
        self.candidate=candidate;self.evidence=evidence
        self.result=super().validate(candidate,evidence)
        return self.result


def scrub_model(value):
    """Remove known reasoning fields/tags before persistence. Never scrub original input."""
    removed=[False]
    forbidden={'thinking','reasoning','reasoning_content','chain_of_thought','analysis'}
    def visit(item):
        if isinstance(item,dict):
            result={}
            for key,val in item.items():
                if key in forbidden:removed[0]=True
                else:result[key]=visit(val)
            return result
        if isinstance(item,list):return [visit(v) for v in item]
        if isinstance(item,str):
            clean=re.sub(r'<think(?:ing)?>.*?(?:</think(?:ing)?>|$)','[REDACTED_REASONING]',item,flags=re.S|re.I)
            removed[0]|=clean!=item
            return clean
        return item
    return visit(value),removed[0]


def safe_raw(raw):
    if raw is None:return None,False
    try:
        value=strict_json(raw)
        # The model content is itself JSON text inside the Ollama envelope.
        if isinstance(value,dict) and isinstance(value.get('message'),dict):
            content=value['message'].get('content')
            if isinstance(content,str):
                try:
                    inner=strict_json(content);inner,changed=scrub_model(inner)
                    if changed:value['message']['content']=json.dumps(inner,ensure_ascii=False)
                except ValueError:pass
        cleaned,removed=scrub_model(value)
        if isinstance(value,dict) and isinstance(value.get('message'),dict):
            removed=removed or cleaned.get('message',{}).get('content')!=strict_json(raw).get('message',{}).get('content')
        return json.dumps(cleaned,ensure_ascii=False),removed
    except (ValueError,TypeError):
        return scrub_model(raw)


def violation(candidate):
    if isinstance(candidate,dict):
        return any((key in ('authorized','executable','hardware_commands_enabled') and val is not False) or (key in ('tool_calls','function_call') and bool(val)) or violation(val) for key,val in candidate.items())
    if isinstance(candidate,list):return any(violation(v) for v in candidate)
    return False


def token_metrics(metadata):
    result={}
    for key in ('total_duration','load_duration','prompt_eval_duration','eval_duration'):
        value=metadata.get(key)
        valid=type(value) in (int,float) and math.isfinite(value) and value>=0
        result[key+'_ns']=value if valid else None
        result[key+'_ms']=value/1_000_000 if valid else None
    for key in ('prompt_eval_count','eval_count'):
        value=metadata.get(key);result[key]=value if type(value) is int and value>=0 else None
    return result


class EvaluationService:
    def __init__(self,store,config=None,*,test_fixture=False):
        self.test_fixture=test_fixture
        self.store=store;self.config=config or local_config();self.catalog=OllamaCatalog(self.config)
        self.cases=load_cases();self.by_id={c['case_id']:c for c in self.cases}
        self.lock=threading.Lock();self.last_request_time=None;self.catalog_status={'connected':None,'models':[],'version':None,'error':'尚未检查'}
        self.batch_threads=[]

    def configuration(self):
        return {'provider':'ollama','default_model':self.config.model,'configuration':self.config.public(),
                'prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,'engine_version':ENGINE_VERSION,
                'last_request_time':self.last_request_time,'status':self.catalog_status,
                'single_request_only':True,'hardware_commands_enabled':False}

    def check_models(self):
        self.catalog_status=self.catalog.check()
        return self.configuration()

    def validate_request(self,data):
        if not isinstance(data,dict) or set(data)-{'case_id','original_request','provider','model','reference_time'}:raise ValueError('unknown evaluation field')
        provider=data.get('provider','ollama')
        if provider not in ('ollama','mock','rules'):raise ValueError('unsupported Provider')
        case_id=data.get('case_id')
        if case_id is not None and not isinstance(case_id,str):raise ValueError('case_id must be text or null')
        case=self.by_id.get(case_id) if case_id else None
        if case_id and case is None:raise ValueError('unknown case ID')
        text=data.get('original_request',case['original_request'] if case else '')
        if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('input requires 1–4000 characters')
        if case and text!=case['original_request']:raise ValueError('edited case must use manual input without case_id')
        model=data.get('model',self.config.model)
        if not isinstance(model,str) or len(model)>200:raise ValueError('invalid model name')
        reference=data.get('reference_time')
        now=datetime.fromisoformat(reference) if isinstance(reference,str) else datetime.now(SHANGHAI)
        if reference is not None and not isinstance(reference,str):raise ValueError('reference_time must be ISO text')
        if now.tzinfo is None:raise ValueError('reference_time requires timezone')
        return provider,model,text,case,now

    def evaluate(self,data):
        args=self.validate_request(data)
        if not self.lock.acquire(blocking=False):raise BusyError('模型正在运行；不并发请求，请等待')
        try:return self._evaluate(args)
        finally:self.lock.release()

    def _evaluate(self,args):
        provider,model,text,case,now=args
        started=time.perf_counter();self.last_request_time=datetime.now(SHANGHAI).isoformat()
        source='MOCK HTTP' if self.test_fixture and provider=='ollama' else {'ollama':'REAL LLM','mock':'MOCK','rules':'RULES'}[provider]
        catalog=None;preflight_error=None;version='not_applicable'
        if provider=='ollama':
            self.catalog_status=self.catalog.check();catalog=self.catalog_status
            row=next((r for r in catalog['models'] if r['name']==model),None)
            if not catalog['connected']:preflight_error=catalog['error']
            elif not row:preflight_error='所选模型未安装或未选择；没有推理、没有自动下载或切换Mock'
            else:version=row.get('digest') or row.get('modified_at') or 'unavailable'
        config=replace(self.config,provider=provider,enabled=provider=='ollama',model=model if provider=='ollama' else provider,model_version=version)
        engine=SemanticEngine(config=config);capture=CapturingValidator();engine.validator=capture
        if preflight_error:
            result=None;candidate=None;complete=False;parse_pass=None;errors={'valid':False,'errors':[]}
            failure='model_unavailable' if catalog and catalog['connected'] else (catalog or {}).get('failure_kind','transport_failure')
            raw=None;metadata={};provider_timings={};evidence=None
        else:
            result=engine.analyze(text,mode='v2_rules' if provider=='rules' else 'v3_llm',now=now)
            if provider=='ollama':
                native=engine.provider;diag=native.diagnostics
                complete=diag.get('complete_response',False);parse_pass=diag.get('json_parse_success')
                candidate=native.last_candidate;raw=native.last_response;metadata=native.response_metadata
                provider_timings=dict(native.timings);failure=diag.get('failure_kind')
            else:
                candidate=result['model_candidate'] if provider=='mock' else capture.candidate
                raw=json.dumps(candidate,ensure_ascii=False,allow_nan=False)
                candidate=strict_json(raw);complete=True;parse_pass=True;metadata={};provider_timings={};failure=None
            errors=result.get('validation') or {'valid':False,'errors':[]}
            evidence=getattr(capture,'evidence',None)
            if evidence is None:evidence=build_evidence(text,result['v2'],now)
        schema_result={'passed':None,'errors':[]}
        evidence_result={'passed':None,'errors':[]}
        validator_result={'valid':False,'errors':[],'executed':False}
        if parse_pass is True:
            schema_issues=schema_errors(candidate)
            schema_result={'passed':not schema_issues,'errors':schema_issues}
            evidence_result=check_evidence(candidate,evidence)
            if schema_result['passed']:
                validator_result={**(getattr(capture,'result',None) or SemanticValidator().validate(candidate,evidence)),'executed':True}
        safe=SafetyGuard().seal(candidate,validator_result,'llm_candidate' if provider=='ollama' else ('mock_script' if provider=='mock' else 'rules_v2'))
        if not complete:outcome='PROVIDER_ERROR'
        elif not schema_result['passed'] or not validator_result['valid'] or evidence_result['passed'] is not True:outcome='REJECTED'
        else:
            ambiguous=bool(re.search(r'那个|记不清|也可能|对应设备|不确定',text)) or any(not t['resolved'] for t in candidate['temporal_constraints']) or any(i['type']=='unknown' for i in candidate['intents'])
            outcome='NEEDS_CLARIFICATION' if ambiguous else 'ACCEPTED'
        unsafe=violation(candidate)
        if raw:
            try:unsafe=unsafe or violation(strict_json(raw))
            except ValueError:pass
        raw_sha256=hashlib.sha256(raw.encode()).hexdigest() if isinstance(raw,str) else None
        raw,raw_redacted=safe_raw(raw);parsed,parsed_redacted=scrub_model(candidate)
        draft,draft_redacted=scrub_model(safe['structured_task_draft'])
        record={'evaluation_id':uuid.uuid4().hex,'case_id':case['case_id'] if case else None,'category':case['category'] if case else '手动输入',
                'original_request':text,'reference_time':now.astimezone(SHANGHAI).isoformat(),
                'timestamp':self.last_request_time,'source':source,'provider':provider,'requested_model':model,
                'model_name':metadata.get('model') if isinstance(metadata.get('model'),str) else ((result or {}).get('provider') or {}).get('model',config.model),
                'model_version':version,'ollama_version':catalog.get('version') if catalog else None,
                'configuration':config.public(),'configuration_sha256':config.sha256,'prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,
                'schema_sha256':hashlib.sha256(json.dumps(SCHEMA,sort_keys=True).encode()).hexdigest(),
                'prompt_sha256':hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                'raw_response':raw,'raw_response_sha256_before_redaction':raw_sha256,'parsed_json':parsed,'reasoning_redacted':raw_redacted or parsed_redacted or draft_redacted,
                'request_result':{'complete':complete,'failure_kind':failure,'error':preflight_error or (result or {}).get('error')},
                'parse_result':{'passed':parse_pass,'origin':'ollama_response' if provider=='ollama' else 'explicit_offline_fixture_serialization'},
                'schema_result':schema_result,'evidence_result':evidence_result,'validator_result':validator_result,
                'safety_result':{'authorized':False,'executable':False,'hardware_commands_enabled':False,'candidate_violation':unsafe,'guard_status':safe['status']},
                'task_draft':draft,'outcome':outcome,'fallback_used':False,
                'latency':{'total_ms':(time.perf_counter()-started)*1000,'provider_timings_seconds':provider_timings},
                'token_metrics':token_metrics(metadata),'annotation':None,
                'interpretation':'ACCEPTED仅为当前工程校验；草案不可执行、人工语义确认独立。'}
        if provider=='ollama':engine.provider.last_response=None;engine.provider.last_candidate=None
        return self.store.save(record)

    def start_batch(self,data):
        if not isinstance(data,dict) or set(data)-{'case_ids','provider','model','reference_time'}:raise ValueError('unknown batch field')
        ids=data.get('case_ids')
        if not isinstance(ids,list) or not 1<=len(ids)<=50 or any(not isinstance(i,str) or i not in self.by_id for i in ids):raise ValueError('batch requires 1–50 known case IDs')
        reference=data.get('reference_time',datetime.now(SHANGHAI).isoformat())
        requests=[{'case_id':i,'provider':data.get('provider','ollama'),'model':data.get('model',self.config.model),'reference_time':reference} for i in ids]
        args=[self.validate_request(r) for r in requests]
        if not self.lock.acquire(blocking=False):raise BusyError('模型正在运行；批量不并发')
        batch={'batch_id':uuid.uuid4().hex,'status':'RUNNING','case_ids':ids,'total':len(ids),'completed':0,'evaluation_ids':[],'error':None}
        try:self.store.save_batch(batch)
        except BaseException:self.lock.release();raise
        def work():
            try:
                for request_args in args:
                    record=self._evaluate(request_args);batch['evaluation_ids'].append(record['evaluation_id']);batch['completed']+=1;self.store.save_batch(batch)
                batch['status']='COMPLETED'
            except Exception as exc:batch.update(status='FAILED',error=type(exc).__name__+'; batch stopped, earlier records retained')
            finally:
                try:self.store.save_batch(batch)
                finally:self.lock.release()
        thread=threading.Thread(target=work,name='evaluation-batch',daemon=True);self.batch_threads.append(thread);thread.start()
        return self.store.batch(batch['batch_id'])

    def statistics(self,**filters):return aggregate(self.store.records(**filters))
    def annotate(self,eid,payload):return annotate(self.store,eid,payload)

    def export(self,kind,**filters):
        records=self.store.records(**filters)
        if kind=='json':return json.dumps({'records':records,'statistics':aggregate(records)},ensure_ascii=False,indent=2).encode(),'application/json; charset=utf-8'
        if kind=='csv':
            stream=io.StringIO();writer=csv.writer(stream)
            keys=['evaluation_id','case_id','source','category','provider','model_name','model_version','prompt_version','schema_version','outcome','timestamp','reference_time','original_request','raw_response','parsed_json','schema_result','validator_result','evidence_result','safety_result','latency','token_metrics','annotation']
            writer.writerow(keys+['latency_ms','schema_pass','validator_pass','annotation_confirmed'])
            def cell(value):
                value='' if value is None else json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
                return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
            for r in records:writer.writerow([cell(r.get(k)) for k in keys]+[r['latency']['total_ms'],r['schema_result']['passed'],r['validator_result']['valid'],bool(r.get('annotation'))])
            return stream.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8'
        if kind=='markdown':
            lines=['# InspectionBrain Evaluation Lab 汇总','','仅当前工程记录；ACCEPTED不是人工语义确认或执行授权。','']
            for group in aggregate(records)['groups']:
                m=group['metrics'];lines += [f"## {group['source']} · {group['model_name']}",'',f"样本量：{m['samples']}；耗时 P95：{m['latency']['p95_ms']} ms（{m['latency']['p95_note']}）",'', '```json',json.dumps(m,ensure_ascii=False,indent=2),'```','']
            return '\n'.join(lines).encode(),'text/markdown; charset=utf-8'
        raise ValueError('export format must be json/csv/markdown')
