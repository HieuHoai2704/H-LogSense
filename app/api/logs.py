"""Authorized, bounded parsed-log API. Raw log levels are not anomaly priorities."""

import csv
from datetime import timedelta
import io

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    request,
    stream_with_context,
)
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import NotFound

from app.extensions import db
from app.i18n import translate
from app.models import AnomalyOutput, Dataset, GroundTruthLabel, LogEvent, RawLogRecord, SourceArtifact
from app.security import Forbidden, authorized_datasets, identity, roles
from app.services import log_patterns
from app.services.csv_safety import safe_cell
from app.services.investigation import QueryError, integer, iso
from app.services.log_queries import facets, page, parse_scope, predicates, scope_key, timeline
from app.services.redaction import redact
from app.services.report_cache import cached

logs_api = Blueprint("logs", __name__)


@logs_api.errorhandler(QueryError)
def invalid(error):
    return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400


@logs_api.errorhandler(NotFound)
def missing(error):
    return jsonify(error={"code": "not_found"}), 404


@logs_api.errorhandler(SQLAlchemyError)
def unavailable(error):
    db.session.rollback()
    return jsonify(
        error={
            "code": "database_unavailable",
            "message": "The database query could not complete.",
        }
    ), 503


@logs_api.before_request
def require_access():
    if request.endpoint == "logs.datasets" and identity() is not None:
        return
    if not authorized_datasets():
        raise Forbidden()
    if "sqlalchemy" not in current_app.extensions:
        return jsonify(error={"code": "database_unavailable"}), 503


@logs_api.get("/api/v1/logs/datasets")
def datasets():
    allowed = authorized_datasets()
    result = []
    for dataset in db.session.scalars(
        select(Dataset).where(Dataset.id.in_(allowed)).order_by(Dataset.id).limit(100)
    ):
        first, last = db.session.execute(
            select(func.min(LogEvent.timestamp), func.max(LogEvent.timestamp)).where(
                LogEvent.dataset_id == dataset.id
            )
        ).one()
        result.append(
            dict(
                id=dataset.id,
                name=dataset.name,
                data_mode=dataset.data_mode,
                input_revision=dataset.input_revision,
                start_time=iso(first) if first else None,
                end_time=iso(last + timedelta(seconds=1)) if last else None,
            )
        )
    return jsonify(datasets=result)


def serialize(row):
    return {
        "id": row.id,
        "timestamp": iso(row.timestamp),
        "raw_timestamp": row.raw_timestamp,
        "host": redact(row.host),
        "service": redact(row.service),
        "severity": row.severity,
        "message": redact(row.message[:8192]),
        "message_truncated": len(row.message) > 8192,
    }


@logs_api.get("/api/v1/logs")
def logs():
    scope = parse_scope(db.session, request.args)
    rows, cursor, count = page(db.session, scope)
    return jsonify(
        mode="database",
        dataset_id=scope.dataset_id,
        scope_token=scope.token,
        input_revision=scope.revision,
        count=count,
        items=[serialize(r) for r in rows],
        next_cursor=cursor,
        range={
            "start": iso(scope.start),
            "end": iso(scope.end),
            "semantics": "[start,end)",
        },
    )


@logs_api.get("/api/v1/logs/timeline")
def volume():
    scope = parse_scope(db.session, request.args)
    cells = timeline(
        db.session,
        scope,
        bins=integer(request.args.get("bins", 60), 20, 120, "Timeline bins"),
    )
    return jsonify(
        scope_token=scope.token,
        input_revision=scope.revision,
        metric="parsed_event_count",
        bins=cells,
        count=sum(c["event_count"] for c in cells),
        coverage="unknown; count refers to observed imported events",
    )


@logs_api.get("/api/v1/logs/<int:event_id>")
def details(event_id):
    scope = parse_scope(db.session, request.args)
    event = db.session.scalar(select(LogEvent).where(*predicates(scope), LogEvent.id == event_id))
    if event is None:
        raise NotFound()
    raw = db.session.get(RawLogRecord, event.raw_id)
    artifact = db.session.get(SourceArtifact, raw.artifact_id)
    text = redact(raw.raw_bytes[:262144].decode("utf-8", errors="replace"))
    offset = integer(request.args.get("raw_offset", "0"), 0, len(text), "Raw offset")
    annotation = db.session.execute(
        select(GroundTruthLabel.label, GroundTruthLabel.source, GroundTruthLabel.version)
        .where(
            GroundTruthLabel.dataset_id == scope.dataset_id,
            GroundTruthLabel.event_id == event.id,
            GroundTruthLabel.source.in_(["loghub-bgl", "uploaded-bgl"]),
        )
        .order_by(GroundTruthLabel.id)
        .limit(1)
    ).first()
    return jsonify(
        event=serialize(event),
        ground_truth_label=redact(annotation.label) if annotation else None,
        ground_truth_label_provenance={
            "source": annotation.source,
            "version": annotation.version,
            "note": "Imported annotation; not an unsupervised model feature.",
        }
        if annotation
        else None,
        raw={
            "text": text[offset : offset + 8192],
            "next_offset": offset + 8192 if offset + 8192 < len(text) else None,
            "redacted": True,
        },
        provenance={
            "source_artifact": artifact.artifact_key,
            "archive_sha256": artifact.sha256,
            "physical_line": raw.line_number,
            "byte_offset": raw.byte_offset,
            "parser_version": event.parser_version,
            "upload": redact((event.attributes or {}).get("upload")),
            "source_kind": "normalized-upload"
            if (event.attributes or {}).get("upload")
            else "operator-source",
        },
    )


@logs_api.get("/api/v1/logs/export")
def export():
    scope = parse_scope(db.session, request.args)
    count = db.session.scalar(select(func.count()).select_from(LogEvent).where(*predicates(scope)))
    if count > 100000:
        return jsonify(
            error={
                "code": "export_limit",
                "message": "Narrow the scope to 100,000 parsed events.",
            }
        ), 422

    def safe(value):
        return safe_cell(value)

    def generate():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        fields = ["id", "timestamp", "host", "service", "severity", "message"]
        writer.writerow(fields)
        yield output.getvalue()
        # Server-side cursor streams rows; no complete result list is materialized.
        order = (
            (LogEvent.timestamp.asc(), LogEvent.id.asc())
            if scope.direction == "asc"
            else (LogEvent.timestamp.desc(), LogEvent.id.desc())
        )
        rows = db.session.scalars(
            select(LogEvent).where(*predicates(scope)).order_by(*order).execution_options(yield_per=50)
        )
        for row in rows:
            output.seek(0)
            output.truncate(0)
            values = serialize(row)
            values["message"] = redact(row.message)
            writer.writerow([safe(values[k]) for k in fields])
            yield output.getvalue()

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="bgl-logs.csv"',
            "X-Result-Count": str(count),
        },
    )


@logs_api.get("/api/v1/logs/facets")
def facet_counts():
    scope = parse_scope(db.session, request.args)
    size = integer(request.args.get("size", "10"), 1, 50, "Facet size")
    counted = cached(("facets", size, scope_key(scope)), lambda: facets(db.session, scope, size))
    return jsonify(scope_token=scope.token, facets=counted)


@logs_api.get("/api/v1/logs/patterns")
def patterns():
    scope = parse_scope(db.session, request.args)
    found = cached(("patterns", scope_key(scope)), lambda: log_patterns.top_patterns(db.session, scope))
    return jsonify(scope_token=scope.token, **found)


@logs_api.get("/api/v1/logs/insights")
def insights():
    scope = parse_scope(db.session, request.args)
    # Detector anomalies are part of the insights: a new run changes the key.
    newest = db.session.scalar(
        select(func.max(AnomalyOutput.id)).where(AnomalyOutput.dataset_id == scope.dataset_id)
    )
    found = cached(("insights", newest, scope_key(scope)), lambda: log_patterns.insights(db.session, scope))
    return jsonify(scope_token=scope.token, **found)


@logs_api.get("/api/v1/logs/<int:event_id>/context")
def context(event_id):
    scope = parse_scope(db.session, request.args)
    event = db.session.scalar(
        select(LogEvent).where(
            LogEvent.dataset_id == scope.dataset_id, LogEvent.id <= scope.maximum_id, LogEvent.id == event_id
        )
    )
    if event is None:
        raise NotFound()
    size = integer(request.args.get("size", "10"), 1, 50, "Context size")
    before, after = log_patterns.surrounding(db.session, scope, event, size)
    return jsonify(
        event=serialize(event),
        before=[serialize(row) for row in before],
        after=[serialize(row) for row in after],
        pattern=redact(log_patterns.normalize(event.message[:2000])[:500]),
        pattern_terms=[
            redact(x) for x in log_patterns.filter_terms(log_patterns.normalize(event.message[:2000]))
        ],
    )


# ---- Saved views: named filter sets kept on the account ----

VIEW_KEYS = {"dataset_id", "start_time", "end_time", "host", "severity", "q", "query", "sort", "limit"}
MAX_VIEWS = 20


def clean_view(data):
    if not isinstance(data, dict):
        raise QueryError("JSON object required.")
    name = data.get("name")
    params = data.get("params")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        raise QueryError("A view name of 1 to 60 characters is required.")
    if any(ord(ch) < 32 for ch in name):
        raise QueryError("A view name of 1 to 60 characters is required.")
    if not isinstance(params, dict) or not params or set(params) - VIEW_KEYS:
        raise QueryError("Unknown saved view field.")
    if any(not isinstance(v, str) or len(v) > 600 for v in params.values()):
        raise QueryError("Saved view values must be text of at most 600 characters.")
    return name.strip(), params


@logs_api.route("/api/v1/logs/views", methods=["GET", "POST", "DELETE"])
@roles("staff", "admin")
def saved_views():
    user = g.user
    views = list(user.saved_log_views or [])
    if request.method == "POST":
        name, params = clean_view(request.get_json(silent=True))
        views = [view for view in views if view.get("name") != name]
        if len(views) >= MAX_VIEWS:
            raise QueryError("Keep at most 20 saved views; delete one first.")
        views.append({"name": name, "params": params})
        user.saved_log_views = sorted(views, key=lambda view: view["name"].lower())
        db.session.commit()
    elif request.method == "DELETE":
        name = request.args.get("name", "")
        remaining = [view for view in views if view.get("name") != name]
        if len(remaining) == len(views):
            raise NotFound()
        user.saved_log_views = remaining
        db.session.commit()
    response = jsonify(views=user.saved_log_views or [])
    response.headers["Cache-Control"] = "no-store"
    return response
