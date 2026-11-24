"""Log Explorer logic without a database: search syntax, pattern templates and error-spike insights."""

import unittest

from sqlalchemy.dialects import mysql

from app.models import LogEvent
from app.services.investigation import QueryError
from app.services.log_patterns import error_spikes, filter_terms, normalize
from app.services.log_queries import field_filter, parse_query


class SearchSyntaxTests(unittest.TestCase):
    def test_fields_exclusions_phrases_and_words(self):
        parsed = parse_query(
            'host:R02-M1* level:error -service:KERNEL "machine check" timeout -retry status:fatal'
        )
        self.assertEqual(parsed["hosts"], ["R02-M1*"])
        self.assertEqual(parsed["severities"], ["ERROR", "FATAL"])
        self.assertEqual(parsed["exclude_services"], ["KERNEL"])
        self.assertEqual(parsed["terms"], ["machine check", "timeout"])
        self.assertEqual(parsed["exclude_terms"], ["retry"])

    def test_aliases_unknown_fields_and_quoting(self):
        parsed = parse_query('component:APP severity:warning http://example.org/x -host:"node 7" "" -')
        self.assertEqual(parsed["services"], ["APP"])
        self.assertEqual(parsed["severities"], ["WARNING"])
        self.assertEqual(parsed["exclude_hosts"], ["node 7"])
        self.assertEqual(parsed["terms"], ["http://example.org/x"])  # an unknown field is plain text
        self.assertEqual(parse_query("   ")["terms"], [])

    def test_length_limit(self):
        with self.assertRaises(QueryError):
            parse_query("x" * 501)

    def test_prefix_values_compile_to_like_with_escaping(self):
        sql = str(
            field_filter(LogEvent.host, ["R02-M1*", "node_%*", "exact"]).compile(
                dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        self.assertIn("IN ('exact')", sql)
        self.assertIn("LIKE concat('R02-M1', '%%')", sql.replace('"', "'").replace("CONCAT", "concat"))
        self.assertIn("node/_/%", sql)  # wildcard characters in a prefix are escaped


class PatternTests(unittest.TestCase):
    def test_numbers_and_hex_become_placeholders(self):
        self.assertEqual(
            normalize("ciod: error loading 0x1f3a on node 128 after 3 tries"),
            "ciod: error loading <*> on node <*> after <*> tries",
        )
        self.assertEqual(normalize("R02-M1 abc123 v2"), "R02-M1 abc123 v2")  # tokens inside words stay

    def test_filter_terms_are_long_literal_parts(self):
        self.assertEqual(
            filter_terms("ciod: error loading <*> on node <*> after <*> tries"),
            ["ciod: error loading", "on node"],
        )
        self.assertEqual(filter_terms("<*> <*>"), [])

    def test_window_detector_template_uses_the_same_policy(self):
        import hashlib

        from app.services.window_detection import template

        message = "machine check 0xdead on 42"
        self.assertEqual(template(message), hashlib.sha256(normalize(message).encode()).hexdigest())


class InsightTests(unittest.TestCase):
    @staticmethod
    def bins(errors):
        return [
            {"start": f"s{i}", "end": f"e{i}", "levels": {"INFO": 100, "ERROR": count}}
            for i, count in enumerate(errors)
        ]

    def test_spike_above_median_and_floor(self):
        spikes = error_spikes(self.bins([2, 3, 2, 1, 2, 80, 3, 2]))
        self.assertEqual(spikes, [{"start": "s5", "end": "e5", "count": 80, "baseline": 2.0}])

    def test_no_spike_in_flat_or_small_data(self):
        self.assertEqual(error_spikes(self.bins([5, 6, 5, 6, 5])), [])
        self.assertEqual(error_spikes(self.bins([0, 0, 0, 9])), [])  # below the minimum of 10
        self.assertEqual(error_spikes([]), [])


if __name__ == "__main__":
    unittest.main()
