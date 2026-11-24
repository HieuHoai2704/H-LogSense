"""Public synthetic parser examples; no research payload is committed."""

from datetime import datetime, timezone
from io import BytesIO
import unittest

from app.parsers.bgl import parse_line, iter_records, LEGACY_VERSION, MAX_LINE_BYTES, VERSION
from app.services.detection import features

LINE = b"- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.363779 R02-M1-N0-C:J12-U11 RAS KERNEL INFO test message\n"


class BGLParserTests(unittest.TestCase):
    def test_preserves_raw_and_fields(self):
        r = parse_line(LINE, 1, 0)
        self.assertEqual(r.raw, LINE)
        self.assertEqual(r.label, "-")
        self.assertEqual(r.message, "test message")
        self.assertEqual(r.host, "R02-M1-N0-C:J12-U11")
        self.assertEqual(r.attributes["component"], "KERNEL")

    def test_epoch_authoritative_not_printed_timezone(self):
        r = parse_line(LINE, 1, 0)
        self.assertEqual(r.timestamp, datetime.fromtimestamp(1117838570, timezone.utc))
        self.assertEqual(r.timestamp.microsecond, 0)

    def test_alert_label_preserved_without_feature_leakage(self):
        normal = parse_line(LINE, 1, 0)
        alert = parse_line(LINE.replace(b"- ", b"KERNALERT ", 1), 1, 0)
        self.assertEqual(alert.label, "KERNALERT")
        self.assertEqual(
            features(normal.message, normal.attributes["level"]),
            features(alert.message, alert.attributes["level"]),
        )

    def test_offsets_crlf_final_line(self):
        a = LINE.rstrip(b"\n") + b"\r\n"
        b = LINE.rstrip(b"\n")
        records = list(iter_records(BytesIO(a + b), first_line=3, byte_offset=99))
        self.assertEqual([r.line_number for r in records], [3, 4])
        self.assertEqual(records[1].byte_offset, 99 + len(a))
        self.assertEqual(records[1].raw, b)

    def test_invalid_utf8(self):
        self.assertEqual(parse_line(LINE + b"\xff", 1, 0).error, "invalid_utf8")

    def test_blank_and_truncated(self):
        for raw in (b"\n", b"", b"- 123 2005.06.03\n"):
            self.assertEqual(parse_line(raw, 1, 0).error, "invalid_field_count")

    def test_invalid_timestamps(self):
        for raw in (
            LINE.replace(b"1117838570", b"NaN"),
            LINE.replace(b"2005.06.03", b"2005.99.03"),
            LINE.replace(b"1117838570", b"99999999999999999999999999999"),
        ):
            self.assertEqual(parse_line(raw, 1, 0).error, "invalid_timestamp")

    def test_oversized_line_aborts(self):
        with self.assertRaises(ValueError):
            list(iter_records(BytesIO(b"x" * (MAX_LINE_BYTES + 1))))

    def test_missing_host_not_invented(self):
        raw = LINE.replace(b" R02-M1-N0-C:J12-U11 ", b" - ", 1)
        self.assertIsNone(parse_line(raw, 1, 0).host)

    def test_node_repeat_does_not_override_node(self):
        raw = LINE.replace(b" R02-M1-N0-C:J12-U11 RAS ", b" other-node RAS ")
        record = parse_line(raw, 1, 0)
        self.assertEqual(record.host, "R02-M1-N0-C:J12-U11")
        self.assertEqual(record.attributes["node_repeat"], "other-node")

    def test_safe_html_is_text(self):
        raw = LINE.replace(b"test message", b"<script>alert(1)</script>")
        self.assertEqual(parse_line(raw, 1, 0).message, "<script>alert(1)</script>")

    def test_iterator_is_lazy(self):
        stream = BytesIO(LINE * 100)
        iterator = iter_records(stream)
        next(iterator)
        self.assertEqual(stream.tell(), len(LINE))

    def test_invalid_provenance(self):
        with self.assertRaises(ValueError):
            parse_line(LINE, 0, 0)


EMPTY_CONTENT = b"- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL FATAL\n"


class ParserVersionTests(unittest.TestCase):
    def test_empty_content_row_is_valid_since_1_1(self):
        record = parse_line(EMPTY_CONTENT, 1, 0)
        self.assertIsNone(record.error)
        self.assertEqual(record.message, "")
        self.assertEqual(record.attributes["level"], "FATAL")
        self.assertEqual(VERSION, "bgl-1.1.0")

    def test_legacy_version_keeps_the_frozen_behaviour(self):
        self.assertEqual(parse_line(EMPTY_CONTENT, 1, 0, LEGACY_VERSION).error, "invalid_field_count")
        self.assertIsNone(parse_line(LINE.replace(b"\n", b"\rx\n"), 1, 0, LEGACY_VERSION).error)

    def test_carriage_return_inside_a_line_is_rejected(self):
        self.assertEqual(parse_line(LINE.replace(b" test", b"\r test"), 1, 0).error, "invalid_line_break")
        self.assertIsNone(parse_line(LINE.replace(b"\n", b"\r\n"), 1, 0).error)

    def test_iterator_and_unknown_version(self):
        records = list(iter_records(BytesIO(EMPTY_CONTENT), version=LEGACY_VERSION))
        self.assertEqual(records[0].error, "invalid_field_count")
        with self.assertRaises(ValueError):
            parse_line(LINE, 1, 0, "bgl-9")
