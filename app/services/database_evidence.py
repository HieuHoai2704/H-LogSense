"""Evidence from persisted rows; bounded and redacted before serialization."""

from datetime import timedelta
import hashlib

from sqlalchemy import func, select

from app.models import (
    AnomalyOutput,
    DetectionUnit,
    DetectorRun,
    DetectorVersion,
    LogEvent,
    RawLogRecord,
    SourceArtifact,
)
from app.services.evidence import bounded_fields
from app.services.redaction import redact


def load_evidence(session, dataset_id, anomaly_id, *, raw_offset=0, raw_limit=2048):
    if raw_offset < 0 or not 128 <= raw_limit <= 8192:
        raise ValueError("Invalid raw pagination.")
    anomaly = session.scalar(
        select(AnomalyOutput)
        .join(
            DetectorRun,
            (DetectorRun.id == AnomalyOutput.run_id) & (DetectorRun.dataset_id == AnomalyOutput.dataset_id),
        )
        .where(
            AnomalyOutput.dataset_id == dataset_id,
            AnomalyOutput.id == anomaly_id,
            DetectorRun.state == "completed",
        )
    )
    if anomaly is None:
        return None
    unit = session.scalar(
        select(DetectionUnit).where(
            DetectionUnit.dataset_id == dataset_id, DetectionUnit.id == anomaly.unit_id
        )
    )
    run = session.get(DetectorRun, anomaly.run_id)
    version = session.get(DetectorVersion, run.version_id)
    event = (
        session.scalar(
            select(LogEvent).where(LogEvent.dataset_id == dataset_id, LogEvent.id == unit.event_id)
        )
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
            select(LogEvent.id, LogEvent.timestamp, LogEvent.host, LogEvent.service)
            .where(
                LogEvent.dataset_id == dataset_id,
                LogEvent.host == event.host,
                LogEvent.id != event.id,
                LogEvent.timestamp >= start,
                LogEvent.timestamp < end,
            )
            .order_by(LogEvent.timestamp, LogEvent.id)
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
