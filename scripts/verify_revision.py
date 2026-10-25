"""Run revision checks without disguising missing optional dependencies as passes."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Require all dependencies and run the original pytest suite plus revision tests')
    parser.add_argument('--json-out', type=Path)
    args = parser.parse_args()
    modules = ['numpy','pandas','scipy','sklearn','pydantic','torch','pytest','fastapi','httpx','uvicorn']
    present = {name: importlib.util.find_spec(name) is not None for name in modules}
    report = {'python':sys.version, 'dependencies':present, 'mode':'full_pytest' if args.full else 'revision_unittest'}
    if args.full:
        missing = [name for name, ok in present.items() if not ok]
        if missing:
            report.update(status='BLOCKED', missing=missing)
            code = 2
        else:
            result = subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT)
            code = result.returncode
            report.update(status='PASS' if code == 0 else 'FAIL', returncode=code)
    else:
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'), pattern='test_*_revision.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        report.update(status='PASS_WITH_SKIPS' if result.skipped and result.wasSuccessful() else 'PASS' if result.wasSuccessful() else 'FAIL',
                      tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      skipped=[{'test':str(test),'reason':reason} for test,reason in result.skipped],
                      scope='revision regression tests only; does not certify HTTP, full pytest, external authenticated APIs, or all branches')
        code = 0 if result.wasSuccessful() else 1
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return code

if __name__ == '__main__':
    raise SystemExit(main())
