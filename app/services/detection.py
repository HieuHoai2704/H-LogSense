"""First event-unit baselines. Labels are never queried or used as features."""

import hashlib
import json
import math
import platform
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from app.paths import MODEL_ARTIFACTS_DIR
from app.models import (
    Dataset,
    LogEvent,
    DetectionUnit,
    UnitEvent,
    Detector,
    DetectorVersion,
    DetectorRun,
    AnomalyOutput,
)

FEATURES = ["message_character_count", "message_token_count", "high_severity_indicator"]
ERROR_LEVELS = frozenset({"ERROR", "FATAL", "SEVERE", "FAILURE"})


def features(message, severity):
    """No label, raw prefix, event ID, host ID or absolute timestamp feature."""
    return [len(message), len(message.split()), int(severity in ERROR_LEVELS)]


def _events(session, dataset_id, cursor, limit):
    query = select(
        LogEvent.id, LogEvent.timestamp, LogEvent.message, LogEvent.severity
    ).where(LogEvent.dataset_id == dataset_id)
    if cursor:
        timestamp, event_id = cursor
        query = query.where(
            or_(
                LogEvent.timestamp > timestamp,
                and_(LogEvent.timestamp == timestamp, LogEvent.id > event_id),
            )
        )
    return session.execute(
        query.order_by(LogEvent.timestamp, LogEvent.id).limit(limit)
    ).all()


def detect(
    engine,
    dataset_id,
    *,
    kind="rule",
    train_size=1000,
    batch_size=500,
    artifact_root=None,
    seed=42,
):
    if (
        kind not in {"rule", "isolation_forest"}
        or not 1 <= batch_size <= 1000
        or not 16 <= train_size <= 20000
    ):
        raise ValueError("Invalid detector configuration.")
    model = None
    cursor = None
    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None or dataset.state not in {"partial", "imported"}:
            raise ValueError("Dataset is not ready for detection.")
        revision = dataset.input_revision
        if kind == "isolation_forest":
            training = _events(session, dataset_id, None, train_size)
            if len(training) < train_size:
                raise ValueError("Insufficient training events.")
            cursor = (training[-1].timestamp, training[-1].id)
            train_cursor = cursor
            x = np.asarray(
                [features(r.message, r.severity) for r in training], dtype=np.float64
            )
            model = IsolationForest(
                n_estimators=100,
                max_samples=min(256, train_size),
                contamination="auto",
                random_state=seed,
                n_jobs=1,
            ).fit(x)
            distinct_training_vectors = len(np.unique(x, axis=0))
            del x, training
    configuration = {
        "feature_schema_version": "bgl-event-features-1",
        "seed": seed,
        "unit": "event",
        "threshold": 1 if model is None else float(model.offset_),
        "comparison": ">=" if model is None else "<",
        "score_semantics": "high_severity_indicator"
        if model is None
        else "sklearn.score_samples",
        "priority_policy": "fixed High for rule; fixed Medium for IF; no common score scale",
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
    }
    if model is not None:
        root = Path(artifact_root) if artifact_root else MODEL_ARTIFACTS_DIR
        root.mkdir(parents=True, exist_ok=True)
        model_key = uuid4().hex + ".joblib"
        path = root / model_key
        joblib.dump(model, path)
        configuration.update(
            model_artifact_key=model_key,
            model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            training_count=train_size,
            training_distinct_vectors=distinct_training_vectors,
            training_end_utc=train_cursor[0].isoformat(),
            training_end_id=train_cursor[1],
            training_policy="first N chronological events, label-blind; later events scored",
            estimators=100,
            max_samples=min(256, train_size),
        )
    version_key = hashlib.sha256(
        json.dumps(configuration, sort_keys=True).encode()
    ).hexdigest()
    with Session(engine) as session, session.begin():
        # A single dataset lock serializes detector registration with other runs.
        dataset = session.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
        if dataset.input_revision != revision:
            if model is not None:
                path.unlink(missing_ok=True)  # never leave an orphaned model behind
            raise ValueError("Dataset revision changed during training.")
        detector = session.scalar(
            select(Detector).where(Detector.detector_key == "bgl-" + kind)
        )
        if detector is None:
            detector = Detector(
                detector_key="bgl-" + kind,
                family="rule" if model is None else "classical_ml",
            )
            session.add(detector)
            session.flush()
        version = session.scalar(
            select(DetectorVersion).where(
                DetectorVersion.detector_id == detector.id,
                DetectorVersion.version == version_key,
            )
        )
        if version is None:
            version = DetectorVersion(
                detector_id=detector.id,
                version=version_key,
                configuration=configuration,
                feature_schema={"names": FEATURES, "version": "1", "label_free": True},
                score_direction="higher" if model is None else "lower",
            )
            session.add(version)
            session.flush()
        run = DetectorRun(
            dataset_id=dataset_id,
            detector_id=detector.id,
            version_id=version.id,
            run_key=uuid4().hex,
            state="running",
            input_revision=revision,
            configuration=dict(configuration, input_revision=revision),
        )
        session.add(run)
        session.flush()
        run_id = run.id
    flagged = 0
    try:
        while True:
            with Session(engine) as session, session.begin():
                dataset = session.scalar(
                    select(Dataset).where(Dataset.id == dataset_id).with_for_update()
                )
                if dataset.input_revision != revision or dataset.state == "archived":
                    raise ValueError(
                        "Dataset changed; analysis stopped without publication."
                    )
                rows = _events(session, dataset_id, cursor, batch_size)
                run = session.get(DetectorRun, run_id)
                if not rows:
                    run.state = "completed"
                    break
                matrix = np.asarray(
                    [features(r.message, r.severity) for r in rows], dtype=np.float64
                )
                scores = matrix[:, 2] if model is None else model.score_samples(matrix)
                selected = [
                    (row, float(score), feature.tolist())
                    for row, score, feature in zip(rows, scores, matrix)
                    if (score >= 1 if model is None else score < model.offset_)
                ]
                for row, score, values in selected:
                    if not math.isfinite(score):
                        raise ValueError("Non-finite detector score.")
                    key = "event:" + str(row.id)
                    unit = session.scalar(
                        select(DetectionUnit).where(
                            DetectionUnit.dataset_id == dataset_id,
                            DetectionUnit.unit_key == key,
                        )
                    )
                    if unit is None:
                        unit = DetectionUnit(
                            dataset_id=dataset_id,
                            unit_key=key,
                            kind="event",
                            event_id=row.id,
                            start_time=row.timestamp,
                        )
                        session.add(unit)
                        session.flush()
                        session.add(
                            UnitEvent(
                                dataset_id=dataset_id, unit_id=unit.id, event_id=row.id
                            )
                        )
                    session.add(
                        AnomalyOutput(
                            dataset_id=dataset_id,
                            run_id=run_id,
                            unit_id=unit.id,
                            anchor_time=row.timestamp,
                            priority="High" if model is None else "Medium",
                            score=score,
                            evidence={
                                "feature_names": FEATURES,
                                "feature_values": values,
                                "threshold": configuration["threshold"],
                                "comparison": configuration["comparison"],
                                "explanation": "Configured severity rule matched."
                                if model is None
                                else "Explanation unavailable",
                                "score_is_probability": False,
                            },
                        )
                    )
                run.evaluated_units += len(rows)
                flagged += len(selected)
                cursor = (rows[-1].timestamp, rows[-1].id)
    except Exception:
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "failed"
        raise
    with Session(engine) as session:
        run = session.get(DetectorRun, run_id)
        return dict(
            run_id=run_id,
            kind=kind,
            evaluated_units=run.evaluated_units,
            anomaly_outputs=flagged,
            state=run.state,
            input_revision=revision,
        )
