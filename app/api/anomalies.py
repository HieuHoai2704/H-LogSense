"""Investigation API (V2 contract) for synthetic fixtures and authorized persisted datasets.

Every route serves both kinds of source through ``app.api.sources``; the response shapes are the same.
"""

import time

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import NotFound

from app.api.sources import source_for
from app.i18n import translate
from app.presentation import payload
from app.services.investigation import QueryError

api = Blueprint("anomalies", __name__, url_prefix="/api/v1")

TIMELINE_KEYS = [
    "state",
    "revision",
    "mode",
    "scope_count",
    "high_critical_count",
    "timeline",
    "coverage",
    "row_count",
    "row_page_count",
]
RESULT_KEYS = ["state", "revision", "mode", "scope_count", "result_count", "events", "page_count"]


@api.errorhandler(QueryError)
def invalid_query(error: QueryError) -> ResponseReturnValue:
    return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400


@api.errorhandler(NotFound)
def missing_evidence(error: NotFound) -> ResponseReturnValue:
    return jsonify(error={"code": "not_found", "message": "Anomaly is unavailable in this source."}), 404


@api.before_request
def validate_scope() -> ResponseReturnValue | None:
    return source_for(request.args).check(request.args)


@api.after_request
def no_cached_scope(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


@api.get("/investigation")
def investigation() -> ResponseReturnValue:
    started = time.perf_counter()
    result = payload(source_for(request.args).view(request.args))
    result["query_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return jsonify(result)


@api.get("/anomalies/timeline")
def timeline() -> ResponseReturnValue:
    view = source_for(request.args).view(request.args)
    return jsonify({key: view[key] for key in TIMELINE_KEYS})


@api.get("/anomalies")
def anomalies() -> ResponseReturnValue:
    view = source_for(request.args).view(request.args)
    return jsonify({key: view[key] for key in RESULT_KEYS})


@api.get("/anomalies/export")
def export() -> ResponseReturnValue:
    return source_for(request.args).export(request.args)


@api.get("/anomalies/<anomaly_id>")
def anomaly_detail(anomaly_id: str) -> ResponseReturnValue:
    return source_for(request.args).anomaly(anomaly_id, request.args)


@api.get("/anomalies/<anomaly_id>/evidence")
def anomaly_evidence(anomaly_id: str) -> ResponseReturnValue:
    return source_for(request.args).evidence(anomaly_id, request.args)


@api.get("/anomalies/<anomaly_id>/evidence/raw")
def raw_evidence(anomaly_id: str) -> ResponseReturnValue:
    return source_for(request.args).raw(anomaly_id, request.args)


@api.get("/anomalies/<anomaly_id>/related")
def related_evidence(anomaly_id: str) -> ResponseReturnValue:
    return source_for(request.args).related(anomaly_id, request.args)


@api.get("/anomalies/<anomaly_id>/evidence/export")
def export_evidence(anomaly_id: str) -> ResponseReturnValue:
    return source_for(request.args).evidence_export(anomaly_id, request.args)
