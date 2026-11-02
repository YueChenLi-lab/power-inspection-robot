"""Conditional denominators, source/version grouping, confirmed human metrics."""
import math
from collections import Counter
from .annotation import digest


def rate(num,den):return {'value':num/den if den else None,'numerator':num,'denominator':den}


def distribution(values):
    values=sorted(values);n=len(values)
    histogram=[]
    if n:
        step=max((values[-1]-values[0])/6,0.001)
        for i in range(6):
            low=values[0]+i*step;high=values[0]+(i+1)*step
            count=sum(low<=v and (v<high or i==5 and v<=high) for v in values)
            histogram.append({'low_ms':low,'high_ms':high,'count':count})
    return {'histogram':histogram,'sample_count':n,'average_ms':sum(values)/n if n else None,
            'p50_ms':values[max(0,math.ceil(n*.5)-1)] if n else None,
            'p95_ms':values[max(0,math.ceil(n*.95)-1)] if n else None,
            'p95_note':'小样本描述值，非稳定性能结论' if n<30 else 'nearest-rank；仍需结合实验条件'}


def group_summary(records):
    n=len(records);complete=[r for r in records if r['request_result']['complete']]
    parsed=[r for r in complete if r['parse_result']['passed']]
    schema=[r for r in parsed if r['schema_result']['passed']]
    accepted=[r for r in schema if r['validator_result']['valid']]
    annotations=[]
    for r in records:
        a=r.get('annotation')
        if a and a.get('confirmed') is True and a.get('source')=='local_human_review' and a.get('original_sha256')==digest(r['original_request']) and a.get('candidate_sha256')==digest(r['parsed_json']):annotations.append(a)
    evidence=[a['evidence_consistent'] for a in annotations if type(a.get('evidence_consistent')) is bool]
    dimensions=[v for a in annotations for v in a['semantic_dimensions'].values() if type(v) is bool]
    return {'samples':n,'request_success_rate':rate(len(complete),n),'json_parse_rate':rate(len(parsed),len(complete)),
            'schema_pass_rate':rate(len(schema),len(parsed)),'validator_acceptance_rate':rate(len(accepted),len(schema)),
            'human_evidence_consistency':rate(sum(evidence),len(evidence)),
            'semantic_accuracy':rate(sum(dimensions),len(dimensions)),
            'engineering_evidence_constraint_rate':rate(sum(r['evidence_result']['passed'] is True for r in parsed),len(parsed)),
            'latency':distribution([r['latency']['total_ms'] for r in records]),
            'fallback_count':sum(r['fallback_used'] for r in records),
            'safety_violation_count':sum(r['safety_result']['candidate_violation'] for r in records),
            'failure_counts':dict(Counter(r['request_result']['failure_kind'] for r in records if r['request_result']['failure_kind'])),
            'outcomes':dict(Counter(r['outcome'] for r in records)),
            'annotated_records':len(annotations)}


def aggregate(records):
    groups={}
    for r in records:
        key=(r['source'],r['model_name'],r['model_version'],r['prompt_version'],r['schema_version'],r['configuration_sha256'])
        groups.setdefault(key,[]).append(r)
    return {'groups':[{'source':k[0],'model_name':k[1],'model_version':k[2],'prompt_version':k[3],'schema_version':k[4],
                       'configuration_sha256':k[5],'metrics':group_summary(rows),
                       'categories':{cat:group_summary([r for r in rows if r['category']==cat]) for cat in sorted({r['category'] for r in rows})}}
                      for k,rows in groups.items()],
            'note':'REAL LLM / MOCK / RULES 及配置版本分别统计；ACCEPTED不等于人工确认或执行授权'}
