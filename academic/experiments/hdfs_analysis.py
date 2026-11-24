"""Run HDFS_v1 block analysis independently of the BGL MySQL schema."""

from collections import Counter
from contextlib import closing
import csv
from hashlib import sha256
from io import TextIOWrapper
import json
from pathlib import Path
import sqlite3
import time
from zipfile import ZipFile

import numpy as np
from sklearn.ensemble import IsolationForest

from app.parsers.hdfs import BLOCK, parse_hdfs, physical_lines, wall_iso
from app.services.detector_calibration import binary_metrics, choose_threshold, reservoir_sample

LOG_MEMBER = "HDFS.log"
LABEL_MEMBER = "preprocessed/anomaly_label.csv"
FEATURES = ("event_count", "warn_error", "packet_responder", "data_xceiver", "name_system", "other")
COMPONENT_INDEX = {
    "dfs.DataNode$PacketResponder": 6,
    "dfs.DataNode$DataXceiver": 7,
    "dfs.FSNamesystem": 8,
}
BATCH = 100_000
VERSION = "hdfs-block-v1"
SEED = 42
FIT_LIMIT = 50_000

SCHEMA = """
CREATE TABLE blocks (
    block_id TEXT PRIMARY KEY, first_wall INTEGER NOT NULL, last_wall INTEGER NOT NULL,
    first_line INTEGER NOT NULL, last_line INTEGER NOT NULL,
    event_count INTEGER NOT NULL, warn_error INTEGER NOT NULL,
    packet_responder INTEGER NOT NULL, data_xceiver INTEGER NOT NULL,
    name_system INTEGER NOT NULL, other INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE labels (block_id TEXT PRIMARY KEY, label INTEGER NOT NULL CHECK (label IN (0, 1))) WITHOUT ROWID;
"""
UPSERT = """
INSERT INTO blocks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(block_id) DO UPDATE SET
  first_wall=min(blocks.first_wall,excluded.first_wall),
  last_wall=max(blocks.last_wall,excluded.last_wall),
  first_line=min(blocks.first_line,excluded.first_line),
  last_line=max(blocks.last_line,excluded.last_line),
  event_count=blocks.event_count+excluded.event_count,
  warn_error=blocks.warn_error+excluded.warn_error,
  packet_responder=blocks.packet_responder+excluded.packet_responder,
  data_xceiver=blocks.data_xceiver+excluded.data_xceiver,
  name_system=blocks.name_system+excluded.name_system,
  other=blocks.other+excluded.other
"""


def member(archive, name, limit):
    matches = [entry for entry in archive.infolist() if entry.filename == name]
    if len(matches) != 1 or matches[0].is_dir() or matches[0].file_size > limit:
        raise ValueError(f"Missing, ambiguous or oversized archive member: {name}")
    return matches[0]


def digest(path):
    sha = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def ingest_blocks(db, stream, progress=print):
    counts = Counter()
    batch = {}

    def flush():
        with db:
            db.executemany(UPSERT, ((key, *batch[key]) for key in sorted(batch)))
        batch.clear()

    for line_number, raw in physical_lines(stream):
        counts["raw_lines"] = line_number
        try:
            if raw is None:
                raise ValueError("Line exceeds the byte limit.")
            record = parse_hdfs(raw.decode("utf-8").rstrip("\r\n"))
        except (ValueError, UnicodeError):
            counts["malformed"] += 1
            continue
        counts["parsed_lines"] += 1
        counts["block_references"] += len(record.block_ids)
        counts["lines_without_block"] += not record.block_ids
        for block in record.block_ids:
            row = batch.get(block)
            if row is None:
                row = [record.wall_seconds, record.wall_seconds, line_number, line_number, 0, 0, 0, 0, 0, 0]
                batch[block] = row
            else:
                row[0] = min(row[0], record.wall_seconds)
                row[1] = max(row[1], record.wall_seconds)
                row[3] = line_number
            row[4] += 1
            row[5] += record.level in {"WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"}
            row[COMPONENT_INDEX.get(record.component, 9)] += 1
        if line_number % BATCH == 0 or len(batch) >= BATCH:
            flush()
        if line_number % 1_000_000 == 0:
            progress(f"HDFS parsed {line_number:,} physical lines")
    flush()
    return {
        key: counts[key]
        for key in ("raw_lines", "parsed_lines", "malformed", "block_references", "lines_without_block")
    }


def label_rows(stream):
    reader = csv.DictReader(stream, strict=True)
    if reader.fieldnames != ["BlockId", "Label"]:
        raise ValueError("Expected the HDFS_v1 BlockId,Label header.")
    for row in reader:
        block, label = row["BlockId"], row["Label"]
        if not block or not BLOCK.fullmatch(block) or label not in ("Normal", "Anomaly") or None in row:
            raise ValueError(f"Invalid HDFS label at physical line {reader.line_num}.")
        yield block, int(label == "Anomaly")


def cohort_ranges(db):
    first, final = db.execute("SELECT MIN(first_wall), MAX(last_wall) FROM blocks").fetchone()
    if first is None:
        raise ValueError("No HDFS blocks were parsed.")
    end = final + 1
    span = end - first
    train_end = first + span * 60 // 100
    validation_end = first + span * 80 // 100
    if not first < train_end < validation_end < end:
        raise ValueError("HDFS clock range is too short for three cohorts.")
    return {
        "train": (first, train_end),
        "validation": (train_end, validation_end),
        "test": (validation_end, end),
    }


def count_cohorts(db, splits):
    result = {}
    for name, (start, end) in splits.items():
        total, labeled, positive = db.execute(
            """SELECT COUNT(*),COUNT(l.label),COALESCE(SUM(l.label),0)
            FROM blocks b LEFT JOIN labels l ON b.block_id=l.block_id
            WHERE b.first_wall>=? AND b.last_wall<?""",
            (start, end),
        ).fetchone()
        result[name] = {
            "start_inclusive_wall_clock": wall_iso(start),
            "end_exclusive_wall_clock": wall_iso(end),
            "blocks": total,
            "labeled": labeled,
            "positive": positive,
        }
    return result


def train_features(db, limits):
    return db.execute(
        f"SELECT {','.join(FEATURES)} FROM blocks WHERE first_wall>=? AND last_wall<? ORDER BY block_id",
        limits,
    )


def labeled_rows(db, limits):
    return db.execute(
        f"""SELECT b.block_id,l.label,b.first_line,b.last_line,{",".join(FEATURES)}
        FROM blocks b JOIN labels l ON b.block_id=l.block_id
        WHERE b.first_wall>=? AND b.last_wall<? ORDER BY b.block_id""",
        limits,
    )


def detect(model, rows):
    x = np.asarray([row[4:] for row in rows], dtype=np.float64)
    if not len(x):
        raise ValueError("The requested cohort has no labeled blocks.")
    return {"count_rule": x[:, 0], "isolation_forest": -model.score_samples(np.log1p(x))}


def predictions(path, rows, scores, threshold):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "unit_id",
                "label",
                "prediction",
                "score",
                "first_source_line",
                "last_source_line",
                "event_count",
            )
        )
        for row, score in zip(rows, scores):
            block, label, first, last, event_count, *_ = row
            writer.writerow(
                (block, label, int(score > threshold), format(score, ".17g"), first, last, event_count)
            )


def analyze(db, output, budget):
    splits = cohort_ranges(db)
    cohorts = count_cohorts(db, splits)
    train = reservoir_sample(train_features(db, splits["train"]), limit=FIT_LIMIT, seed=SEED)
    if len(train) < 2:
        raise ValueError("At least two complete train blocks are required.")
    model = IsolationForest(n_estimators=100, max_samples=min(256, len(train)), random_state=SEED, n_jobs=1)
    model.fit(np.log1p(np.asarray(train, dtype=float)))
    validation = list(labeled_rows(db, splits["validation"]))
    labels = [row[1] for row in validation]
    thresholds = {
        name: choose_threshold(labels, scores, max_fpr=budget, direction="higher")
        for name, scores in detect(model, validation).items()
    }
    del validation, labels
    test = list(labeled_rows(db, splits["test"]))
    labels = [row[1] for row in test]
    methods = {}
    for name, scores in detect(model, test).items():
        decision = thresholds[name]
        prediction_path = output / f"{name}-test.csv"
        predictions(prediction_path, test, scores, decision["threshold"])
        methods[name] = {
            "score_direction": "higher",
            "comparison": ">",
            "threshold": decision["threshold"],
            "validation": decision["metrics"],
            "test": binary_metrics(labels, scores, decision["threshold"], direction="higher"),
            "test_predictions": prediction_path.name,
            "test_predictions_sha256": digest(prediction_path),
        }
    blocks = db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
    labels_total = db.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
    matched = db.execute("SELECT COUNT(*) FROM blocks JOIN labels USING (block_id)").fetchone()[0]
    return {
        "block_count": blocks,
        "label_count": labels_total,
        "matched": matched,
        "unlabeled_blocks": blocks - matched,
        "labels_without_block": labels_total - matched,
        "boundary_purge_blocks": blocks - sum(item["blocks"] for item in cohorts.values()),
        "cohorts": cohorts,
        "train_sample_blocks": len(train),
        "seed": SEED,
        "feature_schema": list(FEATURES),
        "validation_fpr_budget": budget,
        "methods": methods,
    }


def run(archive_path, output, *, budget=0.01, progress=print):
    archive_path = Path(archive_path)
    output = Path(output)
    if not np.isfinite(budget) or not 0 <= budget <= 1:
        raise ValueError("The validation FPR budget must be in [0, 1].")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        archive_sha = digest(archive_path)
        with ZipFile(archive_path) as archive, closing(sqlite3.connect(output / "blocks.sqlite3")) as db:
            log_member = member(archive, LOG_MEMBER, 3 * 1024**3)
            label_member = member(archive, LABEL_MEMBER, 64 * 1024**2)
            db.executescript(SCHEMA)
            with archive.open(log_member) as logs:
                counts = ingest_blocks(db, logs, progress)
            with (
                archive.open(label_member) as raw,
                TextIOWrapper(raw, encoding="utf-8-sig", newline="") as labels,
                db,
            ):
                db.executemany("INSERT INTO labels VALUES (?, ?)", label_rows(labels))
            references = db.execute("SELECT COALESCE(SUM(event_count),0) FROM blocks").fetchone()[0]
            if counts["block_references"] != references:
                raise RuntimeError("Block membership counts do not reconcile.")
            ingest_seconds = time.perf_counter() - started
            report = analyze(db, output, budget)
        report.update(
            version=VERSION,
            dataset="Loghub HDFS_v1",
            unit="hdfs_block",
            clock="Source wall clock, timezone not supplied",
            archive_sha256=archive_sha,
            log_member=LOG_MEMBER,
            label_member=LABEL_MEMBER,
            ingest_seconds=round(ingest_seconds, 3),
            total_seconds=round(time.perf_counter() - started, 3),
            **counts,
        )
        with (output / "report.json").open("x", encoding="utf-8") as file:
            json.dump(report, file, indent=2, allow_nan=False)
        return report
    except Exception as error:
        (output / "failed.txt").write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        raise
