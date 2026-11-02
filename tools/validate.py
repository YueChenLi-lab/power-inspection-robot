"""Run both suites without hiding known baseline failures; preserve old reports."""
import argparse
from pathlib import Path
import subprocess
import sys
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--original-child',action='store_true');args=parser.parse_args()
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
                return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    results=[]
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'InspectionBrain')+os.pathsep+str(ROOT)
    commands=[([sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT),
              ([sys.executable,str(Path(__file__).resolve()),'--original-child'],ROOT/'InspectionBrain'),
              (['node','--test',*[str(p) for p in sorted((ROOT/'InspectionBrain/tests').glob('*.mjs'))]],ROOT/'InspectionBrain')]
    for command,cwd in commands:
        results.append(subprocess.run(command,cwd=cwd,env=env).returncode)
    print('new / original / node exit codes:',results)
    return 0 if all(r==0 for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
