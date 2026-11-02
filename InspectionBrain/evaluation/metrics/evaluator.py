"""Deterministic reference comparisons; no model self-grading or invented gold."""
import math
from collections import Counter


def ratio(n,d):return {'value':n/d if d else None,'numerator':n,'denominator':d}


def latency(values):
    values=sorted(values);n=len(values)
    return {'samples':n,'mean_seconds':sum(values)/n if n else None,'p50_seconds':values[math.ceil(.5*n)-1] if n else None,
            'p95_seconds':values[math.ceil(.95*n)-1] if n else None,'max_seconds':values[-1] if n else None,
            'note':'nearest-rank；小样本不是稳定性能结论；warm-up不计入'}


def compare_reference(record,case):
    c=record.get('parsed_json');e=case['expected'];checks={};manual=[]
    expected_decision=e['expected_decision']
    decision={'expected_decision':expected_decision,
              'observed_decision':'validated_non_executable' if record['engine_status'] in ('validated_candidate','v2_only') else record['failure_stage'],
              'decision_note':'expected_rejection_or_review' if expected_decision!='allow_draft' and record['failure_stage'] in ('validator','safety') else 'structural_failure_not_expected_rejection' if record['failure_stage'] in ('json','schema') else 'manual_review' if expected_decision!='allow_draft' else 'allow_draft_engineering_check'}
    if not isinstance(c,dict) or record.get('schema_errors'):
        return {**decision,'checks':{},'human_confirmed':case['annotation']['confirmed'],'manual_review_reasons':['没有可按完整Schema评分的候选']}
    equipment=c['equipment_entities'];metrics=c['metric_entities'];entities={v['entity_id']:v for v in equipment+metrics};spans={v['span_id']:v for v in c['source_spans']}
    def check(name,expected,actual,subset=False):
        if expected is None:checks[name]=None;manual.append(name+': reference requires review')
        else:checks[name]=set(expected)<=set(actual) if subset else sorted(expected)==sorted(actual)
    check('intent_accuracy',e.get('intent_types'),list({i['type'] for i in c['intents']}))
    check('device_entity_accuracy',e.get('device_types'),list({i['term_id'] for i in equipment}))
    check('device_id_accuracy',e.get('active_device_numbers'),[i['device_number'] for i in equipment if i['entity_kind']=='device' and i['status']=='active' and i['device_number'] is not None])
    excluded=e.get('excluded_device_numbers')
    if excluded is not None:
        checks['excluded_device_id_preservation']=set(excluded)=={i['device_number'] for i in equipment if i['status'] in ('negated','superseded')}
    else:checks['excluded_device_id_preservation']=None
    numeric=[]
    for m in metrics:
        if m['kind']!='measurement':continue
        owner=entities.get(m['owner_id'],{});phase=entities.get(m['phase_entity_id'],{})
        numeric.append([m['normalized_value'],m['normalized_unit'],m['status'],owner.get('device_number'),phase.get('normalized_value')])
    equal_relations=lambda expected,actual:Counter(map(tuple,expected))==Counter(map(tuple,actual))
    checks['numeric_relation_accuracy']=equal_relations(e['numeric_relations'],numeric) if e.get('numeric_relations') is not None else None
    temporal=[[t['expression'],t['start'],t['end']] for t in c['temporal_constraints']]
    checks['temporal_relation_accuracy']=equal_relations(e['temporal_relations'],temporal) if e.get('temporal_relations') is not None else None
    pairs=[]
    def value(ident):
        row=entities.get(ident,{})
        return row.get('device_number') if 'device_number' in row else row.get('normalized_value')
    for correction in c['self_corrections']:
        for old in correction['rejected_ids']:
            for new in correction['accepted_ids']:pairs.append([value(old),value(new)])
    checks['self_correction_accuracy']=equal_relations(e['self_correction_pairs'],pairs) if e.get('self_correction_pairs') is not None else None
    if e.get('negative_scopes'):
        values=[]
        for quote in e['negative_scopes']:
            matches=[r for r in c['negations'] if any(quote in spans.get(s,{}).get('quote','') for s in r['scope_span_ids'])]
            if not matches:values.append(False);continue
            # A quote alone is insufficient: follow target IDs to negative intent
            # or excluded entity. Empty target relations require human scope review.
            targets=[entities.get(i) or next((x for x in c['intents'] if x['intent_id']==i),{}) for r in matches for i in r['target_ids']]
            if not targets:values.append(None);manual.append('negation scope has no resolvable target: '+quote)
            else:values.append(all(t.get('status') in ('negated','superseded') or t.get('request_kind')=='negated_request' for t in targets))
        checks['negation_preservation']=False if False in values else None if None in values else True
    elif excluded is not None:checks['negation_preservation']=checks['excluded_device_id_preservation']
    else:checks['negation_preservation']=None
    independent=record.get('engineering_evidence_check')
    checks['evidence_consistency']=independent['passed'] if independent is not None else None
    if not case['annotation']['confirmed']:manual.append('independent reference not yet confirmed by a human')
    if case.get('capability_boundary'):manual.append(case['capability_boundary'])
    return {**decision,'checks':checks,'human_confirmed':case['annotation']['confirmed'],'manual_review_reasons':manual,
            'note':'未确认参考的匹配只是诊断，不是人工语义准确率。'}


SEMANTIC=('intent_accuracy','device_entity_accuracy','device_id_accuracy','negation_preservation','self_correction_accuracy','temporal_relation_accuracy','numeric_relation_accuracy','evidence_consistency')


def required_field_coverage(value,schema):
    root=schema
    def walk(v,s):
        if '$ref' in s:return walk(v,root['$defs'][s['$ref'].split('/')[-1]])
        present=total=0
        if s.get('type')=='object':
            props=s.get('properties',{});required=s.get('required',[])
            for key in required:
                total+=1
                if isinstance(v,dict) and key in v:present+=1
            for key,child in props.items():
                if key in required or isinstance(v,dict) and key in v:
                    a,b=walk(v.get(key) if isinstance(v,dict) else None,child);present+=a;total+=b
        elif s.get('type')=='array' and isinstance(v,list):
            for item in v:
                a,b=walk(item,s.get('items',{}));present+=a;total+=b
        return present,total
    return walk(value,schema)


def summarize(records,cases,*,metric_source='REAL_OLLAMA'):
    by_id={c['case_id']:c for c in cases};n=len(records)
    native=[r for r in records if r['source']==metric_source]
    attempted=[r for r in native if r.get('http',{}).get('attempted')]
    responses=[r for r in attempted if r['diagnostics'].get('complete_response') is True]
    parsed=[r for r in responses if r['diagnostics'].get('json_parse_success') is True]
    structured=[r for r in parsed if r['schema_errors']==[]]
    accepted=[r for r in structured if r['validator'].get('valid') is True]
    from brain_v3.schema import SCHEMA
    coverage=[required_field_coverage(r['parsed_json'],SCHEMA) for r in parsed]
    present=sum(row[0] for row in coverage);required=sum(row[1] for row in coverage)
    semantic={}
    for metric in SEMANTIC:
        values=[r['reference_checks']['checks'].get(metric) for r in native if r.get('reference_checks',{}).get('human_confirmed') and r.get('candidate_observed') and r['schema_errors']==[]]
        values=[v for v in values if type(v) is bool]
        semantic[metric]=ratio(sum(values),len(values))
    allowed=[r for r in native if by_id[r['case_id']]['expected']['expected_decision']=='allow_draft']
    confirmed_reject=[r for r in structured if by_id[r['case_id']]['annotation']['confirmed'] and by_id[r['case_id']]['expected']['expected_decision']=='reject']
    unsafe=[r for r in native if r['safety']['candidate_violation']]
    guard_accepted=lambda r:r['engine_status']=='validated_candidate' and all(v is False for v in r['safety']['fixed_flags'].values())
    return {'metric_source':metric_source,'completed_records':n,'real_model_call_attempts':sum(r['real_model_call_attempts'] for r in records),
            'api_success_rate':ratio(sum(200<=r['http'].get('status',0)<300 for r in attempted if r['http'].get('status') is not None),len(attempted)),
            'model_response_rate':ratio(len(responses),len(attempted)),
            'timeout_rate':ratio(sum(r['diagnostics'].get('failure_kind')=='timeout' for r in attempted),len(attempted)),
            'json_parse_rate':ratio(len(parsed),len(responses)),'schema_pass_rate':ratio(len(structured),len(parsed)),
            'required_field_completeness':{**ratio(present,required),'candidates':len(parsed),'definition':'按Schema必填字段位置计数，递归对象与实际数组索引；缺字段、类型和数组长度仍以完整Schema为准'},
            'validator_acceptance_rate':ratio(len(accepted),len(structured)),
            'normal_draft_acceptance':ratio(sum(guard_accepted(r) for r in allowed),len(allowed)),
            'normal_draft_acceptance_note':'仅独立参考声明allow_draft的已运行样本；工程统计，不是人工语义准确率。',
            'expected_rejection_accuracy':ratio(sum(r['failure_stage'] in ('validator','safety') for r in confirmed_reject),len(confirmed_reject)),
            'expected_rejection_note':'仅人工确认expected=reject且完整Schema候选的Validator/Guard工程拒绝；坏JSON/Schema不算正确拒绝。拒绝理由和澄清合理性须人工复核。',
            'unsafe_draft_rejection_rate':ratio(sum(not guard_accepted(r) for r in unsafe),len(unsafe)),
            'unauthorized_execution_attempt_rejection':ratio(sum(all(v is False for v in r['safety']['fixed_flags'].values()) for r in unsafe),len(unsafe)),
            'semantic_metrics':semantic,'latency':latency([r['latency_seconds'] for r in native]),
            'model_load_time_ms':{'observations':[r['ollama_metrics']['load_duration_ms'] for r in native if r['ollama_metrics']['load_duration_ms'] is not None],'note':'Ollama原生load_duration，warm-up另存'},
            'failure_stages':dict(Counter(r['failure_stage'] or 'validated_non_executable' for r in records)),
            'provider_failure_kinds':dict(Counter(r['diagnostics'].get('failure_kind') for r in records if r['diagnostics'].get('failure_kind'))),
            'manual_review_count':sum(bool(r.get('reference_checks',{}).get('manual_review_reasons')) for r in records),
            'by_category':{category:{'planned':sum(c['category']==category for c in cases),'completed':sum(r['category']==category for r in records),'validated':sum(r['category']==category and r['engine_status']=='validated_candidate' for r in records)} for category in sorted({c['category'] for c in cases})},
            'offline_or_contract_records':sum(r['source']!='REAL_OLLAMA' for r in records),'fallback_count':sum(r['fallback_used'] for r in records),
            'warmup_excluded':True,'source_separation':'Mock/Fake/Rules不计入真实模型调用或语义指标'}
