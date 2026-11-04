"""Read-only V2 fixture baseline for the V3 architecture report.

This is NOT the 10K/100K/1M parsed-event or MySQL benchmark. It does not create,
connect to, import into, migrate or modify any database. It writes audit artifacts
only, under docs/benchmarks/v3, and shuts down its owned loopback server.
"""
import argparse
import cProfile
import ctypes
from ctypes import wintypes
import hashlib
import importlib.metadata
import io
import json
import logging
import math
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app
from app.demo import ANOMALIES
from app.services.investigation import build, query
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)]


def memory():
    if sys.platform != 'win32':
        return {'working_set_bytes': None, 'process_peak_working_set_bytes': None}

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
            ['PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage']]
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not get_info(get_process(), ctypes.byref(counters), counters.cb):
        return {'working_set_bytes': None, 'process_peak_working_set_bytes': None, 'error': 'GetProcessMemoryInfo failed'}
    return {'working_set_bytes': counters.WorkingSetSize,
            'process_peak_working_set_bytes': counters.PeakWorkingSetSize}


def hashes():
    files = [p for directory in ['app', 'tests'] for p in (ROOT/directory).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/'config.py', ROOT/'requirements.txt']
    # Research/user data are never opened for writing by the harness.
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repetitions', type=int, default=60)
    parser.add_argument('--browser', action='store_true')
    args = parser.parse_args()
    if not 30 <= args.repetitions <= 200:
        parser.error('Choose 30–200 repetitions for this fixture baseline.')
    out = ROOT/'docs/benchmarks/v3'
    out.mkdir(parents=True, exist_ok=True)
    before = hashes()
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app()
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    dense = dict(start_time='2026-11-03T05:50:00Z', end_time='2026-11-03T07:50:00Z', resolution=60)
    cases = [('timeline_1h', '/api/v1/anomalies/timeline', {'range': '1h'}),
             ('timeline_24h', '/api/v1/anomalies/timeline', {'range': '24h'}),
             ('timeline_7d', '/api/v1/anomalies/timeline', {'range': '7d'}),
             ('timeline_30d', '/api/v1/anomalies/timeline', {'range': '30d'}),
             ('timeline_120_bins', '/api/v1/anomalies/timeline', dense),
             ('timeline_entity_filter', '/api/v1/anomalies/timeline', {'host': 'storage-02', 'service': 'storage'}),
             ('timeline_empty_result', '/api/v1/anomalies/timeline', {'q': '__no_matching_fixture__'}),
             ('workspace_1h', '/api/v1/investigation', {'range': '1h'}),
             ('workspace_120_bins', '/api/v1/investigation', dense),
             ('results_page', '/api/v1/anomalies', {'limit': 2}),
             ('evidence', '/api/v1/anomalies/LS-1041/evidence', {})]
    report = dict(scope='V2 synthetic fixture baseline only; not large-data or MySQL performance',
                  timestamp=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
                  python=sys.version, platform=platform.platform(),
                  packages={name: importlib.metadata.version(name) for name in ['Flask','tzdata']},
                  cardinalities={'raw_lines': None, 'parsed_events': None, 'detection_units': None,
                                 'anomaly_outputs': len(ANOMALIES), 'detectors': 4},
                  database={'connected': False, 'sql_execution_ms': None, 'database_size_bytes': None,
                            'explain': None, 'parsed_event_workloads_10k_100k_1m': 'not executed'},
                  conditions={'client': 'serial urllib HTTP over owned loopback Werkzeug threaded server',
                              'warmups_per_case': 5, 'repetitions': args.repetitions,
                              'cache': 'warm Python/templates/OS; API Cache-Control no-store; no DB or cold-cache run',
                              'latency_clock': 'perf_counter; HTTP request through body read; JSON decode outside timed interval',
                              'quantile': 'p50=median; p95=nearest rank ceil(.95*N); descriptive single-process baseline'}, cases=[])
    try:
        for name, path, params in cases:
            target = base+path+'?'+urlencode(params)
            latencies, sizes = [], []
            for repeat in range(5+args.repetitions):
                start = time.perf_counter()
                with urlopen(target, timeout=20) as response:
                    body = response.read()
                    if response.status != 200:
                        raise RuntimeError(f'{name}: HTTP {response.status}')
                elapsed = (time.perf_counter()-start)*1000
                payload = json.loads(body)
                if 'timeline' in payload:
                    assert sum(c['count'] for c in payload['timeline']['overall']) == payload['scope_count']
                    assert sum(c['count'] for row in payload['timeline']['lanes'] for c in row['cells']) == payload['scope_count']
                if repeat >= 5:
                    latencies.append(elapsed)
                    sizes.append(len(body))
            row = dict(name=name, path=path, params=params, p50_ms=statistics.median(latencies),
                       p95_ms=percentile(latencies,.95), min_ms=min(latencies), max_ms=max(latencies),
                       payload_bytes_min=min(sizes), payload_bytes_max=max(sizes), samples_ms=latencies,
                       sql_execution_ms=None, memory=memory())
            if 'timeline' in payload:
                row.update(bins=payload['timeline']['bins'], detector_rows=len(payload['timeline']['lanes']),
                           aggregate_cells=payload['timeline']['bins']*(1+len(payload['timeline']['lanes'])),
                           scope_anomaly_count=payload['scope_count'])
            report['cases'].append(row)
            print(json.dumps({k: row[k] for k in ['name','p50_ms','p95_ms','payload_bytes_max']}), flush=True)

        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(30):
            build(query(MultiDict()))
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(25)
        (out/'fixture-profile.txt').write_text(stream.getvalue(), encoding='utf-8')
        tracemalloc.start()
        build(query(MultiDict(dense)))
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        report['instrumented_memory'] = {'case': 'one fixture service build at 120 bins',
                                         'python_allocated_current_bytes': current, 'python_allocated_peak_bytes': peak,
                                         'note': 'tracemalloc Python allocations only; not RSS, DB memory or API peak'}
        report['process_memory_before_browser'] = memory()

        if args.browser:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':900})
                page.goto(base, wait_until='networkidle')
                browser_rows = []
                for name, params in [('workspace_1h', {'range':'1h'}), ('workspace_120_bins', dense)]:
                    target = '/api/v1/investigation?'+urlencode(params)
                    samples = page.evaluate('''async ({target, n}) => {
                        const data=await (await fetch(target)).json();
                        const result=[];
                        for(let i=0;i<n+5;i++) {
                            const start=performance.now();
                            document.getElementById('workspace-results').innerHTML=data.html;
                            initializeChart();
                            const committed=performance.now();
                            document.getElementById('workspace-results').getBoundingClientRect();
                            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
                            if(i>=5) result.push({dom_ms:committed-start,to_second_frame_ms:performance.now()-start});
                        }
                        return {samples:result,cells:document.querySelectorAll('[data-cell]').length,
                                dom_nodes:document.querySelectorAll('*').length,html_bytes:new TextEncoder().encode(data.html).length};
                    }''', {'target':target,'n':args.repetitions})
                    browser_rows.append(dict(name=name, cells=samples['cells'], dom_nodes=samples['dom_nodes'], html_bytes=samples['html_bytes'],
                        p50_dom_ms=statistics.median(s['dom_ms'] for s in samples['samples']),
                        p95_dom_ms=percentile([s['dom_ms'] for s in samples['samples']],.95),
                        p95_to_second_frame_ms=percentile([s['to_second_frame_ms'] for s in samples['samples']],.95),
                        samples=samples['samples']))
                report['browser'] = dict(engine='headless Edge '+browser.version, viewport=[1440,900], cases=browser_rows,
                    note='Cached fixture HTML replacement + chart setup; fetch excluded. Second RAF is a frame-scheduling proxy, not guaranteed paint completion. No browser peak-memory measurement.')
                browser.close()
        else:
            report['browser'] = {'status':'not measured'}
        after = hashes()
        assert before == after, 'Application/test/config/requirements files changed during read-only baseline.'
        report['source_integrity'] = {'unchanged':True, 'files':before}
        (out/'fixture-baseline.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Saved docs/benchmarks/v3/fixture-baseline.json; no database used.', flush=True)
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
