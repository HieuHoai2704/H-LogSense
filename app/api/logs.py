"""Authorized, bounded parsed-log API. Raw log levels are not anomaly priorities."""

from werkzeug.exceptions import NotFound

import csv, io
from datetime import timedelta

from flask import (
    Blueprint,
    jsonify,
    request,
    Response,
    stream_with_context,
    current_app,
)
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Dataset, LogEvent, RawLogRecord, SourceArtifact, GroundTruthLabel
from app.security import authorized_datasets, Forbidden, identity
from app.services.investigation import QueryError, integer, iso
from app.services.log_queries import parse_scope, page, predicates, timeline
from app.services.redaction import redact
from app.services.csv_safety import safe_cell

logs_api = Blueprint("logs", __name__)


@logs_api.errorhandler(QueryError)
def invalid(error):
    return jsonify(error={"code": "invalid_query", "message": str(error)}), 400


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
    event = db.session.scalar(
        select(LogEvent).where(*predicates(scope), LogEvent.id == event_id)
    )
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
        ground_truth_label_provenance={"source": annotation.source, "version": annotation.version,
            "note": "Imported annotation; not an unsupervised model feature."} if annotation else None,
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
            "source_kind": "normalized-upload" if (event.attributes or {}).get("upload") else "operator-source",
        },
    )


@logs_api.get("/api/v1/logs/export")
def export():
    scope = parse_scope(db.session, request.args)
    count = db.session.scalar(
        select(func.count()).select_from(LogEvent).where(*predicates(scope))
    )
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
            select(LogEvent)
            .where(*predicates(scope))
            .order_by(*order)
            .execution_options(yield_per=50)
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
