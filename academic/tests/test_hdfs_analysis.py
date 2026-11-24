"""HDFS block-session experiment: aggregation, label validation and time-isolated evaluation."""

import csv
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from academic.experiments.hdfs_analysis import (
    LABEL_MEMBER,
    LOG_MEMBER,
    SCHEMA,
    ingest_blocks,
    label_rows,
    run,
)


class HDFSAnalysisTests(unittest.TestCase):
    def test_aggregation_deduplicates_a_line_but_assigns_multiple_blocks(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(SCHEMA)
        source = BytesIO(
            b"081109 203615 148 WARN dfs.DataNode$PacketResponder: blk_1 blk_1 blk_-2\n"
            b"081109 203614 222 INFO dfs.FSNamesystem: blk_1\n"
            b"081109 203617 222 INFO dfs.FSNamesystem: no block mentioned\n"
            b"bad row\n"
        )
        count = ingest_blocks(db, source)
        self.assertEqual(
            count, dict(raw_lines=4, parsed_lines=3, malformed=1, block_references=3, lines_without_block=1)
        )
        self.assertEqual(
            db.execute(
                "SELECT event_count,warn_error,packet_responder,name_system,first_line,last_line FROM blocks WHERE block_id='blk_1'"
            ).fetchone(),
            (2, 1, 1, 1, 1, 2),
        )
        self.assertEqual(
            db.execute("SELECT first_wall < last_wall FROM blocks WHERE block_id='blk_1'").fetchone(), (1,)
        )

    def test_invalid_labels_are_rejected(self):
        from io import StringIO

        with self.assertRaises(ValueError):
            list(label_rows(StringIO("BlockId,Label\nblk_1,maybe\n")))

    def test_zip_run_purges_cross_boundary_blocks_and_uses_fixed_test_labels(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            archive_path = folder / "test.zip"
            base = datetime(2008, 11, 9, 20, 0)
            offsets = [0, 9, 17, 20, 22, 25, 28, 30, 36, 39, 45, 47, 50, 55, 58]
            records = []
            labels = ["BlockId,Label"]
            for idx, seconds in enumerate(offsets):
                stamp = base + timedelta(seconds=seconds)
                records.append(f"{stamp:%y%m%d %H%M%S} 1 INFO dfs.FSNamesystem: blk_{idx}")
                labels.append(f"blk_{idx}," + ("Anomaly" if idx % 2 else "Normal"))
            records.extend(
                [
                    "081109 200000 1 INFO dfs.FSNamesystem: blk_100",
                    "081109 200050 1 INFO dfs.FSNamesystem: blk_100",
                ]
            )
            labels.append("blk_100,Normal")
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(LOG_MEMBER, "\n".join(records) + "\n")
                archive.writestr(LABEL_MEMBER, "\n".join(labels) + "\n")
            result = run(archive_path, folder / "out")
            self.assertEqual(result["boundary_purge_blocks"], 1)
            self.assertEqual(result["matched"], 16)
            self.assertEqual(result["cohorts"]["test"]["labeled"], 4)
            for method, report in result["methods"].items():
                self.assertLessEqual(report["validation"]["fpr"], 0.01)
                with (folder / "out" / report["test_predictions"]).open(encoding="utf-8") as output:
                    rows = list(csv.DictReader(output))
                self.assertNotIn("blk_100", {row["unit_id"] for row in rows}, method)
                self.assertEqual(len(rows), result["cohorts"]["test"]["labeled"])
                self.assertTrue(
                    all(
                        int(row["prediction"]) == int(float(row["score"]) > report["threshold"])
                        for row in rows
                    )
                )
            with self.assertRaises(FileExistsError):
                run(archive_path, folder / "out")
