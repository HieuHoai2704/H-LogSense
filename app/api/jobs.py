"""Authenticated job submission. Worker execution never runs in Flask requests."""

from flask import Blueprint, jsonify, request
from sqlalchemy import select, func

from app.extensions import db
from app.models import ProcessingJob, Dataset, LogEvent
from app.security import roles, require_dataset
from app.services.investigation import integer, QueryError
from app.i18n import translate

jobs_api = Blueprint("jobs", __name__)


@jobs_api.post("/api/v1/detection/jobs")
@roles("analyst", "manager", "admin")
def submit():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error={"code": "invalid_query"}), 400
    try:
        dataset_id = integer(data.get("dataset_id"), 1, 2**63 - 1, "Dataset")
        require_dataset(dataset_id)
        key = data.get("idempotency_key")
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise QueryError("A bounded idempotency_key is required.")
        config = data.get("configuration", {})
        if not isinstance(config, dict) or set(config) - {
            "detector",
            "window_seconds",
            "seed",
            "start_time",
            "end_time",
            "study_id",
            "model_id",
        }:
            raise QueryError("Unknown detector configuration.")
        if "model_id" in config:
            from app.services.validated_if import DEFAULT_MODEL_ID, model_card
            from datetime import datetime
            if set(config) != {"detector", "model_id"} or config.get("detector") != "isolation_forest" or config.get("model_id") != DEFAULT_MODEL_ID:
                raise QueryError("Use the registered validated model without parameter overrides.")
            try:
                card = model_card(config["model_id"])
            except (ValueError, OSError):
                return jsonify(error={"code": "model_unavailable", "message": "The trusted validated model is not available."}), 503
            last = db.session.scalar(select(func.max(LogEvent.timestamp)).where(LogEvent.dataset_id == dataset_id))
            if last is None or last < datetime.fromisoformat(card["inference_start_utc"]):
                return jsonify(error={"code": "model_time_incompatible", "message": "This model scores only closed BGL windows after its calibration cutoff: " + card["inference_start_utc"]}), 409
        if "study_id" in config:
            import re

            if (
                set(config) != {"detector", "study_id"}
                or config["detector"] != "isolation_forest"
                or not isinstance(config["study_id"], str)
                or not re.fullmatch(r"[a-f0-9]{32}", config["study_id"])
            ):
                raise QueryError(
                    "A frozen study accepts only isolation_forest and a valid study_id."
                )
        detector, window = config.get("detector", "rule"), config.get("window_seconds", 300)
        # Type checks first: a JSON list or object is unhashable and must be a 400, not a 500.
        if (not isinstance(detector, str) or detector not in {"rule", "isolation_forest"}
                or type(window) is not int or window not in {60, 300, 900, 3600}):
            raise QueryError("Unsupported detector/window.")
        if (
            type(config.get("seed", 42)) is not int
            or not 0 <= config.get("seed", 42) <= 2**31 - 1
        ):
            raise QueryError("Invalid seed.")
        if bool(config.get("start_time")) != bool(config.get("end_time")):
            raise QueryError("Both explicit UTC boundaries are required.")
        if config.get("start_time"):
            from app.services.investigation import instant
            from datetime import timedelta
            from app.services.window_detection import second

            start, end = instant(config["start_time"]), instant(config["end_time"])
            width = config.get("window_seconds", 300)
            if (
                start >= end
                or end - start > timedelta(days=366)
                or start.microsecond
                or end.microsecond
                or second(start) % width
                or second(end) % width
            ):
                raise QueryError(
                    "Choose aligned positive UTC windows, at most 366 days."
                )
    except QueryError as error:
        return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400
    dataset = db.session.scalar(
        select(Dataset).where(Dataset.id == dataset_id).with_for_update()
    )
    if dataset is None:
        return jsonify(error={"code": "not_found"}), 404
    job = db.session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.dataset_id == dataset_id, ProcessingJob.job_key == key
        )
    )
    if job is not None:
        if job.configuration != config:
            return jsonify(error={"code": "idempotency_conflict"}), 409
        db.session.commit()
        return jsonify(job_id=job.id, state=job.state), 200
    job = ProcessingJob(
        dataset_id=dataset_id,
        kind="analysis",
        state="queued",
        job_key=key,
        configuration=config,
    )
    db.session.add(job)
    db.session.commit()
    return jsonify(job_id=job.id, state="queued"), 202


@jobs_api.get("/api/v1/detection/jobs/<int:job_id>")
@roles("viewer", "analyst", "manager", "admin")
def status(job_id):
    job = db.session.get(ProcessingJob, job_id)
    if job is None:
        return jsonify(error={"code": "not_found"}), 404
    require_dataset(job.dataset_id)
    return jsonify(
        job_id=job.id,
        state=job.state,
        processed_count=job.processed_count,
        result=job.result,
        error_code=job.error_code,
    )


@jobs_api.post("/api/v1/detection/jobs/<int:job_id>/retry")
@roles("analyst", "manager", "admin")
def retry(job_id):
    from app.services.bgl_ingestion import import_lease
    from sqlalchemy.orm import Session

    # A worker holds this exact connection-owned lease for its entire job.
    # A process crash releases it; an active worker cannot be requeued.
    try:
        with import_lease(db.engine, "analysis-job-" + str(job_id)):
            with Session(db.engine) as session, session.begin():
                job = session.scalar(
                    select(ProcessingJob)
                    .where(ProcessingJob.id == job_id)
                    .with_for_update()
                )
                if job is None:
                    return jsonify(error={"code": "not_found"}), 404
                require_dataset(job.dataset_id)
                if job.kind != "analysis" or job.state not in {"failed", "running"}:
                    return jsonify(error={"code": "job_not_retryable"}), 409
                job.state = "queued"
                job.error_code = None
        return jsonify(job_id=job_id, state="queued"), 202
    except RuntimeError:
        return jsonify(error={"code": "worker_active"}), 409


@jobs_api.get("/api/v1/detection/models")
@roles("viewer", "analyst", "manager", "admin")
def models():
    from app.services.validated_if import model_card
    try:
        return jsonify(items=[model_card()], availability="ready")
    except (ValueError, OSError):
        return jsonify(items=[], availability="unavailable", message="Install the trusted frozen BGL model artifact before using this profile.")
