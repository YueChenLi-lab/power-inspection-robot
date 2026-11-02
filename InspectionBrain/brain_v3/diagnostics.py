"""Pure diagnostic helpers shared by CLI and the existing Lab; no Web/DB runtime."""
import json
import math
import re
from urllib.error import HTTPError
from urllib.request import Request
from .ollama import OllamaProvider
from .providers import strict_json
from .validator import SemanticValidator

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
