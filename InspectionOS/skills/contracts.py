"""Small closed JSON contract; unsupported vocabulary is an error."""
from dataclasses import dataclass
import math
from typing import Protocol


def validate(value, schema, path='$'):
    allowed={'type','properties','required','additionalProperties','items','enum','minimum','maximum','minLength'}
    if set(schema)-allowed: raise ValueError('unsupported schema vocabulary')
    kind=schema.get('type')
    checks={'object':lambda v:isinstance(v,dict),'array':lambda v:isinstance(v,list),
            'string':lambda v:isinstance(v,str),'integer':lambda v:type(v) is int,
            'number':lambda v:type(v) in (int,float) and math.isfinite(v),'boolean':lambda v:type(v) is bool}
    if kind not in checks or not checks[kind](value): raise ValueError(path+': type')
    if 'enum' in schema and value not in schema['enum']: raise ValueError(path+': enum')
    if kind=='object':
        if set(schema.get('required',[]))-value.keys(): raise ValueError(path+': required')
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False and value.keys()-props.keys(): raise ValueError(path+': unknown field')
        for key in value.keys() & props.keys(): validate(value[key],props[key],path+'.'+key)
    elif kind=='array':
        for item in value: validate(item,schema['items'],path+'[]')
    elif kind in ('integer','number'):
        if not schema.get('minimum',-math.inf)<=value<=schema.get('maximum',math.inf): raise ValueError(path+': bounds')
    elif kind=='string' and len(value)<schema.get('minLength',0): raise ValueError(path+': length')


@dataclass(frozen=True)
class SkillSpec:
    skill_id: str
    name: str
    description: str
    input_schema: dict
    output_schema: dict
    timeout: float = 2
    retryable: bool = True
    idempotent: bool = True
    offline_supported: bool = True
    risk_level: str = 'low'
    version: str = '1.0'
    execution_scope: str = 'mock'
    requires_network_authorization: bool = False

    def __post_init__(self):
        if not self.skill_id or not self.version or not 0 < self.timeout <= 60:
            raise ValueError('invalid skill metadata')
        if self.risk_level not in ('low','high','motion'): raise ValueError('unknown risk')


class Skill(Protocol):
    spec: SkillSpec
    def execute(self, payload: dict) -> dict: ...


INPUT = {'type':'object','required':['device_id'],'additionalProperties':False,'properties':{
    'device_id':{'type':'string','enum':['MOCK-CB-3','MOCK-TR-1']},
    'start':{'type':'string'},'end':{'type':'string'},'compare':{'type':'boolean'}}}
OUTPUT = {'type':'object','required':['is_mock','source','device_id','records','summary'],
          'additionalProperties':False,'properties':{
              'is_mock':{'type':'boolean','enum':[True]},'source':{'type':'string','enum':['mock-fixture-v1']},
              'device_id':{'type':'string'},'records':{'type':'array','items':{'type':'object'}},
              'summary':{'type':'string'}}}
