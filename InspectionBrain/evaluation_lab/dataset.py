"""Independent development cases; pending expectations are never model prompts."""
import json
from pathlib import Path

DATASET_PATH=Path(__file__).with_name('datasets')/'electrical_semantic_cases.json'


def load_cases(path=DATASET_PATH):
    cases=json.loads(Path(path).read_text(encoding='utf-8'))['cases']
    required={'case_id','category','original_request','expected','must_preserve','must_not','annotation_status','annotator','notes'}
    if any(not required<=c.keys() for c in cases):raise ValueError('invalid dataset contract')
    if len({c['case_id'] for c in cases})!=len(cases):raise ValueError('duplicate case ID')
    return cases
