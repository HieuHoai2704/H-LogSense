"""Behavior checks for shared synthetic scope and linked timeline drilldown."""

import unittest
from unittest.mock import patch

from app import create_app
from app.demo import ANOMALIES, build_workspace


def total_cells(view):
    return sum(cell['count'] for lane in view['lanes'] for cell in lane['cells'])


class WorkspaceTests(unittest.TestCase):
    def test_scope_and_cells_describe_same_records(self):
        for filters in [{}, {'host': 'storage-02'}, {'service': 'api'},
                        {'severity': 'High'}, {'range': 'early'}, {'q': 'timeout'}]:
            with self.subTest(filters=filters):
                view = build_workspace(filters)
                self.assertEqual(total_cells(view), view['scope_count'])
                self.assertEqual(view['result_count'], view['scope_count'])

    def test_each_event_belongs_to_one_drilldown(self):
        view = build_workspace({})
        found = []
        for lane in view['lanes']:
            for cell in lane['cells']:
                if cell['count']:
                    selected = build_workspace({'selection': cell['key']})
                    self.assertEqual(selected['result_count'], cell['count'])
                    self.assertEqual(selected['scope_count'], view['scope_count'])
                    found.extend(e['id'] for e in selected['events'])
        self.assertCountEqual(found, [e['id'] for e in ANOMALIES])
        self.assertEqual(len(found), len(set(found)))

    def test_time_boundary_is_half_open(self):
        sample = dict(ANOMALIES[0], time='14:15:00')
        with patch('app.demo.ANOMALIES', [sample]):
            self.assertEqual(build_workspace({'range': 'early'})['result_count'], 0)
            self.assertEqual(build_workspace({'range': 'recent'})['result_count'], 1)

    def test_cell_priority_is_not_largest_raw_score(self):
        samples = [dict(ANOMALIES[0], score=1),
                   dict(ANOMALIES[0], id='other', severity='Low', score=99)]
        with patch('app.demo.ANOMALIES', samples):
            view = build_workspace({})
            cell = next(c for lane in view['lanes'] for c in lane['cells'] if c['count'])
            self.assertEqual((cell['count'], cell['priority']), (2, 4))

    def test_timezone_changes_labels_not_membership(self):
        args = {'host': 'storage-02', 'selection': 'Isolation Forest@865'}
        local = build_workspace(args)
        utc = build_workspace(dict(args, timezone='utc'))
        self.assertEqual([e['id'] for e in local['events']], [e['id'] for e in utc['events']])
        self.assertEqual(utc['events'][0]['display_time'], '07:28:41')
        self.assertEqual(total_cells(local), total_cells(utc))

    def test_empty_source_differs_from_no_matches(self):
        empty = build_workspace({'source': 'empty'})
        filtered = build_workspace({'q': 'not-present'})
        self.assertTrue(empty['source_empty'])
        self.assertFalse(filtered['source_empty'])
        self.assertEqual(total_cells(empty), 0)
        self.assertEqual(total_cells(filtered), 0)

    def test_fragment_and_full_page_share_filter_state(self):
        with create_app().test_client() as client:
            url = '/?host=storage-02&severity=High'
            page = client.get(url)
            fragment = client.get(url, headers={'X-Workspace-Fragment': '1'})
            self.assertEqual(page.status_code, 200)
            self.assertEqual(fragment.status_code, 200)
            self.assertEqual([e['id'] for e in fragment.json['events']], ['LS-1041'])
            self.assertEqual(page.get_data(as_text=True).count('data-row-id='), 1)

    def test_search_is_escaped_and_unknown_selection_is_cleared(self):
        view = build_workspace({'selection': 'invalid@9999'})
        self.assertEqual(view['state']['selection'], '')
        with create_app().test_client() as client:
            page = client.get('/?q=%3Cscript%3Ealert(1)%3C/script%3E')
            self.assertNotIn('<script>alert(1)</script>', page.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
