"""Opt-in private result API; not connected to the public demo workspace."""

import os
import secrets

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from app.extensions import db
from app.models import DetectorRun, DetectorVersion
from app.repositories import page_anomalies

database_api = Blueprint("database_api", __name__)


@database_api.after_request
def private_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def access_dataset():
    from app.security import authorized_datasets

    allowed = authorized_datasets()
    if not allowed:
        return None, (jsonify(error={"code": "forbidden"}), 403)
    try:
        dataset_id = int(request.args["dataset_id"])
    except (ValueError, KeyError):
        return None, (jsonify(error={"code": "invalid_query"}), 400)
    if not 1 <= dataset_id <= 2**63 - 1:
        return None, (jsonify(error={"code": "invalid_query"}), 400)
    if dataset_id not in allowed:
        return None, (jsonify(error={"code": "forbidden"}), 403)
    if "sqlalchemy" not in current_app.extensions:
        return None, (jsonify(error={"code": "database_unavailable"}), 503)
    return dataset_id, None


@database_api.get("/api/v1/database/anomalies/<int:anomaly_id>/evidence")
def evidence(anomaly_id):
    dataset_id, denied = access_dataset()
    if denied:
        return denied
    if not 1 <= anomaly_id <= 2**63 - 1:
        return jsonify(error={"code": "invalid_query"}), 400
    from app.services.database_evidence import load_evidence

    try:
        payload = load_evidence(
            db.session,
            dataset_id,
            anomaly_id,
            raw_offset=int(request.args.get("raw_offset", "0")),
            raw_limit=int(request.args.get("raw_limit", "2048")),
        )
    except ValueError:
        return jsonify(error={"code": "invalid_query"}), 400
    if payload is None:
        return jsonify(error={"code": "not_found"}), 404
    return jsonify(payload)


@database_api.get("/api/v1/database/anomalies")
def anomalies():
    dataset_id, denied = access_dataset()
    if denied:
        return denied
    try:
        run_id = int(request.args["run_id"])
        after = int(request.args.get("after_id", "0"))
        limit = int(request.args.get("limit", "50"))
        if (
            not 1 <= run_id <= 2**63 - 1
            or not 0 <= after <= 2**63 - 1
            or not 1 <= limit <= 100
        ):
            raise ValueError()
    except (ValueError, KeyError):
        return jsonify(error={"code": "invalid_query"}), 400
    # Only completed runs are visible; unfinished batches are not published results.
    run = db.session.scalar(
        select(DetectorRun).where(
            DetectorRun.dataset_id == dataset_id,
            DetectorRun.id == run_id,
            DetectorRun.state == "completed",
        )
    )
    if run is None:
        return jsonify(error={"code": "not_found"}), 404
    version = db.session.get(DetectorVersion, run.version_id)
    rows = page_anomalies(db.session, dataset_id, run_id, after_id=after, limit=limit)
    response = jsonify(
        dataset_id=dataset_id,
        run_id=run_id,
        input_revision=run.input_revision,
        detector_id=run.detector_id,
        detector_version=version.version,
        score_direction=version.score_direction,
        score_is_probability=False,
        evaluated_units=run.evaluated_units,
        anomalies=[
            dict(
                id=r.id,
                unit_id=r.unit_id,
                timestamp=r.anchor_time.isoformat(),
                priority=r.priority,
                native_score=r.score,
            )
            for r in rows
        ],
        next_after_id=rows[-1].id if len(rows) == limit else None,
    )
    response.headers["Cache-Control"] = "no-store"
    return response
