"""Data quality: a server-rendered page and the same report as JSON, for granted datasets only."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.analysis_menu import requested_dataset

quality_pages = Blueprint("quality", __name__)


@quality_pages.get("/analysis/quality")
def page() -> ResponseReturnValue:
    if "sqlalchemy" not in current_app.extensions:
        return render_template("quality.html", datasets=[], dataset=None, report=None, unavailable=True), 503
    from app.extensions import db
    from app.models import Dataset
    from app.security import authorized_datasets
    from app.services.data_quality import quality_report

    try:
        allowed = authorized_datasets()
        datasets = list(
            db.session.scalars(select(Dataset).where(Dataset.id.in_(allowed)).order_by(Dataset.id))
        )
        wanted = requested_dataset()
        dataset = next((item for item in datasets if item.id == wanted), datasets[0] if datasets else None)
        report = quality_report(db.session, dataset.id) if dataset else None
    except SQLAlchemyError:
        db.session.rollback()
        return render_template("quality.html", datasets=[], dataset=None, report=None, unavailable=True), 503
    return render_template(
        "quality.html", datasets=datasets, dataset=dataset, report=report, unavailable=False
    )


@quality_pages.get("/api/v1/quality")
def report() -> ResponseReturnValue:
    if "sqlalchemy" not in current_app.extensions:
        return jsonify(error={"code": "database_unavailable"}), 503
    from app.extensions import db
    from app.security import authorized_datasets
    from app.services.data_quality import quality_report

    dataset_id = request.args.get("dataset_id", "")
    if not (dataset_id.isascii() and dataset_id.isdigit()):
        return jsonify(error={"code": "invalid_query", "message": "dataset_id is required."}), 400
    try:
        if int(dataset_id) not in authorized_datasets():
            return jsonify(error={"code": "forbidden"}), 403
        return jsonify(dataset_id=int(dataset_id), **quality_report(db.session, int(dataset_id)))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error={"code": "database_unavailable"}), 503
