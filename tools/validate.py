"""Run both suites without hiding known baseline failures; preserve old reports."""
import argparse
from pathlib import Path
import subprocess
import sys
import os
import tempfile
import unittest
import json
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original-child',action='store_true');parser.add_argument('--asset-policy',choices=('strict','skip-missing'),default='strict');parser.add_argument('--summary',type=Path);args=parser.parse_args()
    if args.original_child:
        sys.path.insert(0,str(ROOT/'InspectionBrain'))
        original_write=Path.write_text
        # Existing optional real-ASR tests write historical report names. Redirect
        # report writes only, never alter test expectations or fixture reads.
        with tempfile.TemporaryDirectory(prefix='brain-regression-reports-') as tmp:
            def preserve(path,*a,**kw):
                if path.parent.resolve()==ROOT/'InspectionBrain/reports':path=Path(tmp)/path.name
                return original_write(path,*a,**kw)
            with patch.object(Path,'write_text',preserve):
                suite=unittest.defaultTestLoader.discover(str(ROOT/'InspectionBrain/tests'))
                missing=[]
                if args.asset_policy=='skip-missing':
                    sys.path.insert(0,str(ROOT))
                    from tools.test_assets import apply_asset_policy
                    missing=apply_asset_policy(suite)
                    for row in missing:print('::warning::'+row['test']+' missing '+row['asset'])
                result=unittest.TextTestRunner(verbosity=2).run(suite)
                summary={'tests_run':result.testsRun,'passed':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
                         'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
                         'skip_reasons':[{'test':str(t),'reason':reason} for t,reason in result.skipped],
                         'missing_historical_assets':missing,'asset_policy':args.asset_policy}
                if args.summary:
                    args.summary.parent.mkdir(parents=True,exist_ok=True)
                    args.summary.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
                return 0 if result.wasSuccessful() and result.testsRun>=100 else 1
    results=[]
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'InspectionBrain')+os.pathsep+str(ROOT)
    commands=[([sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT),
              ([sys.executable,str(Path(__file__).resolve()),'--original-child'],ROOT/'InspectionBrain'),
              (['node','--test',*[str(p) for p in sorted((ROOT/'InspectionBrain/tests').glob('*.mjs'))]],ROOT/'InspectionBrain'),
              (['node','--test',str(ROOT/'tests/test_evaluation_lab_frontend.mjs')],ROOT)]
    for command,cwd in commands:
        results.append(subprocess.run(command,cwd=cwd,env=env).returncode)
    print('runtime / original / original Node / Evaluation Lab UI exit codes:',results)
    return 0 if all(r==0 for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
