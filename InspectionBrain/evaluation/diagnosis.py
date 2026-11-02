"""Classify evidence in existing private smoke reports without exposing prompts."""
from collections import Counter
from brain_v3.schema import schema_errors


def diagnose_row(row,index=0):
    result=row.get('result',row)
    diagnostics=row.get('diagnostics',{})
    candidate=result.get('model_candidate')
    if candidate is None and row.get('candidate_observed'):candidate=row.get('parsed_candidate')
    validation=result.get('validation') or {}
    status=result.get('status','unavailable')
    errors=validation.get('errors',[])
    kind=diagnostics.get('failure_kind')
    schema=schema_errors(candidate) if candidate is not None or diagnostics.get('json_parse_success') is True else None
    if schema:stage='schema'
    elif status=='validation_rejected':stage='validator'
    elif kind=='json_parse_failure':stage='json'
    elif kind in ('transport_failure','timeout','http_error','disabled','model_unavailable'):stage='provider'
    elif status in ('provider_unavailable','provider_error'):stage='provider_or_response_contract'
    elif status in ('validated_candidate','v2_only'):stage='accepted_non_executable'
    else:stage='unknown_requires_private_details'
    safe=result.get('v3') or result.get('fallback') or {}
    return {'sample_index':index,'status':status,'failure_stage':stage,'failure_kind':kind,
            'error':result.get('error'),'schema_errors':schema,'validator_errors':errors,
            'json_parse_success':diagnostics.get('json_parse_success'),
            'complete_response':diagnostics.get('complete_response'),
            'safety_guard_status':safe.get('status'),'fallback_used':result.get('fallback_used',False),
            'safety_note':'上游校验失败后空草案不代表SafetyGuard另有缺陷；不能从accepted=0推断根因。'}


def diagnose_report(data):
    rows=data.get('rows') if isinstance(data,dict) else data
    if not isinstance(rows,list):raise ValueError('smoke report must contain rows[]')
    reports=[diagnose_row(row,i+1) for i,row in enumerate(rows)]
    return {'samples':len(rows),'stages':dict(Counter(r['failure_stage'] for r in reports)),
            'rows':reports,'private_inputs_or_raw_outputs_included':False,
            'note':'仅根据该文件实际元数据分类；未知项保持unknown，不推测超时或语义错误。'}
