"""External sort, label separation and phase gates for a later BGL holdout."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import scripts.audit_if_holdout as study
from app.services.window_detection import aggregate_windows


class LaterBGLHoldoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bounds = {key: study.epoch(value) for key, value in {
            'train_start': '2005-07-01T00:00:00Z',
            'train_end': '2005-07-14T00:00:00Z',
            'validation_end': '2005-07-21T00:00:00Z',
            'test_end': '2005-07-28T00:00:00Z',
        }.items()}

    def line(self, stamp, *, label='-', message='same text', host='host-a'):
        date = datetime.fromtimestamp(stamp, timezone.utc)
        return (f'{label} {stamp} {date:%Y.%m.%d} {host} '
                f'{date:%Y-%m-%d-%H.%M.%S}.000000 {host} RAS KERNEL INFO {message}\n').encode()

    def archive(self, name, lines):
        path = self.root / name
        with ZipFile(path, 'w') as zipped:
            zipped.writestr('BGL.log', b''.join(lines))
        return path

    def test_disjoint_whole_bins_and_fresh_period_required(self):
        study.validate_bounds(self.bounds, 300)
        phases = [study.phase_for(value, self.bounds) for value in (
            self.bounds['train_start'] - 1, self.bounds['train_start'],
            self.bounds['train_end'] - 1, self.bounds['train_end'],
            self.bounds['validation_end'], self.bounds['test_end'])]
        self.assertEqual(phases, [None, 'train', 'train', 'validation', 'test', None])
        with self.assertRaises(ValueError):
            study.validate_bounds(dict(self.bounds, train_start=study.EXPOSED_TEST_END), 300)
        with self.assertRaises(ValueError):
            study.validate_bounds(dict(self.bounds, train_end=self.bounds['train_end'] + 1), 300)
        with self.assertRaises(ValueError):
            study.validate_bounds(self.bounds, 0)

    def test_external_merge_handles_out_of_order_source_exactly_once(self):
        start = self.bounds['train_start']
        archive = self.archive('unordered.zip', [self.line(start + 301), self.line(start + 1),
                                                self.line(start + 2), self.line(start)])
        destination = self.root / 'external'
        destination.mkdir()
        paths, metadata = study.external_chunks(archive, destination,
            {'splits': self.bounds, 'external_sort': {'rows_per_chunk': 2}})
        units = list(aggregate_windows(study.sorted_events(paths), 300, include_templates=True))
        self.assertEqual(metadata['source_time_reversals'], 2)
        self.assertEqual(metadata['external_chunks'], 2)
        self.assertEqual([unit['count'] for unit in units], [3, 1])
        self.assertEqual(units[0]['sample_ids'], [4, 2, 3])
        self.assertEqual(sum(u['count'] for u in units), 4)

    def test_ground_truth_mutation_cannot_change_feature_vectors(self):
        start = self.bounds['train_start']
        features = []
        for index, label in enumerate(('-', 'SYNTHETIC_ALERT')):
            archive = self.archive(f'labels-{index}.zip', [
                self.line(start, label=label), self.line(start + 1, label=label)])
            destination = self.root / str(index)
            destination.mkdir()
            paths, _ = study.external_chunks(archive, destination,
                {'splits': self.bounds, 'external_sort': {'rows_per_chunk': 2}})
            features.append(list(aggregate_windows(study.sorted_events(paths), 300, include_templates=True)))
        self.assertEqual(features[0], features[1])
        self.assertNotIn('label', features[0][0])

    def test_duplicate_physical_reference_fails_before_double_count(self):
        path = self.root / 'duplicate.jsonl'
        row = [self.bounds['train_start'], 1, 'host-a', 'INFO', 'same text', 0]
        path.write_text(json.dumps(row) + '\n' + json.dumps(row) + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            list(study.sorted_events([path]))

    def test_test_labels_require_frozen_access_and_train_labels_are_forbidden(self):
        path = self.root / 'test.jsonl'
        for phase in ('train', 'test'):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                study.labels_for(self.root / 'not-opened.zip', {}, phase, path)

    def test_repeat_test_and_reselection_are_rejected_before_model_loading(self):
        study_id = 'a' * 32
        directory = self.root / study_id
        directory.mkdir()
        (directory / 'test-access.json').write_text('{}', encoding='utf-8')
        with patch.object(study, 'ROOT', self.root), patch.object(study.joblib, 'load') as load:
            with self.assertRaisesRegex(ValueError, 'opened'):
                study.test(study_id, self.root / 'not-opened.zip')
            with self.assertRaisesRegex(ValueError, 'frozen'):
                study.validate(study_id, self.root / 'not-opened.zip')
            load.assert_not_called()

    def test_matrix_enforces_frozen_count_and_finite_features(self):
        unit = {'features': [0.0] * 5}
        self.assertEqual(study.matrix([unit], 1).shape, (1, 5))
        with self.assertRaises(ValueError):
            study.matrix([unit], 2)
        with self.assertRaises(ValueError):
            study.matrix([{'features': [float('nan')] * 5}], 1)


if __name__ == '__main__':
    unittest.main()
