"""Emit a durable result summary; all tests use synthetic data and temporary roots."""
import json
import sys
import time
import unittest
from pathlib import Path

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    suite=unittest.defaultTestLoader.discover(str(root),pattern='test_*.py')
    start=time.perf_counter();result=unittest.TextTestRunner(verbosity=2).run(suite)
    summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skipped':len(result.skipped),'seconds':time.perf_counter()-start,
             'production_qq_test':False,'real_llm_calls':0,'real_tts_calls':0,
             'restart_test':'offline engine close/reopen and separate subprocess; not a production AstrBot restart'}
    out=Path(sys.argv[1]) if len(sys.argv)>1 else root/'test_results.json'
    out.write_text(json.dumps(summary,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
