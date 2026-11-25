"""Analysis report pages (overview, data quality, pipeline and jobs) and their JSON reports, for granted
datasets only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flask import Blueprint, current_app, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.analysis_menu import requested_dataset

operations = Blueprint("operations", __name__)


def render_page(
    template: str, build: Callable[[Any, int], dict[str, Any]], **extra: Any
) -> ResponseReturnValue:
    """The dataset picker plus ``build(session, dataset_id)`` for the chosen dataset."""
    empty = {"datasets": [], "dataset": None, "report": None, "unavailable": True, **extra}
    if "sqlalchemy" not in current_app.extensions:
        return render_template(template, **empty), 503
    from app.extensions import db
    from app.models import Dataset
    from app.security import authorized_datasets

    try:
        allowed = authorized_datasets()
        datasets = list(
            db.session.scalars(select(Dataset).where(Dataset.id.in_(allowed)).order_by(Dataset.id))
        )
        wanted = requested_dataset()
        dataset = next((item for item in datasets if item.id == wanted), datasets[0] if datasets else None)
        report = build(db.session, dataset.id) if dataset else None
    except SQLAlchemyError:
        db.session.rollback()
        return render_template(template, **empty), 503
    return render_template(
        template, datasets=datasets, dataset=dataset, report=report, unavailable=False, **extra
    )


def json_report(build: Callable[[Any, int], dict[str, Any]]) -> ResponseReturnValue:
    if "sqlalchemy" not in current_app.extensions:
        return jsonify(error={"code": "database_unavailable"}), 503
    from app.extensions import db
    from app.security import authorized_datasets

    dataset_id = request.args.get("dataset_id", "")
    if not (dataset_id.isascii() and dataset_id.isdigit()):
        return jsonify(error={"code": "invalid_query", "message": "dataset_id is required."}), 400
    try:
        if int(dataset_id) not in authorized_datasets():
            return jsonify(error={"code": "forbidden"}), 403
        return jsonify(dataset_id=int(dataset_id), **build(db.session, int(dataset_id)))
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error={"code": "database_unavailable"}), 503


def overview_report(session: Any, dataset_id: int) -> dict[str, Any]:
    from app.services.overview import overview_report as build

    return build(session, dataset_id)


def quality_report(session: Any, dataset_id: int) -> dict[str, Any]:
    from app.services.data_quality import quality_report as build

    return build(session, dataset_id)


def pipeline_report(session: Any, dataset_id: int) -> dict[str, Any]:
    from app.services.pipeline import pipeline_report as build

    return build(session, dataset_id)


@operations.get("/analysis/overview")
def overview() -> ResponseReturnValue:
    return render_page("overview.html", overview_report)


@operations.get("/api/v1/overview")
def overview_json() -> ResponseReturnValue:
    return json_report(overview_report)


@operations.get("/analysis/quality")
def quality() -> ResponseReturnValue:
    return render_page("quality.html", quality_report)


@operations.get("/api/v1/quality")
def quality_json() -> ResponseReturnValue:
    return json_report(quality_report)


@operations.get("/analysis/pipeline")
def pipeline() -> ResponseReturnValue:
    selected = request.args.get("job", "")
    return render_page(
        "pipeline.html",
        pipeline_report,
        selected=int(selected) if selected.isascii() and selected.isdigit() else None,
    )


@operations.get("/api/v1/pipeline")
def pipeline_json() -> ResponseReturnValue:
    return json_report(pipeline_report)
