"""Recurring jobs. The worker calls ``run_due`` on every pass: a due detector schedule queues an analysis
job (the same worker then runs it), and a due import schedule reads the next lines of the BGL archive.

The archive is operator configuration (``LOGSENSE_BGL_ARCHIVE``, default ``data/raw/BGL.zip``), never a
path typed into a web form.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session

from app.domain import JobSchedule
from app.models import ProcessingJob, SourceArtifact
from app.paths import PACKAGE_ROOT

TASKS = ("rule", "isolation_forest", "import")
INTERVALS = (15, 60, 360, 1440)  # minutes offered by the form
DETECTOR_CONFIG = {"window_seconds": 300, "seed": 42}
BGL_MEMBER = "BGL.log"
DUE_BATCH = 20  # schedules handled per worker pass
OVERDUE = timedelta(minutes=10)  # past this, the overview says the worker seems stopped


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bgl_archive() -> Path:
    configured = os.environ.get("LOGSENSE_BGL_ARCHIVE")
    return Path(configured).expanduser() if configured else PACKAGE_ROOT / "data" / "raw" / "BGL.zip"


def next_after(due: datetime, interval_minutes: int, now: datetime) -> datetime:
    """The first slot after ``now`` on the schedule's grid: a stopped worker does not cause a burst."""
    step = timedelta(minutes=interval_minutes)
    if due > now:
        return due
    missed = (now - due) // step + 1
    return due + missed * step


def import_allowed(session: Session | scoped_session[Any], dataset_id: int) -> bool:
    """Import schedules may only extend a BGL dataset (or start an empty one), never mix sources."""
    keys = set(
        session.scalars(select(SourceArtifact.artifact_key).where(SourceArtifact.dataset_id == dataset_id))
    )
    return keys <= {BGL_MEMBER}


def queue_detector(session: Session, schedule: JobSchedule, now: datetime) -> int:
    job = ProcessingJob(
        dataset_id=schedule.dataset_id,
        kind="analysis",
        state="queued",
        job_key=f"schedule-{schedule.id}-{int(now.timestamp())}",
        configuration={"detector": schedule.task, **DETECTOR_CONFIG},
    )
    session.add(job)
    session.flush()
    return job.id


def import_next(engine: Engine, dataset_id: int, lines: int) -> tuple[int | None, str | None]:
    """Import the next ``lines`` physical lines; returns (ingestion job id, error code)."""
    from app.services.bgl_ingestion import ImportBusyError, ingest_bgl

    archive = bgl_archive()
    if not archive.is_file():
        return None, "archive_missing"
    with Session(engine) as session:
        if not import_allowed(session, dataset_id):
            return None, "not_a_bgl_dataset"
        done = session.scalar(
            select(SourceArtifact.checkpoint_line).where(
                SourceArtifact.dataset_id == dataset_id, SourceArtifact.artifact_key == BGL_MEMBER
            )
        )
    started: list[int] = []
    try:
        ingest_bgl(engine, dataset_id, str(archive), limit=(done or 0) + lines, job_started=started.append)
    except ImportBusyError:
        return None, "import_busy"
    except (OSError, ValueError, KeyError):
        return (started[0] if started else None), "import_failed"
    return (started[0] if started else None), None


def run_due(engine: Engine, now: datetime | None = None) -> int:
    """Handle the schedules that are due; returns how many ran. Rows are claimed with SKIP LOCKED, so
    two workers never run the same schedule twice."""
    now = now or utcnow()
    ran = 0
    with Session(engine) as session:
        due_ids = list(
            session.scalars(
                select(JobSchedule.id)
                .where(JobSchedule.enabled.is_(True), JobSchedule.next_run_at <= now)
                .order_by(JobSchedule.next_run_at, JobSchedule.id)
                .limit(DUE_BATCH)
            )
        )
    for schedule_id in due_ids:
        imports: tuple[int, int] | None = None
        with Session(engine) as session, session.begin():
            schedule = session.scalar(
                select(JobSchedule)
                .where(
                    JobSchedule.id == schedule_id,
                    JobSchedule.enabled.is_(True),
                    JobSchedule.next_run_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            if schedule is None:
                continue
            schedule.last_run_at = now
            schedule.next_run_at = next_after(schedule.next_run_at, schedule.interval_minutes, now)
            if schedule.task == "import":
                imports = (schedule.dataset_id, schedule.import_lines or 10_000)
            else:
                schedule.last_job_id = queue_detector(session, schedule, now)
                schedule.last_error = None
        if imports is not None:
            # The import commits batch by batch, outside the schedule's row lock.
            job_id, error = import_next(engine, *imports)
            with Session(engine) as session, session.begin():
                schedule = session.get(JobSchedule, schedule_id)
                if schedule is not None:
                    schedule.last_job_id = job_id if job_id is not None else schedule.last_job_id
                    schedule.last_error = error
        ran += 1
    return ran


def schedule_view(schedule: JobSchedule, now: datetime, jobs: dict[int, str]) -> dict[str, Any]:
    overdue = schedule.enabled and schedule.next_run_at < now - OVERDUE
    return {
        "id": schedule.id,
        "name": schedule.name,
        "task": schedule.task,
        "interval_minutes": schedule.interval_minutes,
        "import_lines": schedule.import_lines,
        "enabled": schedule.enabled,
        "next_run_at": schedule.next_run_at,
        "last_run_at": schedule.last_run_at,
        "last_job_id": schedule.last_job_id,
        "last_job_state": jobs.get(schedule.last_job_id) if schedule.last_job_id else None,
        "last_error": schedule.last_error,
        "overdue": overdue,
    }


def list_schedules(session: Any, dataset_id: int, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or utcnow()
    schedules = list(
        session.scalars(
            select(JobSchedule).where(JobSchedule.dataset_id == dataset_id).order_by(JobSchedule.name)
        )
    )
    job_ids = [item.last_job_id for item in schedules if item.last_job_id]
    jobs = dict(
        session.execute(select(ProcessingJob.id, ProcessingJob.state).where(ProcessingJob.id.in_(job_ids)))
        .tuples()
        .all()
    )
    return [schedule_view(item, now, jobs) for item in schedules]
