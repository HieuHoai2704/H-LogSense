"""Evidence for persisted anomalies: bounded, redacted rows from the database.

``load_evidence`` reads one anomaly's raw record, parsed event and detector provenance (also used by the
opt-in private result API). ``evidence`` fulfils the Evidence Drawer contract that the synthetic fixtures
in ``app.services.evidence`` also serve, scoped to the validated investigation state.
"""

from datetime import timedelta
import hashlib
import json

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import and_, func, or_, select
from werkzeug.exceptions import NotFound

from app.contracts import anomaly_id_of, anomaly_identity, dataset_id_of
from app.extensions import db
from app.models import (
    AnomalyOutput as A,
    Dataset,
    DetectionUnit as U,
    Detector as D,
    DetectorRun as R,
    DetectorVersion as V,
    LogEvent as E,
    RawLogRecord,
    SourceArtifact,
    UnitEvent,
)
from app.services.evidence import bounded_fields
from app.services.investigation import QueryError, instant, integer, iso
from app.services.mysql_investigation import HOST, base, row_summary, state
from app.services.redaction import redact


def load_evidence(session, dataset_id, anomaly_id, *, raw_offset=0, raw_limit=2048):
    if raw_offset < 0 or not 128 <= raw_limit <= 8192:
        raise ValueError("Invalid raw pagination.")
    anomaly = session.scalar(
        select(A)
        .join(
            R,
            (R.id == A.run_id) & (R.dataset_id == A.dataset_id),
        )
        .where(
            A.dataset_id == dataset_id,
            A.id == anomaly_id,
            R.state == "completed",
        )
    )
    if anomaly is None:
        return None
    unit = session.scalar(select(U).where(U.dataset_id == dataset_id, U.id == anomaly.unit_id))
    run = session.get(R, anomaly.run_id)
    version = session.get(V, run.version_id)
    event = (
        session.scalar(select(E).where(E.dataset_id == dataset_id, E.id == unit.event_id))
        if unit.event_id
        else None
    )
    result = {
        "mode": "database",
        "synthetic": False,
        "dataset_id": dataset_id,
        "anomaly": {
            "id": anomaly.id,
            "priority": anomaly.priority,
            "anchor_utc": anomaly.anchor_time.isoformat(),
        },
        "detection_unit": {
            "id": unit.id,
            "kind": unit.kind,
            "start": unit.start_time.isoformat(),
            "end": unit.end_time.isoformat() if unit.end_time else None,
        },
        "detector": {
            "id": run.detector_id,
            "version": version.version,
            "run_id": run.id,
            "feature_schema": version.feature_schema,
            "score": anomaly.score,
            "score_direction": version.score_direction,
            "score_is_probability": False,
            "evidence": redact(anomaly.evidence),
            "explanation_status": "Explanation unavailable",
        },
        "raw_event": None,
        "related_events": [],
        "availability": {"raw": "unavailable", "related": "unavailable"},
        "causation": "An anomaly signal is not a confirmed root cause.",
    }
    # Data mode must come from the actual dataset, never from the provider name.
    from app.models import Dataset

    dataset = session.get(Dataset, dataset_id)
    result["synthetic"] = (
        True if dataset.data_mode == "synthetic" else False if dataset.data_mode == "real" else None
    )
    result["data_mode"] = dataset.data_mode
    if event is None:
        return result
    raw_meta = session.execute(
        select(
            RawLogRecord.id,
            RawLogRecord.artifact_id,
            RawLogRecord.line_number,
            RawLogRecord.byte_offset,
            func.length(RawLogRecord.raw_bytes),
        ).where(RawLogRecord.dataset_id == dataset_id, RawLogRecord.id == event.raw_id)
    ).one()
    if raw_meta[-1] > 262144:
        result["availability"]["raw"] = "exceeds_safe_inline_limit"
        return result
    raw_bytes = session.scalar(
        select(RawLogRecord.raw_bytes).where(
            RawLogRecord.dataset_id == dataset_id, RawLogRecord.id == event.raw_id
        )
    )
    text = redact(raw_bytes.decode("utf-8", errors="replace"))
    if raw_offset > len(text):
        raise ValueError("Raw offset beyond available evidence.")
    artifact = session.get(SourceArtifact, raw_meta.artifact_id)
    parsed, truncated = bounded_fields(redact(event.attributes))
    result["raw_event"] = {
        "text": text[raw_offset : raw_offset + raw_limit],
        "offset": raw_offset,
        "total_chars": len(text),
        "next_offset": raw_offset + raw_limit if raw_offset + raw_limit < len(text) else None,
        "redacted": True,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "raw_timestamp": event.raw_timestamp,
        "parsed_timestamp": event.timestamp.isoformat(),
        "host": redact(event.host),
        "service": redact(event.service),
        "source_artifact": artifact.artifact_key,
        "source_archive_sha256": artifact.sha256,
        "source_line": raw_meta.line_number,
        "uncompressed_byte_offset": raw_meta.byte_offset,
        "parser_version": event.parser_version,
        "parsed_attributes": parsed,
        "attributes_truncated": truncated,
        "parsing_status": "parsed",
    }
    result["availability"]["raw"] = "available"
    if event.host is not None:
        start, end = (
            event.timestamp - timedelta(minutes=5),
            event.timestamp + timedelta(minutes=5),
        )
        rows = session.execute(
            select(E.id, E.timestamp, E.host, E.service)
            .where(
                E.dataset_id == dataset_id,
                E.host == event.host,
                E.id != event.id,
                E.timestamp >= start,
                E.timestamp < end,
            )
            .order_by(E.timestamp, E.id)
            .limit(11)
        ).all()
        result["related_events"] = [
            dict(
                id=r.id,
                timestamp=r.timestamp.isoformat(),
                host=redact(r.host),
                service=redact(r.service),
                reason="Same supplied Node, within [anchor-5m, anchor+5m)",
            )
            for r in rows[:10]
        ]
        result["availability"]["related"] = "first_10_only" if len(rows) > 10 else "available"
    return result


RAW_INLINE_LIMIT = 262144  # bytes; the same inline bound as load_evidence
RELATIONS = ["same_host", "same_service", "before", "after", "context_window", "same_session", "same_window"]
QUERYABLE_RELATIONS = {"same_host", "same_service", "before", "after", "context_window", "same_window"}
CURSOR_MAX_AGE = 900  # seconds
NO_RAW = {"text": "", "offset": 0, "total_chars": 0, "next_offset": None}


def raw_bounds(args):
    return (
        integer(args.get("raw_offset", 0), 0, 10000000, "Raw offset"),
        integer(args.get("raw_limit", 2048), 128, 8192, "Raw limit"),
    )


def scoped_anomaly(scope, dataset_id, anomaly_id):
    """The anomaly with its unit, event, detector, run and version, only from a completed run in scope."""
    row = db.session.execute(
        select(A, U, E, D, R, V)
        .join(U, (U.id == A.unit_id) & (U.dataset_id == A.dataset_id))
        .outerjoin(E, E.id == U.event_id)
        .join(R, R.id == A.run_id)
        .join(D, D.id == R.detector_id)
        .join(V, V.id == R.version_id)
        .where(
            A.dataset_id == dataset_id,
            A.id == anomaly_id,
            A.run_id.in_([int(x) for x in scope["run_id"]]),
            R.state == "completed",
        )
    ).first()
    if row is None:
        raise NotFound()
    return row


def sampled_raw(args, dataset_id, unit):
    """For a window unit (no single event): the first member event's raw line, clearly marked as a sample."""
    sample = db.session.scalar(
        select(UnitEvent.event_id)
        .where(UnitEvent.dataset_id == dataset_id, UnitEvent.unit_id == unit.id)
        .order_by(UnitEvent.id)
        .limit(1)
    )
    parsed = db.session.get(E, sample) if sample else None
    if parsed is None:
        return None
    size = db.session.scalar(
        select(func.length(RawLogRecord.raw_bytes)).where(
            RawLogRecord.dataset_id == dataset_id, RawLogRecord.id == parsed.raw_id
        )
    )
    if size is None or size > RAW_INLINE_LIMIT:
        return None
    # The unit stays the window in the contract; this row only supports it.
    raw = db.session.get(RawLogRecord, parsed.raw_id)
    artifact = db.session.get(SourceArtifact, raw.artifact_id)
    full = redact(raw.raw_bytes.decode("utf-8", errors="replace"))
    offset = integer(args.get("raw_offset", 0), 0, len(full), "Raw offset")
    limit = integer(args.get("raw_limit", 2048), 128, 8192, "Raw limit")
    return {
        "text": full[offset : offset + limit],
        "offset": offset,
        "total_chars": len(full),
        "next_offset": offset + limit if offset + limit < len(full) else None,
        "raw_timestamp": parsed.raw_timestamp,
        "parsed_timestamp": iso(parsed.timestamp),
        "host": parsed.host,
        "service": parsed.service,
        "source_artifact": artifact.artifact_key,
        "source_line": raw.line_number,
        "parsed_attributes": redact(parsed.attributes),
        "parsing_status": "parsed; sampled supporting event for observed window",
    }


def raw_material(args, dataset_id, anomaly_id, unit):
    """The anomaly's own raw text page, else a sampled member line, else nothing."""
    raw_offset, raw_limit = raw_bounds(args)
    try:
        material = load_evidence(
            db.session, dataset_id, anomaly_id, raw_offset=raw_offset, raw_limit=raw_limit
        )
    except ValueError:  # offset past the raw text: a client error, as on /api/v1/database
        raise QueryError("Raw offset is beyond the available evidence.") from None
    supplied = material.get("raw_event")
    if supplied is None:
        supplied = sampled_raw(args, dataset_id, unit)
    return supplied or dict(NO_RAW)


def raw_page(supplied, args):
    return {
        "text": supplied["text"],
        "offset": supplied["offset"],
        "total_chars": supplied["total_chars"],
        "limit": raw_bounds(args)[1],
        "has_more": supplied["next_offset"] is not None,
        "next_offset": supplied["next_offset"],
        "synthetic": False,
        "redacted": True,
        "redaction_note": "Pattern redaction before pagination; not exhaustive PII detection.",
    }


def raw_provenance(supplied, metadata):
    upload = (supplied.get("parsed_attributes") or {}).get("upload")
    return {
        "raw_timestamp": supplied.get("raw_timestamp"),
        "parsed_timestamp": supplied.get("parsed_timestamp"),
        "host": supplied.get("host"),
        "source_file": supplied.get("source_artifact"),
        "source_line": supplied.get("source_line"),
        "event_reference": metadata["id"],
        "parsing_status": supplied.get("parsing_status", "unavailable"),
        "original_log_available": bool(supplied.get("source_line")),
        "upload": upload,
        "source_kind": "normalized-upload" if upload else "operator-source",
    }


def neighbours(scope, anomaly):
    """Whether the anomaly is in the result scope, and the newer/older result next to it (result order)."""
    results = base(scope, selection=True)
    in_scope = db.session.execute(results.where(A.id == anomaly.id).limit(1)).first() is not None
    if not in_scope:
        return False, None, None
    newer = or_(
        A.anchor_time > anomaly.anchor_time, and_(A.anchor_time == anomaly.anchor_time, A.id > anomaly.id)
    )
    older = or_(
        A.anchor_time < anomaly.anchor_time, and_(A.anchor_time == anomaly.anchor_time, A.id < anomaly.id)
    )
    previous = db.session.scalar(
        results.with_only_columns(A.id).where(newer).order_by(A.anchor_time, A.id).limit(1)
    )
    following = db.session.scalar(
        results.with_only_columns(A.id).where(older).order_by(A.anchor_time.desc(), A.id.desc()).limit(1)
    )
    return True, previous, following


def related_events(args, scope, dataset_id, anomaly, unit, metadata):
    """One keyset page of persisted anomalies related to this one, ignoring the result filters."""
    relation = args.get("relation", "same_host")
    seconds = integer(args.get("context_seconds", 1800), 1, 3600, "Context seconds")
    limit = integer(args.get("context_limit", 10), 1, 50, "Context limit")
    if relation not in QUERYABLE_RELATIONS:
        raise QueryError("Relationship unavailable.")
    start, end = (
        anomaly.anchor_time - timedelta(seconds=seconds),
        anomaly.anchor_time + timedelta(seconds=seconds),
    )
    if relation == "same_window":
        if unit.end_time is None:
            raise QueryError("No interval supplied.")
        start, end = unit.start_time, unit.end_time
    unfiltered = dict(
        scope,
        start_time=iso(start),
        end_time=iso(end),
        host=[],
        service=[],
        severity=[],
        detector=[],
        q="",
        selection_start="",
        selection_end="",
        selection_detector="",
    )
    query = base(unfiltered).where(A.id != anomaly.id)
    host, service = metadata["host"], metadata["service"]
    if relation == "same_host":
        query = query.where(host == HOST) if host else query.where(A.id < 0)
    elif relation == "same_service":
        query = query.where(E.service == service) if service else query.where(A.id < 0)
    elif relation == "before":
        query = query.where(A.anchor_time < anomaly.anchor_time)
    elif relation == "after":
        query = query.where(A.anchor_time > anomaly.anchor_time)
    fingerprint = hashlib.sha256(
        json.dumps([dataset_id, anomaly.id, scope["run_id"], relation, iso(start), iso(end), limit]).encode()
    ).hexdigest()
    signer = URLSafeTimedSerializer(current_app.config["EVIDENCE_CURSOR_SECRET"], salt="mysql-related")
    cursor = args.get("context_cursor")
    if cursor:
        try:
            position = signer.loads(cursor, max_age=CURSOR_MAX_AGE)
            if position["scope"] != fingerprint:
                raise ValueError()
            stamp = instant(position["time"])
            cid = integer(position["id"], 1, 2**63 - 1, "Cursor")
            query = query.where(or_(A.anchor_time > stamp, and_(A.anchor_time == stamp, A.id > cid)))
        except (BadData, ValueError, KeyError):
            raise QueryError("Related cursor expired or scope changed.") from None
    rows = db.session.execute(query.order_by(A.anchor_time, A.id).limit(limit + 1)).all()
    next_cursor = (
        signer.dumps(
            {"scope": fingerprint, "time": iso(rows[limit - 1][0].anchor_time), "id": rows[limit - 1][0].id}
        )
        if len(rows) > limit
        else None
    )
    return dict(
        items=[
            row_summary(r, scope)
            | {"relationship_reasons": [relation, "Within explicit context [start,end)"]}
            for r in rows[:limit]
        ],
        has_more=next_cursor is not None,
        next_cursor=next_cursor,
        limit=limit,
        relation=relation,
        interval={"start": iso(start), "end": iso(end)},
        available_relations=[
            dict(
                value=k, available=(unit.end_time is not None if k == "same_window" else k != "same_session")
            )
            for k in RELATIONS
        ],
    )


def detector_evidence(anomaly, unit, detector, run, version):
    """What the run recorded about this detection; ML runs have no explanation."""
    model = detector.family != "rule"
    stored = anomaly.evidence
    return {
        "kind": "ml" if model else "rule",
        "method": detector.detector_key,
        "model_name": detector.detector_key,
        "model_version": version.version,
        "model_run_id": run.id,
        "feature_schema": version.feature_schema,
        "feature_evidence": stored.get("feature_values"),
        "rule_id": detector.detector_key if not model else None,
        "rule_version": version.version if not model else None,
        "observed_value": stored.get("observed_event_count", stored.get("feature_values")),
        "configured_threshold": stored.get("threshold"),
        "reference_statistics": stored.get("reference"),
        "observation_window": {"start": iso(unit.start_time), "end": iso(unit.end_time)}
        if unit.end_time
        else None,
        "score": anomaly.score,
        "score_direction": version.score_direction,
        "score_interpretation": "Native detector score, not probability or confirmed cause. Do not compare scales across detectors.",
        "detection_unit": unit.kind,
        "explanation_status": "Explanation unavailable" if model else "Actual configured rule evidence",
    }


def evidence(identity, args):
    """The Evidence Drawer contract for one persisted anomaly in the validated investigation scope."""
    anomaly_id = anomaly_id_of(identity)
    scope = state(args)
    dataset_id = dataset_id_of(scope["source"])
    row = scoped_anomaly(scope, dataset_id, anomaly_id)
    anomaly, unit, _, detector, run, version = row
    metadata = row_summary(row, scope)
    metadata.update(
        dataset_id=dataset_id, dataset_name=db.session.get(Dataset, dataset_id).name, model_run_id=run.id
    )
    supplied = raw_material(args, dataset_id, anomaly_id, unit)
    page = raw_page(supplied, args)
    in_scope, previous, following = neighbours(scope, anomaly)
    related = related_events(args, scope, dataset_id, anomaly, unit, metadata)
    return redact(
        dict(
            schema_version="1.0",
            mode="database",
            revision="mysql-runs-" + ",".join(scope["run_id"]),
            anomaly=metadata,
            summary={"observed_signal": metadata["message"], "hypotheses": [], "root_cause": None},
            raw_event={"page": page, "provenance": raw_provenance(supplied, metadata)},
            parsed_fields=supplied.get("parsed_attributes"),
            detector_evidence=detector_evidence(anomaly, unit, detector, run, version),
            related_events=related,
            navigation={
                "previous_id": anomaly_identity(previous) if previous else None,
                "next_id": anomaly_identity(following) if following else None,
                "in_result_scope": in_scope,
                "note": "Persisted results in the current scope; related records may be outside filters.",
            },
            availability={
                "raw_event": "actual" if supplied.get("source_line") else "unavailable",
                "redaction": page["redaction_note"],
            },
        )
    )
