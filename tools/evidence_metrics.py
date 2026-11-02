"""Independent evidence-only checks; does not call SemanticValidator.valid.

This measures fidelity to deterministic text evidence, not real-world facts or
semantic accuracy. Intent/DAG/draft policy is deliberately outside this metric.
"""

def check_evidence(candidate, evidence):
    errors=[]
    if not isinstance(candidate,dict) or not isinstance(evidence,dict):
        return {'passed':False,'errors':['evidence_object_unavailable']}
    text=evidence['original_request']
    if candidate.get('original_request')!=text:errors.append('original_request_changed')
    rows=candidate.get('source_spans')
    if not isinstance(rows,list):return {'passed':False,'errors':errors+['source_spans_missing']}
    spans={}
    for row in rows:
        if not isinstance(row,dict):errors.append('invalid_span');continue
        sid,start,end=row.get('span_id'),row.get('start'),row.get('end')
        if not isinstance(sid,str) or sid in spans:errors.append('invalid_or_duplicate_span_id');continue
        spans[sid]=row
        if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text) or text[start:end]!=row.get('quote'):
            errors.append('span_does_not_locate_in_original')
    for row in evidence['source_spans']:
        if spans.get(row['span_id'])!=row:errors.append('anchored_span_changed')
    for field in ('equipment_entities','metric_entities','temporal_constraints','negations','self_corrections','conditions'):
        if candidate.get(field)!=evidence[field]:errors.append('evidence_constraint_changed:'+field)
    def refs(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('source_span_ids','scope_span_ids'):
                    if not isinstance(item,list) or any(not isinstance(s,str) or s not in spans for s in item):errors.append('unknown_span_reference')
                else:refs(item)
        elif isinstance(value,list):
            for item in value:refs(item)
    refs(candidate)
    return {'passed':not errors,'errors':sorted(set(errors))}
