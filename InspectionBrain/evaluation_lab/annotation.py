"""Explicit local human confirmation; no model-generated reference answers."""
import hashlib
import json
from datetime import datetime,timezone

DIMENSIONS={'intents','equipment_relations','numeric_relations','negations','self_corrections','temporal_constraints','task_dependencies'}


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()


def annotate(store,eid,payload):
    allowed={'annotator','confirmed','evidence_consistent','semantic_dimensions','notes'}
    if set(payload)-allowed:raise ValueError('unknown annotation field')
    if payload.get('confirmed') is not True:raise ValueError('explicit human confirmation required')
    actor=payload.get('annotator')
    if not isinstance(actor,str) or not actor.strip() or len(actor)>120:raise ValueError('annotator label required')
    evidence=payload.get('evidence_consistent')
    if evidence is not None and type(evidence) is not bool:raise ValueError('evidence_consistent must be bool or null')
    dimensions=payload.get('semantic_dimensions',{})
    if not isinstance(dimensions,dict) or not dimensions.keys()<=DIMENSIONS or any(v is not None and type(v) is not bool for v in dimensions.values()):raise ValueError('invalid semantic dimensions')
    if evidence is None and not any(type(v) is bool for v in dimensions.values()):raise ValueError('at least one reviewed dimension required')
    notes=payload.get('notes','')
    if not isinstance(notes,str) or len(notes)>2000:raise ValueError('notes must be <=2000 characters')
    record=store.get(eid)
    if not record['parse_result']['passed']:raise ValueError('no parsed candidate to annotate')
    return store.annotate(eid,{'annotator':actor.strip(),'confirmed':True,'evidence_consistent':evidence,
                             'semantic_dimensions':dimensions,'notes':notes,'source':'local_human_review',
                             'original_sha256':digest(record['original_request']),'candidate_sha256':digest(record['parsed_json']),
                             'timestamp':datetime.now(timezone.utc).isoformat()})
