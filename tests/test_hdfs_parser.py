"""HDFS parser and workbench preview: block ids, source clock and bounded lines."""

from io import BytesIO
import unittest

from app.parsers.hdfs import MAX_LINE, parse_hdfs, physical_lines
from app.workbench.external import analyze


class HDFSParserTests(unittest.TestCase):
    def test_preview_and_import_agree_on_block_ids_and_source_clock(self):
        source = "081109 203615 148 INFO dfs.DataNode$PacketResponder: blk_-12 blk_23 blk_-12"
        item = parse_hdfs(source)
        self.assertEqual(item.block_ids, ("blk_-12", "blk_23"))
        self.assertEqual(item.timestamp_raw, "081109 203615")
        self.assertEqual(analyze(source, "hdfs")["preview"][0]["units"], ["blk_-12", "blk_23"])
        with self.assertRaises(ValueError):
            parse_hdfs(source.replace("203615", "298005"))

    def test_oversized_row_is_drained_and_next_physical_line_is_preserved(self):
        source = BytesIO(b"x" * (MAX_LINE * 2) + b"\nvalid\n")
        self.assertEqual(list(physical_lines(source)), [(1, None), (2, b"valid\n")])
