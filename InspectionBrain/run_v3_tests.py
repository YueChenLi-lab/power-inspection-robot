#!/usr/bin/env python3
"""Run all Python tests while preserving historical report artifacts.

Two legacy real-ASR tests normally overwrite their old reports. Redirect only
those report writes to v3-prefixed artifacts, without changing tests/expectations.
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
REDIRECTS = {"scoring_real_user_wav_http.json", "scoring_official_http_real_asr_demo.json"}


def main():
    redirected = []
    original_write = Path.write_text
    def preserve_report(path, text, *args, **kwargs):
        if path.parent.resolve() == (ROOT/"reports").resolve() and path.name in REDIRECTS:
            replacement = path.with_name("v3_legacy_test_"+path.name)
            redirected.append({"historical_report_preserved":str(path), "new_report":str(replacement)})
            return original_write(replacement, text, *args, **kwargs)
        return original_write(path, text, *args, **kwargs)
    with (ROOT/"reports/v3_python_tests.log").open("w", encoding="utf-8") as log:
        with patch.object(Path, "write_text", preserve_report):
            suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"), pattern="test_*.py")
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    report = {"python":sys.executable,"tests_run":result.testsRun,
              "passed":result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
              "failures":len(result.failures), "errors":len(result.errors), "skipped":len(result.skipped),
              "skip_reasons":[{"test":str(t),"reason":r} for t,r in result.skipped],
              "redirected_legacy_reports":redirected}
    (ROOT/"reports/v3_test_summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(report,ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":sys.exit(main())
