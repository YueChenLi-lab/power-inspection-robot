"""Serial, local-only model evaluation with append-only per-case evidence."""
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from urllib.parse import urlsplit
import uuid

from brain_v3.config import ProviderConfig
from brain_v3.diagnostics import OllamaCatalog
from ..dataset import load_dataset,select_cases,DEFAULT_DATASET
from ..metrics.evaluator import compare_reference
from .observation import observe
from .reports import append_record,load_records,write_reports,encode

FORMAT='inspection-local-evaluation-v1'


def build_config(provider='ollama',timeout=None,max_tokens=None):
    base=ProviderConfig.from_environment()
    if provider not in ('ollama','mock','rules'):raise ValueError('only local Ollama / offline controls supported')
    if provider=='ollama':
        url=os.environ.get('BRAIN_V3_BASE_URL',os.environ.get('OLLAMA_BASE_URL','http://127.0.0.1:11434'))
        if urlsplit(url).hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('local evaluator rejects non-loopback model endpoints; no cloud API')
        enabled=base.enabled if 'BRAIN_V3_ENABLE_LLM' in os.environ else True
        return replace(base,provider='ollama',enabled=enabled,base_url=url,
                       model=os.environ.get('BRAIN_V3_MODEL',os.environ.get('OLLAMA_MODEL','qwen3:4b-instruct')),
                       timeout_seconds=timeout if timeout is not None else float(os.environ.get('BRAIN_V3_TIMEOUT',os.environ.get('OLLAMA_TIMEOUT','60'))),
                       max_output_tokens=max_tokens if max_tokens is not None else base.max_output_tokens,allow_external_text=False)
    return replace(base,provider=provider,enabled=False,timeout_seconds=timeout if timeout is not None else base.timeout_seconds,
                   max_output_tokens=max_tokens if max_tokens is not None else base.max_output_tokens)


def pilot_is_healthy(folder,dataset_sha,config,service):
    folder=Path(folder)
    metadata=json.loads((folder/'metadata.json').read_text())
    status=json.loads((folder/'run_status.json').read_text())
    rows=load_records(folder/'raw_results.jsonl')
    if metadata.get('format')!=FORMAT or metadata.get('source')!='REAL_OLLAMA':raise ValueError('pilot must be a real Ollama run, never a Mock/Fake report')
    if metadata['dataset_sha256']!=dataset_sha or metadata['configuration_sha256']!=config.sha256:raise ValueError('pilot dataset/configuration differs; rerun 10-case pilot')
    if status['status']!='COMPLETED' or len(rows)<10:raise ValueError('pilot needs >=10 completed records')
    if not all(r['source']=='REAL_OLLAMA' and r['diagnostics'].get('complete_response') is True and r['diagnostics'].get('json_parse_success') is True and r['http'].get('status')==200 for r in rows[:10]):raise ValueError('pilot transport/JSON unhealthy; diagnose before full run')
    if not any(r['schema_errors']==[] for r in rows[:10]):raise ValueError('pilot has no Schema-compatible candidate; diagnose before full run')
    prior=rows[-1].get('observed_model') or metadata['observed_environment'].get('ollama_model') or {}
    current=next((r for r in service.get('models',[]) if r['name']==config.model),{})
    if not prior.get('digest') or prior['digest']!=current.get('digest') or any((r.get('observed_model') or {}).get('digest')!=current.get('digest') for r in rows[:10]):raise ValueError('pilot model digest unavailable/changed; rerun pilot')
    return {'pilot_dir':str(folder.resolve()),'records':len(rows),'health':'HTTP + complete response + JSON; at least one Schema candidate; Validator rejection allowed as measured outcome'}


class RunLock:
    def __init__(self,folder):self.path=Path(folder)/'.run.lock';self.handle=None
    def __enter__(self):
        import fcntl
        self.handle=self.path.open('a')
        try:fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:self.handle.close();raise RuntimeError('another evaluator is using this run') from None
        return self
    def __exit__(self,*args):
        import fcntl
        fcntl.flock(self.handle,fcntl.LOCK_UN);self.handle.close()


def evaluate_run(*,config,dataset_path=DEFAULT_DATASET,output_dir='.local-evaluation/qwen3-4b',category='all',case_id=None,limit=None,
                 warmup=False,resume=None,pilot_run=None,verbose=False,observer=observe,service_probe=None,fixture=False):
    dataset,dataset_sha=load_dataset(dataset_path)
    cases=select_cases(dataset,category=category,case_id=case_id,limit=limit)
    source='CONTRACT_FIXTURE' if fixture else 'REAL_OLLAMA' if config.provider=='ollama' else config.provider.upper()
    service=(service_probe or (lambda:OllamaCatalog(config).check()))() if config.provider=='ollama' else {'connected':None,'models':[],'version':None,'error':None}
    selected_model=next((m for m in service.get('models',[]) if m['name']==config.model),None)
    if resume:
        folder=Path(resume);metadata=json.loads((folder/'metadata.json').read_text())
        if metadata.get('format')!=FORMAT or metadata['dataset_sha256']!=dataset_sha or metadata['configuration_sha256']!=config.sha256 or metadata['source']!=source:raise ValueError('resume contract/dataset/config differs; original records preserved')
        ids=metadata['case_ids'];by_id={c['case_id']:c for c in dataset['cases']};cases=[by_id[i] for i in ids]
        prior_model=metadata['observed_environment'].get('ollama_model')
        if config.provider=='ollama' and prior_model and selected_model and prior_model.get('digest')!=selected_model.get('digest'):raise ValueError('model digest changed; start a new run')
    else:
        parent=Path(output_dir);parent.mkdir(parents=True,exist_ok=True)
        folder=Path(tempfile.mkdtemp(prefix='run-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-',dir=parent))
        metadata={'format':FORMAT,'run_id':uuid.uuid4().hex,'source':source,'provider':config.provider,
                  'dataset_path':str(Path(dataset_path).resolve()),'dataset_sha256':dataset_sha,'dataset_version':dataset['dataset_version'],
                  'case_ids':[c['case_id'] for c in cases],'configuration':config.public(),'configuration_sha256':config.sha256,
                  'observed_environment':{'python':sys.version,'platform':platform.platform(),'executable':sys.executable,'cpu_count':os.cpu_count(),
                       'ollama_version':service.get('version'),'ollama_model':selected_model,'model_service_connected':service.get('connected')},
                  'created_at':datetime.now().astimezone().isoformat(),'warmup_requested':warmup,
                  'annotation_policy':'Unconfirmed authored expectations are diagnostics only; semantic scores require confirmed human_review.',
                  'privacy':'Private local results. No remote publish, no raw input/output printed by verbose.'}
        with (folder/'metadata.json').open('x',encoding='utf-8') as f:f.write(encode(metadata))
    with RunLock(folder):
        rows=load_records(folder/'raw_results.jsonl');completed={r['case_id'] for r in rows}
        frozen={c['case_id']:c for c in cases}
        for r in rows:
            case=frozen.get(r['case_id'])
            if case is None or r['source']!=source or r['configuration_sha256']!=config.sha256 or r['original_request']!=case['original_request'] or r['reference_time']!=case['reference_time']:
                raise ValueError('journal record differs from frozen source/config/input; original retained')
            if config.provider=='ollama' and selected_model and (r.get('observed_model') or {}).get('digest')!=selected_model.get('digest'):
                raise ValueError('recorded model digest differs from current model; start a new run')
        if not completed<={c['case_id'] for c in cases}:raise ValueError('journal contains case outside frozen selection')
        session_id=uuid.uuid4().hex
        with (folder/('session-'+session_id+'.json')).open('x',encoding='utf-8') as f:
            f.write(encode({'timestamp':datetime.now().astimezone().isoformat(),'ollama':{'connected':service.get('connected'),'version':service.get('version'),'selected_model':selected_model,'error':service.get('error')},'configuration_sha256':config.sha256,'resume':bool(resume)}))
        state={'session_id':session_id,'status':'RUNNING','planned':len(cases),'completed':len(rows),'blocker':None,'inflight_case':None}
        warmup_record=json.loads((folder/'warmup.json').read_text()) if (folder/'warmup.json').exists() else None
        def observed(case,phase):
            def attempted():
                attempt_id=uuid.uuid4().hex
                append_record(folder/'request_attempts.jsonl',{'attempt_id':attempt_id,'case_id':case['case_id'],'phase':phase,
                              'source':source,'timestamp':datetime.now().astimezone().isoformat()})
                return attempt_id
            return observer(config,case,fixture=fixture,on_attempt=attempted)
        # Failed preflight is a run-level blocker, not 10 fabricated failed model calls.
        if config.provider=='ollama' and (not config.enabled or not service.get('connected') or selected_model is None):
            state.update(status='BLOCKED',blocker='LLM explicitly disabled' if not config.enabled else service.get('error') if not service.get('connected') else 'requested model not installed')
            write_reports(folder,rows,cases,state,warmup=warmup_record)
            return folder,state,rows
        if config.provider=='ollama' and len(cases)>10:
            if not pilot_run:
                state.update(status='PILOT_REQUIRED',blocker='First run --limit 10 --warmup, then pass the healthy real run directory via --pilot-run for all 60.')
                write_reports(folder,rows,cases,state,warmup=warmup_record)
                return folder,state,rows
            try:state['pilot']=pilot_is_healthy(pilot_run,dataset_sha,config,service)
            except (ValueError,OSError,KeyError) as exc:
                state.update(status='PILOT_REJECTED',blocker=str(exc))
                write_reports(folder,rows,cases,state,warmup=warmup_record);return folder,state,rows
        write_reports(folder,rows,cases,state,warmup=warmup_record)
        if config.provider=='ollama' and warmup_record and warmup_record['failure_stage'] in ('provider','json'):
            state.update(status='WARMUP_FAILED',blocker='Original warm-up failed; start a new run after diagnosis. Original warm-up is retained.')
            write_reports(folder,rows,cases,state,warmup=warmup_record);return folder,state,rows
        try:
            if metadata['warmup_requested'] and warmup_record is None:
                state['inflight_case']='WARMUP';write_reports(folder,rows,cases,state)
                warmup_record=observed(cases[0],'warmup')
                with (folder/'warmup.json').open('x',encoding='utf-8') as f:f.write(encode(warmup_record));f.flush();os.fsync(f.fileno())
                if config.provider=='ollama' and warmup_record['failure_stage'] in ('provider','json'):
                    state.update(status='WARMUP_FAILED',blocker='Warm-up transport/JSON failed; diagnose before semantic sample run',inflight_case=None)
                    write_reports(folder,rows,cases,state,warmup=warmup_record);return folder,state,rows
            for case in cases:
                if case['case_id'] in completed:continue
                state['inflight_case']=case['case_id'];write_reports(folder,rows,cases,state,warmup=warmup_record)
                row=observed(case,'sample')
                row['observed_model']=selected_model
                row['observed_ollama_version']=service.get('version')
                row['reference_checks']=compare_reference(row,case)
                append_record(folder/'raw_results.jsonl',row);rows.append(row);completed.add(case['case_id'])
                state.update(completed=len(rows),inflight_case=None)
                write_reports(folder,rows,cases,state,warmup=warmup_record)
                if verbose:print(json.dumps({'case_id':case['case_id'],'source':row['source'],'status':row['engine_status'],'failure_stage':row['failure_stage']},ensure_ascii=False),flush=True)
            state.update(status='COMPLETED',inflight_case=None)
        except KeyboardInterrupt:
            state.update(status='INTERRUPTED',blocker='Interrupted request is not counted completed; prior JSONL records retained')
        except Exception as exc:
            state.update(status='FAILED',blocker=type(exc).__name__+': '+str(exc))
            write_reports(folder,rows,cases,state,warmup=warmup_record)
            raise
        write_reports(folder,rows,cases,state,warmup=warmup_record)
        return folder,state,rows
