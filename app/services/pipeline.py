"""Pipeline status for one dataset: a job grid (rows are job types, columns are runs) and the data flow
raw logs -> import -> quality checks -> ML detectors -> alerts, each stage coloured by its state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, scoped_session

from app.domain import Alert
from app.models import AnomalyOutput, LogEvent, ProcessingJob, SourceArtifact

GRID_RUNS = 20  # the grid shows the last 20 runs of each job type
RECENT_JOBS = 500  # jobs read per page view
ANALYSIS_TYPES = ("rule", "isolation_forest", "validated", "study")
ROW_ORDER = ("ingestion", "parsing", *ANALYSIS_TYPES)
ALWAYS_SHOWN = ("ingestion", "rule", "isolation_forest")
ACTIVE = {"queued", "running"}


@dataclass(frozen=True)
class JobRecord:
    id: int
    kind: str
    state: str
    processed_count: int
    error_code: str | None
    configuration: Mapping[str, Any] | None
    result: Mapping[str, Any] | None
    upload_id: str | None


def job_type(kind: str, configuration: Mapping[str, Any] | None) -> str:
    """ingestion, parsing, or for analysis the detector profile the job runs."""
    if kind != "analysis":
        return kind
    config = configuration or {}
    if "model_id" in config:
        return "validated"
    if "study_id" in config:
        return "study"
    return "isolation_forest" if config.get("detector") == "isolation_forest" else "rule"


def actions(job: JobRecord) -> list[str]:
    """What an operator may do with this job through the existing APIs."""
    if job.kind == "analysis":
        if job.state in {"failed", "running"}:
            return ["retry"]  # requeue the same job; refused while a worker holds it
        if job.state == "completed":
            return ["rerun"]  # queue a new job with the same configuration
    if job.kind == "ingestion" and job.upload_id and job.state in {"failed", "running"}:
        return ["retry_upload"]
    return []


def job_view(job: JobRecord) -> dict[str, Any]:
    result = job.result or {}
    summary = result.get("alerts")
    alerts: Mapping[str, Any] = summary if isinstance(summary, dict) else {}
    return {
        "id": job.id,
        "kind": job.kind,
        "type": job_type(job.kind, job.configuration),
        "state": job.state,
        "processed_count": job.processed_count,
        "error_code": job.error_code,
        "configuration": dict(job.configuration or {}),
        "run_id": result.get("run_id"),
        "alerts_created": alerts.get("created"),
        "upload_id": job.upload_id,
        "actions": actions(job),
    }


def job_grid(jobs: Iterable[JobRecord]) -> list[dict[str, Any]]:
    """One row per job type, oldest to newest run, at most GRID_RUNS each."""
    rows: dict[str, list[dict[str, Any]]] = {key: [] for key in ROW_ORDER}
    for job in sorted(jobs, key=lambda item: item.id):
        rows[job_type(job.kind, job.configuration)].append(job_view(job))
    return [
        {
            "type": key,
            "runs": runs[-GRID_RUNS:],
            "total": len(runs),
            "latest": runs[-1]["state"] if runs else None,
        }
        for key, runs in rows.items()
        if runs or key in ALWAYS_SHOWN
    ]


def state_of(states: Iterable[str | None]) -> str:
    """Stage colour from its latest job states: failed beats running beats ok; nothing ran is idle."""
    known = [state for state in states if state]
    if "failed" in known:
        return "failed"
    if any(state in ACTIVE for state in known):
        return "running"
    return "ok" if known else "idle"


def flow(
    *,
    lines: int,
    events: int,
    score: int | None,
    grid: list[dict[str, Any]],
    anomalies: int,
    alerts: int,
    open_alerts: int,
) -> list[dict[str, Any]]:
    latest = {row["type"]: row["latest"] for row in grid}
    imported = state_of([latest.get("ingestion"), latest.get("parsing")])
    if imported == "idle" and events:
        imported = "ok"  # data loaded by an earlier tool that left no job
    detectors = state_of(latest.get(key) for key in ANALYSIS_TYPES)
    quality = "idle" if score is None else "ok" if score >= 90 else "warn" if score >= 70 else "failed"
    alerting = "idle" if detectors == "idle" else "warn" if open_alerts else "ok"
    return [
        {"key": "raw", "state": "ok" if lines else "idle", "value": lines},
        {"key": "import", "state": imported, "value": events},
        {"key": "quality", "state": quality, "value": score},
        {"key": "ml", "state": detectors, "value": anomalies},
        {"key": "alerts", "state": alerting, "value": open_alerts, "total": alerts},
    ]


def load_jobs(session: Session | scoped_session[Any], dataset_id: int) -> list[JobRecord]:
    rows = session.execute(
        select(
            ProcessingJob.id,
            ProcessingJob.kind,
            ProcessingJob.state,
            ProcessingJob.processed_count,
            ProcessingJob.error_code,
            ProcessingJob.configuration,
            ProcessingJob.result,
            ProcessingJob.upload_id,
        )
        .where(ProcessingJob.dataset_id == dataset_id)
        .order_by(ProcessingJob.id.desc())
        .limit(RECENT_JOBS)
    ).tuples()
    return [JobRecord(*row) for row in rows]


def pipeline_report(
    session: Session | scoped_session[Any], dataset_id: int, quality: dict[str, Any] | None = None
) -> dict[str, Any]:
    from app.services.data_quality import quality_report

    jobs = load_jobs(session, dataset_id)
    grid = job_grid(jobs)
    lines = session.scalar(
        select(func.coalesce(func.sum(SourceArtifact.checkpoint_line), 0)).where(
            SourceArtifact.dataset_id == dataset_id
        )
    )
    events = session.scalar(select(func.count()).where(LogEvent.dataset_id == dataset_id))
    anomalies = session.scalar(select(func.count()).where(AnomalyOutput.dataset_id == dataset_id))
    alerts, open_alerts = session.execute(
        select(func.count(), func.coalesce(func.sum(case((Alert.status == "open", 1), else_=0)), 0)).where(
            Alert.dataset_id == dataset_id
        )
    ).one()
    if quality is None and (events or lines):
        quality = quality_report(session, dataset_id)
    score = quality["score"] if quality and (events or lines) else None
    return {
        "flow": flow(
            lines=int(lines or 0),
            events=int(events or 0),
            score=score,
            grid=grid,
            anomalies=int(anomalies or 0),
            alerts=int(alerts),
            open_alerts=int(open_alerts),
        ),
        "grid": grid,
        "recent": [job_view(job) for job in jobs[:GRID_RUNS]],
        "queued": sum(job.state == "queued" for job in jobs),
    }
