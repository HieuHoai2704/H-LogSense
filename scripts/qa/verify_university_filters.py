"""Post-restart filter matrix against independent real-BGL SQL facts.

Uses the dedicated release QA context. No dataset, job or schema is modified.
Only the 158 persisted anomaly facts are collected as a Python reference; log
truth uses COUNT/limited ID queries rather than loading the raw event corpus.
"""

import csv
import argparse
from datetime import datetime, timedelta
import io
import json
import re
from pathlib import Path
import time

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.extensions import db
from app.models import AnomalyOutput as A, DetectionUnit as U, DetectorRun as R
from app.models import Detector as D, LogEvent as E
from scripts.qa.verify_university_e2e import PRIVATE, REPORT, app_for, login, read, save
from scripts.run.mysql_runtime import owned_root, status


def instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def values(params, key):
    value = params.get(key, [])
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def reference(facts, params, *, selection):
    lower, upper = instant(params['start_time']), instant(params['end_time'])
    result = []
    for item in facts:
        if not lower <= item['timestamp'] < upper:
            continue
        if params.get('run_id') and str(item['run']) not in values(params, 'run_id'):
            continue
        if params.get('version_id') and str(item['version']) != str(params['version_id']):
            continue
        if params.get('host') and str(item['host']) not in values(params, 'host'):
            continue
        if params.get('severity') and item['priority'] not in values(params, 'severity'):
            continue
        if params.get('detector') and str(item['detector']) not in values(params, 'detector'):
            continue
        search = params.get('q', '').strip()
        # These are window units, not event units; there is no event-message
        # column in their search domain. Host/key are actual stored facts.
        if search and not (search in (item['host'] or '') or search in item['key']):
            continue
        if selection and params.get('selection_start'):
            if not instant(params['selection_start']) <= item['timestamp'] < instant(params['selection_end']):
                continue
            if params.get('selection_detector') and str(item['detector']) != str(params['selection_detector']):
                continue
        result.append(item)
    return result


def run(report_name='filter-matrix.json'):
    root = owned_root('.local/university-e2e-mysql')
    context = read(PRIVATE / 'context.json')
    assert status(root)['port'] == 13307, 'Dedicated QA port required'
    assert read(REPORT / 'restart.json')['status'] == 'PASS', 'Post-restart evidence required'
    if not re.fullmatch(r'[a-zA-Z0-9_-]+\.json', report_name):
        raise ValueError('Use a JSON report filename inside the release measurements directory.')
    destination = REPORT / report_name
    if destination.exists():
        raise ValueError('Retain existing matrix evidence; use a new report destination for a later audit.')
    app = app_for(root, context)
    started = time.perf_counter()
    cases, errors = [], []
    with app.app_context():
        client, _ = login(app, context)
        ds = context['dataset_id']
        with Session(db.engine) as session:
            rows = session.execute(select(A.id, A.priority, A.anchor_time, U.host,
                D.id, D.detector_key, R.id, R.version_id).join(
                    U, (U.dataset_id == A.dataset_id) & (U.id == A.unit_id)).join(
                    R, (R.dataset_id == A.dataset_id) & (R.id == A.run_id)).join(
                    D, D.id == R.detector_id).where(
                        A.dataset_id == ds, R.state == 'completed').order_by(A.id)).all()
            facts = [dict(id=r[0], priority=r[1], timestamp=r[2], host=r[3],
                          detector=r[4], key=r[5], run=r[6], version=r[7]) for r in rows]
            log_first, log_last = session.execute(select(func.min(E.timestamp), func.max(E.timestamp)).where(E.dataset_id == ds)).one()
            common_log_host, common_log_level = session.execute(select(E.host, E.severity).where(
                E.dataset_id == ds, E.host.is_not(None)).group_by(E.host, E.severity).order_by(func.count().desc()).limit(1)).one()
        assert len(facts) == 158, 'Unexpected frozen release anomaly cohort'
        base = {'source': 'db-' + str(ds), 'run_id': sorted({str(x['run']) for x in facts}),
                'start_time': (min(x['timestamp'] for x in facts) - timedelta(seconds=300)).isoformat(),
                'end_time': (max(x['timestamp'] for x in facts) + timedelta(seconds=300)).isoformat(),
                'timezone': 'utc', 'limit': 100}
        hosts = sorted({r['host'] for r in facts if r['host']})
        detectors = sorted({r['detector'] for r in facts})
        versions = sorted({r['version'] for r in facts})
        anchors = sorted({r['timestamp'] for r in facts})
        pivot = anchors[len(anchors) // 2]

        def get(path, params):
            begin = time.perf_counter()
            response = client.get(path, query_string=params)
            response.get_data()  # Include bounded stream consumption in timing.
            return response, time.perf_counter() - begin

        def anomaly_case(name, changes):
            params = dict(base, **changes)
            scope = reference(facts, params, selection=False)
            result = reference(facts, params, selection=True)
            scope_ids = {x['id'] for x in scope}
            expected_ids = {x['id'] for x in result}
            response, elapsed = get('/api/v1/investigation', params)
            assert response.status_code == 200, name + ': expected200'
            data = response.json
            assert data['scope_count'] == len(scope), name + ': globalcount'
            assert data['result_count'] == len(result), name + ': resultcount'
            assert sum(c['count'] for c in data['timeline']['overall']) == len(scope), name + ': timelinetotal'
            for cell in data['timeline']['overall']:
                lower, upper = instant(cell['start']), instant(cell['end'])
                expected = [x for x in scope if lower <= x['timestamp'] < upper]
                assert cell['count'] == len(expected), name + ': exactbincount'
                assert sum(cell['severity'].values()) == len(expected), name + ': severitytotal'
            table_ids = set()
            for page_number in range(1, data['page_count'] + 1):
                page = data if page_number == 1 else get('/api/v1/investigation', dict(params, page=page_number))[0].json
                ids = {int(x['id'][3:]) for x in page['events']}
                assert not table_ids & ids, name + ': tableduplicates'
                table_ids |= ids
            assert table_ids == expected_ids, name + ': alltableids'
            exported, csv_seconds = get('/api/v1/anomalies/export', params)
            assert exported.status_code == 200, name + ': csvstatus'
            csv_rows = list(csv.DictReader(io.StringIO(exported.text)))
            csv_ids = {int(row['id'][3:]) for row in csv_rows}
            assert csv_ids == expected_ids and len(csv_rows) == len(result), name + ': csvmembership'
            assert int(exported.headers['X-Result-Count']) == len(result), name + ': csvheader'
            assert data['coverage']['status'] == 'unknown', name + ': coverageclaim'
            if not result:
                assert not data['events'] and data['empty_reason'], name + ': emptytruth'
                assert all(cell['coverage'] != 'complete' for cell in data['timeline']['overall']), name + ': nofalsehealth'
            cases.append({'case': name, 'family': 'anomaly', 'status': 'PASS',
                'global_expected': len(scope_ids), 'selected_expected': len(expected_ids),
                'table_csv_exact_ids_match': True, 'all_time_bins_match_reference': True,
                'api_seconds_inprocess': elapsed, 'csv_seconds_inprocess': csv_seconds})
            return data, expected_ids

        matrix = [('all', {}), ('host_single', {'host': hosts[0]}),
                  ('host_OR_two', {'host': hosts[:2]}),
                  ('priority_high', {'severity': 'High'}),
                  ('priority_medium', {'severity': 'Medium'}),
                  ('priority_OR', {'severity': ['High', 'Medium']}),
                  ('detector_OR', {'detector': [str(v) for v in detectors]}),
                  ('time_start_inclusive', {'start_time': pivot.isoformat()}),
                  ('time_end_exclusive', {'end_time': pivot.isoformat()}),
                  ('time_boundary_empty', {'end_time': anchors[0].isoformat()}),
                  ('search_host_literal', {'q': hosts[0]}),
                  ('search_detector_literal', {'q': 'isolation_forest'}),
                  ('search_percent_underscore_literal_empty', {'q': '%_'}),
                  ('timezone_local', {'timezone': 'local'}),
                  ('timezone_dst_zone', {'timezone': 'America/New_York'})]
        matrix += [('detector_' + str(value), {'detector': str(value)}) for value in detectors]
        matrix += [('run_' + value, {'run_id': value}) for value in base['run_id']]
        matrix += [('version_' + str(value), {'version_id': str(value)}) for value in versions]
        item = facts[0]
        conjunction = {'host': item['host'], 'severity': item['priority'], 'detector': str(item['detector'])}
        matrix += [('AND_host_priority_detector', conjunction),
                   ('AND_impossible_priority_detector', {'detector': str(item['detector']),
                     'severity': 'Medium' if item['priority'] == 'High' else 'High'})]
        cell_start = item['timestamp']
        selected = {'host': item['host'], 'selection_start': cell_start.isoformat(),
                    'selection_end': (cell_start + timedelta(seconds=300)).isoformat()}
        matrix += [('selection_adds_to_host', selected),
                   ('selection_detector_adds_to_host', dict(selected, selection_detector=str(item['detector']))),
                   ('clear_selection_keeps_host', {'host': item['host']})]
        for name, changes in matrix:
            try:
                anomaly_case(name, changes)
            except Exception as error:
                errors.append({'case': name, 'error_type': type(error).__name__, 'message': str(error)[:160]})

        log_base = {'dataset_id': ds, 'start_time': log_first.isoformat(),
                    'end_time': (log_last + timedelta(seconds=1)).isoformat(), 'limit': 50, 'sort': 'asc'}

        def log_clauses(params):
            result = [E.dataset_id == ds, E.timestamp >= instant(params['start_time']), E.timestamp < instant(params['end_time'])]
            if params.get('host'): result.append(E.host.in_(values(params, 'host')))
            if params.get('severity'): result.append(E.severity.in_(values(params, 'severity')))
            if params.get('q'): result.append(func.locate(params['q'], E.message) > 0)
            return result

        def logs_case(name, changes):
            params = dict(log_base, **changes)
            with Session(db.engine) as session:
                clauses = log_clauses(params)
                expected_count = session.scalar(select(func.count()).select_from(E).where(*clauses))
                expected_ids = session.scalars(select(E.id).where(*clauses).order_by(E.timestamp, E.id).limit(50)).all()
            response, elapsed = get('/api/v1/logs', params)
            assert response.status_code == 200, name + ': status'
            data = response.json
            assert data['count'] == expected_count, name + ': sqlcount'
            assert [v['id'] for v in data['items']] == expected_ids, name + ': stablefirstpage'
            snapshot = dict(params, scope_token=data['scope_token'])
            timeline, timeline_seconds = get('/api/v1/logs/timeline', snapshot)
            assert timeline.status_code == 200, name + ': timelinestatus'
            assert timeline.json['count'] == expected_count == sum(c['event_count'] for c in timeline.json['bins']), name + ': timelinecount'
            assert all(c['coverage'] == 'unknown' for c in timeline.json['bins']), name + ': unknowncoverage'
            if expected_count <= 1000:
                csv_response, _ = get('/api/v1/logs/export', snapshot)
                assert csv_response.status_code == 200, name + ': csvstatus'
                csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
                with Session(db.engine) as session:
                    csv_expected = set(session.scalars(select(E.id).where(*log_clauses(params))))
                assert len(csv_rows) == expected_count and {int(r['id']) for r in csv_rows} == csv_expected, name + ': csvmembership'
            cases.append({'case': name, 'family': 'logs', 'status': 'PASS',
                          'sql_expected_count': expected_count, 'first_page_ids_match_sql': True,
                          'timeline_count_matches_sql': True, 'csv_tested': expected_count <= 1000,
                          'api_seconds_inprocess': elapsed, 'timeline_seconds_inprocess': timeline_seconds})
            return params, data

        log_matrix = [('logs_all', {}), ('logs_severity_INFO', {'severity': 'INFO'}),
                      ('logs_severity_ERROR_FATAL_OR', {'severity': ['ERROR', 'FATAL']}),
                      ('logs_host', {'host': common_log_host}),
                      ('logs_host_AND_severity', {'host': common_log_host, 'severity': common_log_level}),
                      ('logs_literal_percent_underscore', {'q': '%_'}),
                      ('logs_message_literal', {'q': 'error'}),
                      ('logs_start_boundary_excluded', {'start_time': (log_first + timedelta(seconds=1)).isoformat()})]
        for name, changes in log_matrix:
            try:
                logs_case(name, changes)
            except Exception as error:
                errors.append({'case': name, 'error_type': type(error).__name__, 'message': str(error)[:160]})
        _, first_page = logs_case('logs_cursor_reference_first_page', {})
        if first_page['next_cursor']:
            cursor_params = dict(log_base, scope_token=first_page['scope_token'], cursor=first_page['next_cursor'])
            response, elapsed = get('/api/v1/logs', cursor_params)
            with Session(db.engine) as session:
                second_ids = session.scalars(select(E.id).where(*log_clauses(log_base)).order_by(E.timestamp, E.id).offset(50).limit(50)).all()
            assert response.status_code == 200 and [v['id'] for v in response.json['items']] == second_ids, 'logs cursor page SQL mismatch'
            cases.append({'case': 'logs_cursor_second_page', 'family': 'logs', 'status': 'PASS',
                          'stable_ids_match_independent_sql': True, 'api_seconds_inprocess': elapsed})
        invalid = [
            ('logs_bad_cursor', '/api/v1/logs', dict(log_base, cursor='malformed-cursor'), 400),
            ('logs_snapshot_filter_changed', '/api/v1/logs', dict(log_base, scope_token=first_page['scope_token'], severity='FATAL'), 400),
            ('logs_other_dataset', '/api/v1/logs', dict(log_base, dataset_id=context['forbidden_dataset_id']), 403),
            ('anomaly_other_dataset', '/api/v1/investigation', dict(base, source='db-' + str(context['forbidden_dataset_id'])), 403),
            ('anomaly_invalid_detector', '/api/v1/investigation', dict(base, detector='invalid'), 400),
            ('anomaly_invalid_priority', '/api/v1/investigation', dict(base, severity='not-a-priority'), 400),
        ]
        for name, path, params, expected in invalid:
            response, elapsed = get(path, params)
            assert response.status_code == expected, name + ': status'
            assert isinstance(response.json.get('error'), dict), name + ': JSON error'
            cases.append({'case': name, 'family': 'validation_isolation', 'status': 'PASS',
                          'expected_http': expected, 'actual_http': response.status_code,
                          'api_seconds_inprocess': elapsed})
        db.engine.dispose()
    report = {'status': 'FAIL' if errors else 'PASS', 'phase': 'post-restart-only',
              'data': 'actual BGL 100K import in isolated QA MySQL on port13307',
              'anomaly_reference_facts': len(facts), 'reference_policy': 'Independent Python filtering of exact SQL anomaly facts; logs COUNT/limited IDs use separate SQL, never API query helpers.',
              'passed_cases': len(cases), 'failed_cases': len(errors), 'cases': cases, 'errors': errors,
              'wall_seconds': time.perf_counter() - started,
              'latency_note': 'Measured per-call Flask test client, including bounded payload consumption; not network latency or a production p95 SLO.',
              'writes': 'Session login only; no application records, job, schema or UI mutations.',
              'not_run': ['Native macOS', 'Model quality changes', 'Coverage proof beyond observed import']}
    save(destination, report)
    print(json.dumps({'status': report['status'], 'passed': len(cases), 'failed': len(errors),
                      'wall_seconds': report['wall_seconds'], 'errors': errors}), flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-name', default='filter-matrix.json')
    args = parser.parse_args()
    raise SystemExit(run(args.report_name))
