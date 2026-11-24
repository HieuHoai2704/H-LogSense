"""Real BGL prefix import benchmark; new datasets only, no deletion or reset."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import threading
import time
from uuid import uuid4
from zipfile import ZipFile

import psutil
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import (
    Dataset,
    DataSource,
    GroundTruthLabel,
    LogEvent,
    RawLogRecord,
    SourceArtifact,
)
from app.services.bgl_ingestion import fingerprint, ingest_bgl


def verify_provenance(engine, dataset_id, archive):
    """Compare EVERY imported raw byte string, line number and byte offset."""
    expected_hash, stored_hash = hashlib.sha256(), hashlib.sha256()
    count, offset, after_id = 0, 0, 0
    with ZipFile(archive) as zipped, zipped.open("BGL.log") as stream:
        while True:
            with Session(engine) as session:
                rows = session.execute(
                    select(
                        RawLogRecord.id,
                        RawLogRecord.line_number,
                        RawLogRecord.byte_offset,
                        RawLogRecord.raw_bytes,
                        RawLogRecord.parse_error,
                        LogEvent.id.label("parsed_id"),
                        LogEvent.timestamp,
                        LogEvent.raw_timestamp,
                        LogEvent.host,
                        LogEvent.service,
                        LogEvent.severity,
                        LogEvent.message,
                        LogEvent.attributes,
                        GroundTruthLabel.label,
                    )
                    .outerjoin(
                        LogEvent,
                        (LogEvent.dataset_id == RawLogRecord.dataset_id)
                        & (LogEvent.raw_id == RawLogRecord.id)
                        & (LogEvent.emit_index == 0),
                    )
                    .outerjoin(
                        GroundTruthLabel,
                        (GroundTruthLabel.dataset_id == LogEvent.dataset_id)
                        & (GroundTruthLabel.event_id == LogEvent.id)
                        & (GroundTruthLabel.source == "loghub-bgl")
                        & (GroundTruthLabel.version == "original"),
                    )
                    .where(
                        RawLogRecord.dataset_id == dataset_id,
                        RawLogRecord.id > after_id,
                    )
                    .order_by(RawLogRecord.id)
                    .limit(1000)
                ).all()
            if not rows:
                break
            for row in rows:
                raw = stream.readline(262145)
                if row.line_number != count + 1 or row.byte_offset != offset or row.raw_bytes != raw:
                    raise AssertionError("Raw provenance mismatch")
                if row.parse_error is None:
                    fields = raw.decode("utf-8", errors="strict").rstrip("\r\n").split(maxsplit=9)
                    assert row.parsed_id is not None and row.label == fields[0]
                    assert row.timestamp == datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                        seconds=int(fields[1])
                    )
                    assert row.raw_timestamp == fields[4] and row.host == (
                        None if fields[3] == "-" else fields[3]
                    )
                    assert row.service == fields[7] and row.severity == fields[8] and row.message == fields[9]
                    assert row.attributes["epoch"] == fields[1] and row.attributes["node_repeat"] == fields[5]
                else:
                    assert row.parsed_id is None and row.label is None
                expected_hash.update(raw)
                stored_hash.update(row.raw_bytes)
                count += 1
                offset += len(raw)
            after_id = rows[-1].id
    with Session(engine) as session:
        artifact = session.scalar(select(SourceArtifact).where(SourceArtifact.dataset_id == dataset_id))
        counts = {
            table.__tablename__: session.scalar(
                select(func.count()).select_from(table).where(table.dataset_id == dataset_id)
            )
            for table in (RawLogRecord, LogEvent, GroundTruthLabel)
        }
        distinct = session.scalar(
            select(func.count(func.distinct(RawLogRecord.line_number))).where(
                RawLogRecord.dataset_id == dataset_id
            )
        )
        assert count == counts["raw_log_records"] == artifact.checkpoint_line
        assert count == artifact.parsed_count + artifact.malformed_count
        assert counts["log_events"] == counts["ground_truth_labels"] == artifact.parsed_count
        assert offset == artifact.checkpoint_byte
        assert artifact.sha256 == fingerprint(archive)
        return dict(
            verified_lines=count,
            provenance="PASS",
            labels_exact_match="PASS",
            parsed_fields_exact_match="PASS",
            raw_prefix_sha256=stored_hash.hexdigest(),
            source_prefix_sha256=expected_hash.hexdigest(),
            duplicate_lines=count - distinct,
            checkpoint_byte=offset,
            **counts,
        )


def run_benchmark(archive, lines, *, resume=False):
    app = create_app()
    with app.app_context():
        engine = db.engine
        schema = engine.url.database
        if not schema.startswith("logsense_bench_"):
            raise ValueError("Benchmark requires a NEW logsense_bench_* schema, provisioned separately.")
        with Session(engine) as session, session.begin():
            source = DataSource(source_key=uuid4().hex, name="Real Loghub BGL benchmark")
            session.add(source)
            session.flush()
            dataset = Dataset(
                source_id=source.id,
                dataset_key=uuid4().hex,
                name=f"BGL prefix {lines}",
                data_mode="real",
            )
            session.add(dataset)
            session.flush()
            dataset_id = dataset.id
        process = psutil.Process()
        baseline = process.memory_info().rss
        peak = [baseline]
        stop = threading.Event()

        def sample():
            while not stop.wait(0.01):
                peak[0] = max(peak[0], process.memory_info().rss)

        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started = time.perf_counter()

        def fail(line):
            if resume and line >= 50000:
                raise RuntimeError("Deliberate interruption before batch commit")

        interrupted_checkpoint = None
        try:
            try:
                result = ingest_bgl(
                    engine,
                    dataset_id,
                    archive,
                    limit=lines,
                    before_commit=fail if resume else None,
                )
            except RuntimeError:
                if not resume:
                    raise
                with Session(engine) as session:
                    interrupted_checkpoint = session.scalar(
                        select(SourceArtifact.checkpoint_line).where(SourceArtifact.dataset_id == dataset_id)
                    )
                assert interrupted_checkpoint == 49500
                result = ingest_bgl(engine, dataset_id, archive, limit=lines)
            seconds = time.perf_counter() - started
        finally:
            peak[0] = max(peak[0], process.memory_info().rss)
            stop.set()
            monitor.join()
        # Verification cost is deliberately excluded from ingestion timing.
        proof = verify_provenance(engine, dataset_id, archive)
        retried = ingest_bgl(engine, dataset_id, archive, limit=lines)
        assert retried == result
        proof_after_retry = verify_provenance(engine, dataset_id, archive)
        assert proof_after_retry == proof
        timings = []
        with engine.connect() as connection:
            # Parameterized read path; bound limit and dataset. No raw payload in report.
            query = "SELECT id,timestamp FROM log_events WHERE dataset_id=:dataset ORDER BY timestamp,id LIMIT 100"
            for _ in range(20):
                t = time.perf_counter()
                connection.execute(text(query), {"dataset": dataset_id}).all()
                timings.append((time.perf_counter() - t) * 1000)
            plan = connection.execute(
                text("EXPLAIN FORMAT=JSON " + query), {"dataset": dataset_id}
            ).scalar_one()
            analyzed = connection.execute(
                text("EXPLAIN ANALYZE " + query), {"dataset": dataset_id}
            ).scalar_one()
            server = connection.execute(text("SELECT VERSION()")).scalar_one()
        report = (
            dict(
                data="real Loghub BGL, first physical lines in original archive order",
                platform=platform.platform(),
                python=platform.python_version(),
                mysql=server,
                conditions="Shared local MySQL workstation; other isolated QA schemas/workloads may coexist. Single import run, not a dedicated benchmark host.",
                schema=schema,
                dataset_id=dataset_id,
                requested_lines=lines,
                batch_size=500,
                wall_seconds=seconds,
                lines_per_second=lines / seconds,
                process_rss_baseline_mib=baseline / 1024**2,
                process_peak_rss_mib=peak[0] / 1024**2,
                process_peak_delta_mib=(peak[0] - baseline) / 1024**2,
                rss_sample_interval_ms=10,
                memory_scope="Importer Python process only; excludes mysqld and OS cache",
                query_20_warm_reads_ms={
                    "p50": statistics.median(timings),
                    "p95": sorted(timings)[18],
                },
                interrupted_before_commit=50000 if resume else None,
                committed_checkpoint_after_interruption=interrupted_checkpoint,
                resume="PASS" if resume else "NOT RUN in this workload",
                retry_idempotency="PASS",
                explain_json=json.loads(plan),
                explain_analyze=analyzed,
            )
            | result
            | proof
        )
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--lines", type=int, choices=[1000, 10000, 100000, 1000000], required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_benchmark(args.archive, args.lines, resume=args.resume)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if not k.startswith("explain")}, indent=2))


if __name__ == "__main__":
    main()
