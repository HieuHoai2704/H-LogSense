"""Bounded single-process worker: runs due schedules and queued analysis jobs. Run it outside the Flask
server (the demo command starts one next to the app)."""

import argparse
from functools import partial

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import ProcessingJob
from app.services.window_detection import run_windows
from scripts.run.supervision import configure_logging, log, reclaim_interrupted, serve


def run_once(engine):
    from app.services.bgl_ingestion import import_lease

    with Session(engine) as session:
        candidate = session.scalar(
            select(ProcessingJob.id)
            .where(ProcessingJob.kind == "analysis", ProcessingJob.state == "queued")
            .order_by(ProcessingJob.id)
            .limit(1)
        )
    if candidate is None:
        return False
    try:
        with import_lease(engine, "analysis-job-" + str(candidate)):
            return execute_job(engine, candidate)
    except RuntimeError:
        return False


def execute_job(engine, candidate):
    with Session(engine) as session, session.begin():
        job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.id == candidate, ProcessingJob.state == "queued")
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return False
        job.state = "running"
        job_id = job.id
        dataset_id = job.dataset_id
        config = job.configuration
    try:
        result = run_windows(engine, dataset_id, "job:" + str(job_id), config)
        from app.services.alerts import generate_alerts

        result["alerts"] = generate_alerts(engine, dataset_id, result["run_id"])
        with Session(engine) as session, session.begin():
            job = session.get(ProcessingJob, job_id)
            job.state = "completed"
            job.result = result
    except Exception:
        # Keep the reason for operators; the API still reports only the stable error code.
        log.exception("analysis job %s failed", job_id)
        with Session(engine) as session, session.begin():
            job = session.get(ProcessingJob, job_id)
            job.state = "failed"
            job.error_code = "analysis_failed"
    return True


def tick(engine):
    """One worker pass: queue the schedules that are due, then run the oldest queued analysis job."""
    from app.services.schedules import run_due

    scheduled = run_due(engine)
    return run_once(engine) or scheduled > 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    configure_logging()
    app = create_app()
    with app.app_context():
        if "sqlalchemy" not in app.extensions:
            raise SystemExit("Configure MySQL (DATABASE_URL) before starting the analysis worker.")
        engine = db.engine
        serve(
            partial(tick, engine),
            once=args.once,
            reclaim=partial(reclaim_interrupted, engine, "analysis", "analysis-job-"),
        )


if __name__ == "__main__":
    main()
