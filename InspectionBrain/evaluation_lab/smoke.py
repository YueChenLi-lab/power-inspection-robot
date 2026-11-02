"""Five-category REAL Ollama smoke. No fallback and no fabricated PASS."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import tempfile
from .service import EvaluationService
from .storage import Store

SMOKE_CASES=['T1','T5','T3','T4','T8']


def run(output,config=None):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('smoke report exists; choose a fresh output name')
    with tempfile.TemporaryDirectory(prefix='evaluation-real-smoke-') as folder:
        store=Store(Path(folder)/'lab.sqlite')
        try:
            service=EvaluationService(store,config)
            status=service.check_models()
            records=[service.evaluate({'case_id':case,'provider':'ollama','model':service.config.model}) for case in SMOKE_CASES]
            available=status['status']['connected'] and any(m['name']==service.config.model for m in status['status']['models'])
            passed=all(r['request_result']['complete'] and r['parse_result']['passed'] and r['schema_result']['passed'] and r['validator_result']['valid'] and not r['safety_result']['candidate_violation'] for r in records)
            result='BLOCKED' if not available else 'PASS' if passed else 'FAIL'
            report={'REAL_LLM_TEST':result,'requested_model':service.config.model,'model_service':status,'case_ids':SMOKE_CASES,
                    'records':records,'statistics':service.statistics(),'human_annotation_status':'PENDING',
                    'note':'不训练、不回退、不接硬件；PASS仅为这五类当前工程合同验收，不是人工语义准确率。'}
            with output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
            print(json.dumps({'REAL_LLM_TEST':result,'samples':len(records),'complete_responses':sum(r['request_result']['complete'] for r in records),'human_gold':'PENDING'},ensure_ascii=False))
            return {'PASS':0,'FAIL':1,'BLOCKED':2}[result]
        finally:store.close()


def main():
    parser=argparse.ArgumentParser(description='真实 Ollama 五类烟测，模型不可用则 BLOCKED')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    return run(args.output)


if __name__=='__main__':raise SystemExit(main())
