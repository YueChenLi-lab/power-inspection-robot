"""Validate independent references, never synthesize gold from predictions."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from brain_v3.schema import SCHEMA

DEFAULT_DATASET=Path(__file__).with_name('datasets')/'power_inspection_cases.json'
CATEGORIES=('terminology','correction','negation','relations','ambiguity','safety')


def load_dataset(path=DEFAULT_DATASET):
    path=Path(path);raw=path.read_bytes();data=json.loads(raw)
    cases=data.get('cases')
    if not isinstance(cases,list) or not cases:raise ValueError('dataset requires nonempty cases')
    identifiers=set();intent_types=set(SCHEMA['$defs']['intent']['properties']['type']['enum'])
    for case in cases:
        required={'case_id','category','original_request','reference_time','expected','annotation','capability_boundary'}
        if not isinstance(case,dict) or not required<=case.keys():raise ValueError('invalid dataset case')
        if case['case_id'] in identifiers:raise ValueError('duplicate case ID')
        identifiers.add(case['case_id'])
        if case['category'] not in CATEGORIES:raise ValueError('unknown category')
        if not isinstance(case['original_request'],str) or not case['original_request'].strip():raise ValueError('empty request')
        clock=datetime.fromisoformat(case['reference_time'])
        if clock.tzinfo is None:raise ValueError('reference_time must have timezone')
        expected=case['expected'];intents=expected.get('intent_types')
        if intents is not None and (not isinstance(intents,list) or not set(intents)<=intent_types):raise ValueError('reference intent outside current Schema')
        if expected['expected_decision'] not in ('allow_draft','review','clarify','reject','reject_or_review'):raise ValueError('invalid reference decision')
        for key in ('device_types','active_device_numbers','excluded_device_numbers','negative_scopes'):
            value=expected.get(key)
            if value is not None and (not isinstance(value,list) or any(not isinstance(v,str) for v in value)):raise ValueError('invalid '+key)
        for row in expected.get('numeric_relations') or []:
            if not isinstance(row,list) or len(row)!=5 or row[2] not in ('active','negated','superseded','uncertain'):raise ValueError('invalid numeric relation')
        for row in expected.get('temporal_relations') or []:
            if len(row)!=3 or any(datetime.fromisoformat(t).tzinfo is None for t in row[1:]):raise ValueError('invalid temporal reference')
        annotation=case['annotation']
        if type(annotation.get('confirmed')) is not bool:raise ValueError('annotation confirmation must be bool')
        if annotation['confirmed'] and (annotation.get('status')!='confirmed' or annotation.get('source')!='human_review' or not isinstance(annotation.get('annotator'),str) or not annotation['annotator'].strip()):raise ValueError('confirmed gold requires explicit human review metadata')
    return data,hashlib.sha256(raw).hexdigest()


def select_cases(dataset,*,category='all',case_id=None,limit=None):
    if category not in ('all',*CATEGORIES):raise ValueError('unknown category')
    rows=[c for c in dataset['cases'] if category=='all' or c['category']==category]
    if case_id:
        rows=[c for c in rows if c['case_id']==case_id]
        if not rows:raise ValueError('case ID not in selected category')
    if limit is not None:
        if type(limit) is not int or limit<1:raise ValueError('limit must be positive')
        rows=rows[:limit]
    if not rows:raise ValueError('selection contains no cases')
    return rows
