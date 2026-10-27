"""Synthetic local benchmark. Never runs on or uploads data to production."""
import ctypes
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from astrbot_plugin_family_memory.engine import MemoryEngine
from astrbot_plugin_family_memory.tests.test_engine import fixture_config


def rss():
    if os.name=='nt':
        from ctypes import wintypes
        class PMC(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                      *[(name,ctypes.c_size_t) for name in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]]
        info=PMC();info.cb=ctypes.sizeof(info)
        ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
        handle=ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(PMC),wintypes.DWORD]
        ctypes.windll.psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
        if ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(info),info.cb):return info.WorkingSetSize
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform!='darwin' else 1)
    except ImportError:return None


def main():
    before=rss()
    with tempfile.TemporaryDirectory(prefix='family-memory-benchmark-') as tmp:
        root=Path(tmp);engine=MemoryEngine(root,fixture_config(retrieval_timeout_ms=200))
        owner=engine.policy.resolve('default','fixture-bot','owner-fixture')
        start=time.perf_counter()
        for i in range(1000):
            text=f'我们记录合成事件 synthetic_{i:04d} 的纸鹤展览，地点为测试展厅。'
            source=engine.capture(owner,'bench'+str(i),text,share=True)
            engine.remember(owner,text,[{'id':source,'quote':text}],shared=True,tags=[f'synthetic_{i:04d}','纸鹤'])
        write_seconds=time.perf_counter()-start
        cold=[];warm=[];injection=[]
        for i in range(100):
            q=f'synthetic_{i:04d}'
            t=time.perf_counter();engine.search(owner,q);cold.append((time.perf_counter()-t)*1000)
            t=time.perf_counter();engine.search(owner,q);warm.append((time.perf_counter()-t)*1000)
            injection.append(engine.token_budget.count(engine.injection(owner,q)))
        stats=engine.stats();after=rss()
        result={'environment':{'os':platform.platform(),'python':platform.python_version(),'location':'local Windows development machine, NOT Azure production'},
                'synthetic_memories':1000,'write_seconds':write_seconds,
                'cold_ms':{'p50':statistics.median(cold),'p95':sorted(cold)[94],'max':max(cold)},
                'cached_ms':{'p50':statistics.median(warm),'p95':sorted(warm)[94],'max':max(warm)},
                'rss_before_bytes':before,'rss_after_bytes':after,'rss_delta_bytes':after-before if before and after else None,
                'directory_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
                'index_main_bytes':stats['database_bytes'],
                'injection_units':{'mode':stats['token_counter'],'median':statistics.median(injection),'maximum':max(injection)},
                'cache_hits':stats['counters'].get('cache_hits',0),'network_api_calls':0,
                'disclaimer':'Local synthetic measurements; not model tokenizer measurements, not production latency or billed token savings.'}
        engine.close()
        print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
