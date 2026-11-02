#!/usr/bin/env python3
"""Local-only evaluation / existing private smoke diagnosis. Never publishes."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'InspectionBrain'));sys.path.insert(0,str(ROOT))
from evaluation.dataset import DEFAULT_DATASET
from evaluation.diagnosis import diagnose_report
from evaluation.runners.local_evaluator import build_config,evaluate_run
from evaluation.runners.reports import atomic,encode


def main(argv=None):
    parser=argparse.ArgumentParser(description='InspectionBrain v3 serial local evaluation; no Web or hardware')
    parser.add_argument('--provider',choices=('ollama','mock','rules'),default='ollama')
    parser.add_argument('--category',choices=('all','terminology','correction','negation','relations','ambiguity','safety'),default='all')
    parser.add_argument('--case-id');parser.add_argument('--limit',type=int)
    parser.add_argument('--dataset',type=Path,default=DEFAULT_DATASET)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'.local-evaluation/qwen3-4b')
    parser.add_argument('--warmup',action='store_true');parser.add_argument('--timeout',type=float)
    parser.add_argument('--max-tokens',type=int);parser.add_argument('--verbose',action='store_true')
    parser.add_argument('--resume',type=Path);parser.add_argument('--pilot-run',type=Path)
    parser.add_argument('--diagnose-smoke',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.diagnose_smoke:
            report=diagnose_report(json.loads(args.diagnose_smoke.read_text()))
            args.output_dir.mkdir(parents=True,exist_ok=True)
            folder=Path(tempfile.mkdtemp(prefix='diagnosis-',dir=args.output_dir))
            atomic(folder/'smoke_diagnosis.json',encode(report))
            print(json.dumps({'diagnosis':str(folder/'smoke_diagnosis.json'),'samples':report['samples'],'stages':report['stages']},ensure_ascii=False));return 0
        if args.resume and (args.category!='all' or args.case_id or args.limit is not None or args.warmup):raise ValueError('resume uses frozen case selection; omit category/case-id/limit')
        config=build_config(args.provider,args.timeout,args.max_tokens)
        folder,status,rows=evaluate_run(config=config,dataset_path=args.dataset,output_dir=args.output_dir,category=args.category,case_id=args.case_id,
                                        limit=args.limit,warmup=args.warmup,resume=args.resume,pilot_run=args.pilot_run,verbose=args.verbose)
        metrics=json.loads((folder/'metrics.json').read_text())
        print(json.dumps({'run_dir':str(folder),'status':status['status'],'completed':len(rows),'sample_real_model_call_attempts':metrics['real_model_call_attempts'],
                          'real_model_call_attempts_including_warmup':metrics['real_model_call_attempts_including_warmup'],
                          'warmup_separate':(folder/'warmup.json').exists(),'blocker':status.get('blocker')},ensure_ascii=False))
        if status['status']=='INTERRUPTED':return 130
        if status['status']!='COMPLETED':return 2
        # Completion is not acceptance; failed checks remain in the report.
        return 0  # The run completed; quality/rejection metrics are separate, never implied PASS.
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({'error':str(exc),'result':'NOT_PASSED'},ensure_ascii=False),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
