"""Shared loop for the analysis and ingestion workers: logging, database backoff, crash recovery."""

import logging
import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

log = logging.getLogger("h_logsen.worker")
RECLAIM_INTERVAL = 60.0


def configure_logging(level=logging.INFO):
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def reclaim_interrupted(engine, kind, lease_prefix, error_code="worker_interrupted"):
    """Fail jobs left 'running' by a worker that died: a live worker always holds the job's lease.

    The job becomes retryable through its API instead of staying 'running' forever.
    """
    from app.models import ProcessingJob
    from app.services.bgl_ingestion import ImportBusyError, import_lease

    with Session(engine) as session:
        running = session.scalars(
            select(ProcessingJob.id).where(ProcessingJob.kind == kind, ProcessingJob.state == "running")
            .order_by(ProcessingJob.id).limit(100)
        ).all()
    reclaimed = []
    for job_id in running:
        try:
            with import_lease(engine, lease_prefix + str(job_id)):
                with Session(engine) as session, session.begin():
                    job = session.scalar(select(ProcessingJob).where(
                        ProcessingJob.id == job_id, ProcessingJob.state == "running").with_for_update())
                    if job is not None:
                        job.state, job.error_code = "failed", error_code
                        reclaimed.append(job_id)
        except ImportBusyError:
            continue  # a live worker owns it
    for job_id in reclaimed:
        log.warning("job %s was left running by a stopped worker; marked failed (%s), retry is available",
                    job_id, error_code)
    return reclaimed


def serve(step, *, once=False, reclaim=None, idle=1.0, max_backoff=60.0, sleep=time.sleep, clock=time.monotonic):
    """Run ``step()`` until stopped. Database outages back off exponentially instead of killing
    the worker; ``reclaim()`` runs at start and then at most once per RECLAIM_INTERVAL."""
    failures = 0
    next_reclaim = clock()
    while True:
        try:
            if reclaim is not None and clock() >= next_reclaim:
                reclaim()
                next_reclaim = clock() + RECLAIM_INTERVAL
            worked = step()
        except SQLAlchemyError as error:
            if once:
                raise
            failures += 1
            delay = min(max_backoff, idle * 2 ** min(failures, 6))
            # Type only: driver messages can carry connection details.
            log.warning("database unavailable (%s); retrying in %.0f s", type(error).__name__, delay)
            sleep(delay)
            continue
        if failures:
            log.info("database connection restored")
            failures = 0
        if once:
            return worked
        if not worked:
            sleep(idle)
