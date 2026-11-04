"""Shared REST scope, UTC aggregate, coverage and evidence correctness."""
import csv
import io
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict

from app import create_app
from app.demo import ANOMALIES
from app.services.investigation import build, query, records


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def get(self, path='/api/v1/investigation', **params):
        response = self.client.get(path, query_string=params)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        return response.json

    def test_aggregate_does_not_ship_evidence_or_raw_logs(self):
        data = self.get('/api/v1/anomalies/timeline')
        self.assertNotIn('events', data)
        self.assertNotIn("'raw_log':", str(data))
        self.assertEqual(sum(c['count'] for c in data['timeline']['overall']), 6)
        self.assertEqual(sum(c['count'] for r in data['timeline']['lanes'] for c in r['cells']), 6)

    def test_and_between_or_within_dimensions(self):
        data = self.get(host=['storage-02', 'gateway-01'], severity=['High', 'Critical'])
        self.assertCountEqual([e['id'] for e in data['events']], ['LS-1041', 'LS-1040'])
        self.assertEqual(data['scope_count'], 2)
        self.assertEqual(sum(c['count'] for c in data['timeline']['overall']), 2)

    def test_facets_exclude_only_their_own_dimension(self):
        data = self.get(host=['storage-02'], service=['api'])
        self.assertEqual(data['result_count'], 0)
        hosts = {f['value']: f['count'] for f in data['facets']['host']}
        services = {f['value']: f['count'] for f in data['facets']['service']}
        self.assertEqual(hosts['gateway-01'], 2)
        self.assertEqual(hosts['storage-02'], 0)
        self.assertEqual(services['storage'], 2)
        self.assertEqual(services['api'], 0)

    def test_exact_half_open_boundary_and_partial_edge_bins(self):
        a = self.get(start_time='2026-11-03T07:00:00Z', end_time='2026-11-03T07:09:55Z')
        b = self.get(start_time='2026-11-03T07:09:55Z', end_time='2026-11-03T07:10:01Z')
        self.assertEqual(a['result_count'], 0)
        self.assertEqual([e['id'] for e in b['events']], ['LS-1038'])
        self.assertTrue(b['timeline']['overall'][0]['partial_bin'])
        self.assertEqual(b['timeline']['overall'][0]['start'], b['state']['start_time'])

    def test_cell_selection_matches_table_export_and_preserves_global_scope(self):
        data = self.get(host=['storage-02'])
        row = next(r for r in data['timeline']['lanes'] if r['id'] == 'isolation-forest')
        for cell in row['cells']:
            if not cell['count']:
                continue
            params = dict(host='storage-02', selection_start=cell['start'], selection_end=cell['end'], selection_detector=row['id'])
            selected = self.get(**params)
            self.assertEqual(selected['scope_count'], 2)
            self.assertEqual(selected['result_count'], cell['count'])
            response = self.client.get('/api/v1/anomalies/export', query_string=params)
            exported = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
            self.assertEqual([e['id'] for e in selected['events']], [e['id'] for e in exported])

    def test_clearing_selection_keeps_other_filters(self):
        params = dict(host='storage-02', severity='High')
        data = self.get(**params, selection_start='2026-11-03T07:25:00Z', selection_end='2026-11-03T07:30:00Z')
        cleared = self.get(**params)
        self.assertEqual(data['events'], cleared['events'])
        self.assertEqual(cleared['state']['host'], ['storage-02'])

    def test_timezone_only_changes_labels_and_dst_fold_has_offsets(self):
        utc = self.get(timezone='utc')
        local = self.get(timezone='local')
        self.assertEqual([e['id'] for e in utc['events']], [e['id'] for e in local['events']])
        self.assertNotEqual(utc['events'][0]['display_time'], local['events'][0]['display_time'])
        fold = self.get(timezone='America/New_York', start_time='2026-11-01T05:00:00Z', end_time='2026-11-01T07:00:00Z', resolution=3600)
        labels = [c['full_label'] for c in fold['timeline']['overall']]
        self.assertIn('-0400', labels[0])
        self.assertIn('-0500', labels[1])

    def test_utc_midnight_does_not_use_negative_hour_labels(self):
        data = self.get(timezone='utc', start_time='2026-11-02T23:30:00Z', end_time='2026-11-03T00:30:00Z')
        self.assertIn('02 Nov', data['range_label'])
        self.assertIn('03 Nov', data['range_label'])

    def test_adaptive_resolution_and_manual_bin_limit(self):
        short = self.get(range='15m', width=700)
        long = self.get(range='30d', width=700)
        self.assertLess(short['timeline']['resolution'], long['timeline']['resolution'])
        self.assertLessEqual(long['timeline']['bins'], 120)
        response = self.client.get('/api/v1/anomalies/timeline?range=30d&resolution=60')
        self.assertEqual(response.status_code, 400)

    def test_complete_zero_missing_partial_empty_and_unprocessed_differ(self):
        zero = self.get(q='no-matching-event')
        self.assertEqual(zero['coverage']['status'], 'complete')
        self.assertEqual(zero['result_count'], 0)
        missing = self.get(start_time='2026-11-02T00:00:00Z', end_time='2026-11-02T01:00:00Z')
        self.assertEqual(missing['coverage']['status'], 'missing')
        partial = self.get(source='partial')
        self.assertEqual(partial['coverage']['status'], 'partial')
        self.assertTrue(any(c['coverage'] == 'missing' for c in partial['timeline']['overall']))
        self.assertEqual(self.get(source='empty')['coverage']['status'], 'no_data')
        self.assertEqual(self.get(source='unprocessed')['coverage']['status'], 'unprocessed')
        self.assertIsNone(partial['coverage']['last_processed'])
        self.assertIsNone(partial['coverage']['raw_log_count'])

    def test_priority_not_the_largest_raw_score(self):
        samples = [dict(ANOMALIES[0], score=1), dict(ANOMALIES[0], id='low', severity='Low', score=99)]
        with patch('app.services.investigation.ANOMALIES', samples):
            data = build(query(MultiDict()))
            critical = next(c for c in data['timeline']['overall'] if c['count'])
            self.assertEqual(critical['priority'], 4)
            self.assertEqual(critical['count'], 2)
            self.assertEqual(critical['severity']['Low'], 1)

    def test_search_scope_is_shared_with_csv(self):
        data = self.get(q='timeout', service='api')
        export = self.client.get('/api/v1/anomalies/export?q=timeout&service=api')
        rows = list(csv.DictReader(io.StringIO(export.get_data(as_text=True))))
        self.assertEqual([e['id'] for e in data['events']], [e['id'] for e in rows])
        self.assertEqual(len(rows), 1)

    def test_pagination_does_not_limit_export_or_overview(self):
        data = self.get(limit=1, page=2)
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['result_count'], 6)
        self.assertEqual(data['page_count'], 6)
        export = self.client.get('/api/v1/anomalies/export?limit=1&page=2')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(export.get_data(as_text=True))))), 6)

    def test_api_invalid_values_are_errors_not_silent_defaults(self):
        cases = ['host=unknown', 'source=bgl', 'timezone=Moon', 'mode=other', 'sort=bad', 'range=custom',
                 'limit=101', 'width=-1', 'start_time=2026-01-01T00:00:00',
                 'selection_start=2020-01-01T00:00:00Z&selection_end=2020-01-02T00:00:00Z',
                 'selection_detector=unknown', 'start_time=bad&end_time=bad', 'q='+'x'*201]
        for qs in cases:
            with self.subTest(qs=qs[:80]):
                response = self.client.get('/api/v1/anomalies?'+qs)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json['error']['code'], 'invalid_query')

    def test_evidence_and_related_records_belong_to_selected_identity(self):
        data = self.get('/api/v1/anomalies/LS-1041')['event']
        self.assertEqual(data['host'], 'storage-02')
        self.assertIn('318', data['actual'])
        self.assertIn('[DEMO]', data['raw_log'])
        self.assertEqual([e['id'] for e in data['related_events']], ['LS-1038'])
        self.assertIsNone(data['model_version'])
        self.assertEqual(self.client.get('/api/v1/anomalies/LS-1041?source=empty').status_code, 404)

    def test_missing_optional_evidence_is_not_invented(self):
        sample = dict(ANOMALIES[0], score=None, actual=None, typical=None)
        with patch('app.services.investigation.ANOMALIES', [sample]):
            data = self.get('/api/v1/anomalies/LS-1042')['event']
            self.assertIsNone(data['score'])
            self.assertIsNone(data['actual'])
            self.assertIsNone(data['model_version'])

    def test_revision_conflict_and_missing_identity(self):
        self.assertEqual(self.client.get('/api/v1/anomalies/export?revision=old').status_code, 409)
        self.assertEqual(self.client.get('/api/v1/anomalies/unknown').status_code, 404)

    def test_csv_formula_guard_and_quoting(self):
        with patch('app.services.investigation.ANOMALIES', [dict(ANOMALIES[0], message='=cmd,"quoted"\nnew line')]):
            response = self.client.get('/api/v1/anomalies/export')
            row = next(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
            self.assertEqual(row['message'], '\'=cmd,"quoted"\nnew line')
            self.assertEqual(row['synthetic'], 'True')

    def test_presentation_has_no_unescaped_query_or_evidence(self):
        page = self.client.get('/?q=%3Cscript%3Ealert(1)%3C/script%3E')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn('<script>alert(1)</script>', page.get_data(as_text=True))
        self.assertNotIn('raw_log', page.get_data(as_text=True))

    def test_full_fragment_and_composite_api_match(self):
        url = '/?host=storage-02&severity=High'
        page = self.client.get(url)
        fragment = self.client.get(url, headers={'X-Workspace-Fragment': '1'})
        api = self.get(host='storage-02', severity='High')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(fragment.json['state'], api['state'])
        self.assertEqual(fragment.json['events'], api['events'])
        self.assertEqual(page.get_data(as_text=True).count('data-row-id='), 1)

    def test_drawable_width_changes_bin_budget(self):
        narrow = self.get('/api/v1/anomalies/timeline', range='30d', width=240)
        wide = self.get('/api/v1/anomalies/timeline', range='30d', width=1400)
        self.assertGreater(narrow['timeline']['resolution'], wide['timeline']['resolution'])
        self.assertLessEqual(narrow['timeline']['bins'], 120)

    def test_multiple_detector_filters_and_zero_cell_selection(self):
        data = self.get(detector=['error-burst', 'timeout-frequency'])
        self.assertEqual(data['scope_count'], 2)
        self.assertCountEqual([r['id'] for r in data['timeline']['lanes']], ['error-burst', 'timeout-frequency'])
        zero = self.get(selection_start='2026-11-03T06:50:00Z', selection_end='2026-11-03T06:55:00Z')
        self.assertEqual(zero['result_count'], 0)
        self.assertEqual(zero['scope_count'], 6)

    def test_volume_legend_contains_each_observed_count(self):
        samples = [dict(ANOMALIES[0], id=f'bulk-{i}') for i in range(96)] + [ANOMALIES[-1]]
        with patch('app.services.investigation.ANOMALIES', samples):
            data = build(query(MultiDict()))
            legend = data['timeline']['volume_scale']
            for cell in data['timeline']['overall']:
                if cell['count']:
                    step = next(s for s in legend if s['band'] == cell['volume'])
                    self.assertLessEqual(step['lower'], cell['count'])
                    self.assertGreaterEqual(step['upper'], cell['count'])


if __name__ == '__main__':
    unittest.main()
