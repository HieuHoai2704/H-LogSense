"""Training-only window-context invariants; synthetic records, no BGL payload."""

import json
import math
import pickle
import unittest

from app.services.window_features import (
    BASE_FEATURE_NAMES, CONTEXT_FEATURE_NAMES, FEATURE_NAMES, TrainReference,
)


def record(count=1, host="host-a", templates=None, **extra):
    return {
        "count": count,
        "host": host,
        "templates": templates if templates is not None else {"known-template": count},
        "features": [math.log1p(count), 0.0, 1.0 / max(count, 1), 1.0, math.log1p(20)],
        **extra,
    }


class WindowContextFeaturesTests(unittest.TestCase):
    def test_singletons_are_distinguished_by_frozen_template_frequency(self):
        ref = TrainReference.fit([record(4), record(2)])
        known = record()
        novel = record(templates={"future-template": 1})
        self.assertEqual(known["features"], novel["features"])
        self.assertGreater(ref.transform(novel)[5], ref.transform(known)[5])
        self.assertEqual(ref.transform(known)[6], 0.0)
        self.assertEqual(ref.transform(novel)[6], 1.0)

    def test_laplace_probability_and_event_weighted_mean(self):
        ref = TrainReference.fit([record(4, templates={"a": 3, "b": 1})])
        values = ref.transform(record(4, templates={"a": 1, "never-seen": 3}))
        self.assertAlmostEqual(values[5], (-math.log(4 / 7) - 3 * math.log(1 / 7)) / 4)
        self.assertEqual(values[6], 0.75)

    def test_host_moments_population_std_and_unseen_host_fallback(self):
        ref = TrainReference.fit([record(1), record(3)])
        transformed = ref.transform(record(3))
        self.assertAlmostEqual(transformed[7], 1.0)
        self.assertEqual(transformed[8], 0.0)
        unknown = ref.transform(record(3, host="future-host"))
        self.assertAlmostEqual(unknown[7], 1.0)
        self.assertEqual(unknown[8], 1.0)

    def test_host_scale_has_floor_for_constant_training_counts(self):
        ref = TrainReference.fit([record(), record()])
        self.assertAlmostEqual(ref.transform(record(3))[7], (math.log(4) - math.log(2)) / 0.1)

    def test_future_perturbation_never_updates_frozen_reference(self):
        ref = TrainReference.fit(iter([record(), record(2)]))
        before = pickle.dumps(ref)
        original = ref.transform(record())
        for i in range(10):
            ref.transform(record(100, host=f"future-{i}", templates={f"new-{i}": 100}))
        self.assertEqual(pickle.dumps(ref), before)
        self.assertEqual(ref.transform(record()), original)

    def test_label_changes_do_not_affect_training_or_transformation(self):
        class NoLabelReads(dict):
            def __getitem__(self, key):
                if key in ("label", "ground_truth", "is_anomaly"):
                    raise AssertionError("Ground truth was read")
                return super().__getitem__(key)
        train = NoLabelReads(record(label="ALERT", ground_truth=True))
        ref = TrainReference.fit([train])
        clean = TrainReference.fit([record(label="-")])
        self.assertEqual(ref.summary(), clean.summary())
        self.assertEqual(ref.transform(train), clean.transform(record(label="changed")))

    def test_caps_fail_closed_and_cannot_be_raised(self):
        with self.assertRaisesRegex(ValueError, "host reference"):
            TrainReference.fit([record(host="a"), record(host="b")], max_hosts=1)
        with self.assertRaisesRegex(ValueError, "template reference"):
            TrainReference.fit([record(), record(templates={"new": 1})], max_templates=1)
        for kwargs in ({"max_hosts": 50_001}, {"max_templates": 100_001}, {"max_hosts": 0}):
            with self.assertRaises(ValueError):
                TrainReference.fit([record()], **kwargs)

    def test_histogram_mismatch_and_invalid_vectors_rejected(self):
        ref = TrainReference.fit([record()])
        invalid = [
            record(2, templates={"a": 1}), record(templates={"a": 0}),
            record(templates={"a": True}), record(count=0), record(host=""),
            record(features=[0.0] * 4), record(features=[math.nan] * 5),
            record(features=[math.inf] * 5), record(features=[True] * 5),
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    TrainReference.fit([value])
                with self.assertRaises(ValueError):
                    ref.transform(value)
        with self.assertRaises(ValueError):
            TrainReference.fit([])

    def test_deterministic_names_summary_and_serialization(self):
        records = [record(), record(3, host="host-b", templates={"template-b": 3})]
        first = TrainReference.fit(iter(records))
        second = TrainReference.fit(iter(records))
        self.assertEqual(first.names, BASE_FEATURE_NAMES + CONTEXT_FEATURE_NAMES)
        self.assertEqual(first.names, FEATURE_NAMES)
        self.assertEqual(first.summary(), second.summary())
        self.assertEqual(first.transform(record()), second.transform(record()))
        self.assertEqual(pickle.loads(pickle.dumps(first)).transform(record()), first.transform(record()))
        summary = json.dumps(first.summary())
        self.assertNotIn("host-a", summary)
        self.assertNotIn("known-template", summary)
        names = first.names
        names.append("mutation")
        self.assertEqual(len(first.names), 9)


if __name__ == "__main__":
    unittest.main()
