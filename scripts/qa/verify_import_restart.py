"""Prove committed checkpoints survive an abruptly exiting owned import worker."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import DataSource, Dataset, SourceArtifact, ProcessingJob
from app.services.bgl_ingestion import ingest_bgl
from scripts.bench.benchmark_bgl import verify_provenance

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--worker", type=int)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        if not db.engine.url.database.startswith("logsense_bench_"):
            raise ValueError("Requires the isolated benchmark schema.")
        if args.worker:

            def exit_uncommitted(line):
                if line >= 50000:
                    os._exit(77)  # Intentional worker process crash, no cleanup handlers.

            ingest_bgl(
                db.engine,
                args.worker,
                args.archive,
                limit=100000,
                before_commit=exit_uncommitted,
            )
            raise AssertionError("Crash hook did not execute")
        with Session(db.engine) as session, session.begin():
            source = DataSource(source_key=uuid4().hex, name="Owned process-crash test, real BGL")
            session.add(source)
            session.flush()
            dataset = Dataset(
                source_id=source.id,
                dataset_key=uuid4().hex,
                name="100K BGL abrupt process exit and resume",
                data_mode="real",
            )
            session.add(dataset)
            session.flush()
            dataset_id = dataset.id
        started = time.perf_counter()
        child = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "scripts.qa.verify_import_restart",
                "--archive",
                args.archive,
                "--worker",
                str(dataset_id),
            ],
            check=False,
        )
        assert child.returncode == 77
        with Session(db.engine) as session:
            checkpoint = session.scalar(
                select(SourceArtifact.checkpoint_line).where(SourceArtifact.dataset_id == dataset_id)
            )
        assert checkpoint == 49500
        result = ingest_bgl(db.engine, dataset_id, args.archive, limit=100000)
        proof = verify_provenance(db.engine, dataset_id, args.archive)
        with Session(db.engine) as session:
            stale = session.scalar(
                select(func.count())
                .select_from(ProcessingJob)
                .where(
                    ProcessingJob.dataset_id == dataset_id,
                    ProcessingJob.error_code == "worker_interrupted",
                )
            )
        assert stale == 1
        assert result["physical_lines"] == 100000 and proof["duplicate_lines"] == 0
        report = (
            dict(
                status="PASS",
                worker_exit_code=child.returncode,
                committed_checkpoint_after_crash=checkpoint,
                stale_job_recovered=stale,
                wall_seconds_with_child_startup_and_verification=time.perf_counter() - started,
            )
            | result
            | proof
        )
        output = REPO_ROOT / "docs/database/measurements/bgl-process-crash.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
