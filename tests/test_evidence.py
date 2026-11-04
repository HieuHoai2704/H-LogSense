"""Evidence identity, availability, read policy, redaction and bounded context."""
import json
import unittest
from unittest.mock import patch

from app import create_app
from app.demo import ANOMALIES
from app.services.redaction import redact


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def evidence(self, identity='LS-1042', **params):
        response = self.client.get(f'/api/v1/anomalies/{identity}/evidence', query_string=params)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:500])
        return response.json

    def test_identity_raw_provenance_and_absent_root_cause(self):
        data = self.evidence()
        self.assertEqual(data['anomaly']['host'], 'compute-07')
        self.assertEqual(data['anomaly']['timestamp'], '2026-11-03T07:32:08Z')
        self.assertEqual(data['raw_event']['provenance']['event_reference'], 'LS-1042')
        self.assertIsNone(data['raw_event']['provenance']['source_file'])
        self.assertEqual(data['raw_event']['provenance']['parsing_status'], 'not_run')
        self.assertFalse(data['raw_event']['provenance']['original_log_available'])
        self.assertIsNone(data['summary']['root_cause'])
        self.assertEqual(data['summary']['hypotheses'], [])

    def test_reference_is_not_a_threshold_and_missing_rule_is_explicit(self):
        evidence = self.evidence()['detector_evidence']
        self.assertEqual(evidence['kind'], 'rule')
        self.assertEqual(evidence['observed_value'], '42 errors / min')
        self.assertEqual(evidence['reference_statistics'], '3 errors / min')
        self.assertIsNone(evidence['configured_threshold'])
        self.assertIsNone(evidence['observation_window'])
        self.assertIsNone(evidence['rule_id'])
        self.assertIn('Explanation unavailable', evidence['explanation_status'])

    def test_isolation_forest_has_no_probability_importance_or_invented_direction(self):
        evidence = self.evidence('LS-1041')['detector_evidence']
        self.assertEqual(evidence['kind'], 'ml')
        self.assertEqual(evidence['method'], 'Isolation Forest')
        self.assertEqual(evidence['score'], 84)
        for field in ['model_name', 'model_version', 'model_run_id', 'feature_schema', 'feature_evidence', 'score_direction']:
            self.assertIsNone(evidence[field])
        self.assertIsNone(evidence['explanation'])
        self.assertIn('Do not compare scores', evidence['score_interpretation'])

    def test_supplied_versions_map_to_correct_detector_without_cross_mapping(self):
        rule = dict(ANOMALIES[0], rule_id='rule-test', rule_version='v2', threshold=10)
        model = dict(ANOMALIES[1], model_name='model-test', model_version='v3', model_run_id='run-test',
                     feature_schema=['count'], feature_evidence={'count': 12}, score_direction='lower_is_more_unusual')
        with patch('app.services.investigation.ANOMALIES', [rule, model]):
            a = self.evidence()['detector_evidence']
            b = self.evidence('LS-1041')['detector_evidence']
            self.assertEqual((a['rule_id'], a['rule_version'], a['configured_threshold']), ('rule-test', 'v2', 10))
            self.assertEqual((b['model_name'], b['model_version']), ('model-test', 'v3'))
            self.assertEqual(b['feature_evidence'], {'count': 12})
            self.assertIsNone(a['model_version'])
            self.assertIsNone(b['rule_version'])

    def test_scope_navigation_spans_result_pages(self):
        first = self.evidence(limit=1)
        self.assertIsNone(first['navigation']['previous_id'])
        self.assertEqual(first['navigation']['next_id'], 'LS-1041')
        middle = self.evidence('LS-1041', limit=1, page=4)
        self.assertEqual(middle['navigation']['previous_id'], 'LS-1042')
        self.assertEqual(middle['navigation']['next_id'], 'LS-1040')

    def test_navigation_respects_filters_and_selected_interval(self):
        data = self.evidence('LS-1041', host='storage-02')
        self.assertEqual(data['navigation']['next_id'], 'LS-1038')
        self.assertIsNone(data['navigation']['previous_id'])
        one = self.evidence(selection_start='2026-11-03T07:30:00Z', selection_end='2026-11-03T07:35:00Z', selection_detector='error-burst')
        self.assertIsNone(one['navigation']['next_id'])
        outside = self.evidence('LS-1038', severity='High')
        self.assertFalse(outside['navigation']['in_result_scope'])
        self.assertIsNone(outside['navigation']['next_id'])

    def test_related_reasons_source_window_and_global_filter_independence(self):
        data = self.evidence('LS-1041', severity='High')['related_events']
        self.assertEqual([e['id'] for e in data['items']], ['LS-1038'])
        self.assertIn('Same host', data['items'][0]['relationship_reasons'])
        self.assertIn('Before detection', data['items'][0]['relationship_reasons'])
        narrow = self.evidence('LS-1041', context_seconds=60)['related_events']
        self.assertEqual(narrow['items'], [])

    def test_before_after_and_same_service_are_real_relationships(self):
        before = self.evidence(relation='before')['related_events']['items']
        self.assertEqual([e['id'] for e in before], ['LS-1041', 'LS-1040', 'LS-1039', 'LS-1038'])
        after = self.evidence('LS-1037', relation='after', context_seconds=3600)['related_events']['items']
        self.assertEqual(len(after), 5)
        service = self.evidence('LS-1040', relation='same_service', context_seconds=3600)['related_events']['items']
        self.assertEqual([e['id'] for e in service], ['LS-1037'])

    def test_signed_keyset_pagination_has_no_duplicates(self):
        args = dict(relation='before', context_limit=1)
        first = self.evidence(**args)['related_events']
        seen = [first['items'][0]['id']]
        while first['has_more']:
            first = self.evidence(**args, context_cursor=first['next_cursor'])['related_events']
            seen.extend(e['id'] for e in first['items'])
        self.assertEqual(seen, ['LS-1041', 'LS-1040', 'LS-1039', 'LS-1038'])
        self.assertEqual(len(seen), len(set(seen)))

    def test_cursor_tampering_cross_source_and_changed_window_are_rejected(self):
        cursor = self.evidence(relation='before', context_limit=1)['related_events']['next_cursor']
        cases = [dict(context_cursor=cursor+'broken'), dict(context_cursor=cursor, source='partial'),
                 dict(context_cursor=cursor, context_seconds=60)]
        for params in cases:
            query = dict(relation='before', context_limit=1) | params
            response = self.client.get('/api/v1/anomalies/LS-1042/evidence', query_string=query)
            self.assertEqual(response.status_code, 400)

    def test_raw_redacted_before_chunking_and_raw_payload_is_bounded(self):
        text = 'A'*2040+' password=private-cross-boundary '+'B'*5000
        with patch('app.services.investigation.ANOMALIES', [dict(ANOMALIES[0], raw_log=text)]):
            data = self.evidence()
            self.assertEqual(len(data['raw_event']['page']['text']), 2048)
            self.assertTrue(data['availability']['raw_page_truncated'])
            second = self.client.get('/api/v1/anomalies/LS-1042/evidence/raw?raw_offset=2048').json['raw_event']
            combined = data['raw_event']['page']['text']+second['text']
            self.assertNotIn('private-cross-boundary', combined)
            self.assertIn('[REDACTED]', combined)

    def test_html_log_is_text_and_secrets_redacted_in_every_read_surface(self):
        raw = '<img src=x onerror=alert(1)> password=hunter api_key=private Authorization: Bearer abcd.efgh email=person@example.com'
        sample = dict(ANOMALIES[0], message=raw, raw_log=raw, parsed_attributes={'token': 'secret', 'email': 'person@example.com'})
        with patch('app.services.investigation.ANOMALIES', [sample]):
            for path in ['/api/v1/anomalies/LS-1042/evidence', '/api/v1/anomalies/LS-1042/evidence/raw',
                         '/api/v1/anomalies/LS-1042/evidence/export', '/api/v1/anomalies/LS-1042', '/api/v1/anomalies/export']:
                body = self.client.get(path).get_data(as_text=True)
                for private in ['hunter', 'abcd.efgh', 'person@example.com', '"token": "secret"']:
                    self.assertNotIn(private, body, path)
            self.assertIn('<img', self.evidence()['raw_event']['page']['text'])

    def test_malformed_optional_raw_and_missing_evidence(self):
        sample = dict(ANOMALIES[0], raw_log={'unexpected': ['not', 'a', 'string']}, score=None, actual=None, typical=None)
        with patch('app.services.investigation.ANOMALIES', [sample]):
            data = self.evidence()
            self.assertIn('unexpected', data['raw_event']['page']['text'])
            self.assertIsNone(data['detector_evidence']['observed_value'])
            self.assertIsNone(data['detector_evidence']['score'])
        with patch('app.services.investigation.ANOMALIES', [dict(ANOMALIES[0], raw_log=b'invalid utf8: \xff')]):
            self.assertIn('\ufffd', self.evidence()['raw_event']['page']['text'])

    def test_large_attribute_and_feature_fields_have_explicit_preview_limits(self):
        sample = dict(ANOMALIES[1], parsed_attributes={'long': 'x'*100000}, feature_evidence={'long': 'y'*100000})
        with patch('app.services.investigation.ANOMALIES', [sample]):
            data = self.evidence('LS-1041')
            self.assertEqual(data['availability']['parsed_fields'], 'truncated')
            self.assertTrue(data['availability']['feature_evidence_truncated'])
            self.assertLess(len(json.dumps(data)), 25000)

    def test_access_denial_is_enforced_for_all_anomaly_surfaces_and_page(self):
        self.app.config['DEMO_READ_ENABLED'] = False
        paths = ['/', '/api/v1/investigation', '/api/v1/anomalies', '/api/v1/anomalies/export',
                 '/api/v1/anomalies/timeline', '/api/v1/anomalies/LS-1042', '/api/v1/anomalies/LS-1042/evidence',
                 '/api/v1/anomalies/LS-1042/related', '/api/v1/anomalies/LS-1042/evidence/raw', '/api/v1/anomalies/LS-1042/evidence/export']
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403, path)
            self.assertNotIn('compute-07', response.get_data(as_text=True))

    def test_dataset_isolation_and_per_source_read_policy(self):
        response = self.client.get('/api/v1/anomalies/LS-1042/evidence?source=empty')
        self.assertEqual(response.status_code, 404)
        self.app.config['PUBLIC_DEMO_SOURCES'] = ('demo',)
        for suffix in ['/evidence', '/related', '/evidence/raw', '/evidence/export']:
            response = self.client.get('/api/v1/anomalies/LS-1042'+suffix+'?source=partial')
            self.assertEqual(response.status_code, 403)

    def test_invalid_ids_windows_limits_relationships_and_offsets(self):
        for params in [dict(context_seconds=3601), dict(context_limit=51), dict(relation='same_session'), dict(relation='same_window'),
                       dict(relation='unknown'), dict(raw_limit=100000), dict(raw_offset=9999999)]:
            response = self.client.get('/api/v1/anomalies/LS-1042/evidence', query_string=params)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/v1/anomalies/not-a-record/evidence').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/anomalies/LS-9999/evidence').status_code, 404)

    def test_export_is_redacted_json_with_explicit_current_page_scope(self):
        response = self.client.get('/api/v1/anomalies/LS-1042/evidence/export?relation=before&context_limit=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        data = response.json
        self.assertEqual(len(data['related_events']['items']), 1)
        self.assertTrue(data['availability']['related_page_truncated'])
        self.assertIn('current evidence page', data['export_scope']['type'])
        self.assertEqual(data['availability']['original_raw_log'], 'unavailable')

    def test_secret_pattern_policy_including_headers_keys_tokens_and_url_credentials(self):
        samples = ['Authorization: Basic cHJpdmF0ZQ==', 'Cookie: session=private-cookie',
                   'eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiZGVtbyJ9.signature',
                   '-----BEGIN PRIVATE KEY-----\nprivate-key-material\n-----END PRIVATE KEY-----',
                   'https://demo-user:private-password@example.invalid/path']
        for sample in samples:
            value = redact(sample)
            self.assertIn('[REDACTED', value)
            for sensitive in ['cHJpdmF0ZQ==', 'private-cookie', '.signature', 'private-key-material', 'private-password']:
                self.assertNotIn(sensitive, value)
        self.assertEqual(redact({'nested': {'api_key': 'private'}})['nested']['api_key'], '[REDACTED]')


if __name__ == '__main__':
    unittest.main()
