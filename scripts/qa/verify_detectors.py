"""Evaluate persisted baselines against held-out BGL event labels, without tuning."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import secrets
import time

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import (
    Dataset,
    LogEvent,
    GroundTruthLabel,
    DetectionUnit,
    AnomalyOutput,
    DetectorRun,
    DetectorVersion,
    Detector,
)
from app.services.detection import detect

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def verify(dataset_id, *, reuse=False):
    app = create_app()
    report = []
    with app.app_context():
        if not db.engine.url.database.startswith("logsense_bench_"):
            raise ValueError("Use the isolated benchmark schema.")
        for kind in ("rule", "isolation_forest"):
            if reuse:
                with Session(db.engine) as session:
                    run = session.scalar(
                        select(DetectorRun)
                        .join(Detector, Detector.id == DetectorRun.detector_id)
                        .where(
                            DetectorRun.dataset_id == dataset_id,
                            Detector.detector_key == "bgl-" + kind,
                            DetectorRun.state == "completed",
                        )
                        .order_by(DetectorRun.id.desc())
                        .limit(1)
                    )
                    if run is None:
                        raise ValueError("No completed run available to verify.")
                    result = dict(
                        run_id=run.id,
                        kind=kind,
                        evaluated_units=run.evaluated_units,
                        anomaly_outputs=session.scalar(
                            select(func.count())
                            .select_from(AnomalyOutput)
                            .where(
                                AnomalyOutput.dataset_id == dataset_id,
                                AnomalyOutput.run_id == run.id,
                            )
                        ),
                        state=run.state,
                        input_revision=run.input_revision,
                    )
                duration = (
                    None  # Do not fabricate timing for a previously completed run.
                )
            else:
                started = time.perf_counter()
                result = detect(db.engine, dataset_id, kind=kind, train_size=10000)
                duration = time.perf_counter() - started
            with Session(db.engine) as session:
                run = session.get(DetectorRun, result["run_id"])
                dataset = session.get(Dataset, dataset_id)
                assert dataset.data_mode == "real"
                version = session.get(DetectorVersion, run.version_id)
                predictions = (
                    select(DetectionUnit.event_id.label("event_id"))
                    .select_from(AnomalyOutput)
                    .join(
                        DetectionUnit,
                        (DetectionUnit.id == AnomalyOutput.unit_id)
                        & (DetectionUnit.dataset_id == AnomalyOutput.dataset_id),
                    )
                    .where(
                        AnomalyOutput.dataset_id == dataset_id,
                        AnomalyOutput.run_id == run.id,
                    )
                    .distinct()
                    .subquery()
                )
                predicted = predictions.c.event_id.is_not(None)
                actual = GroundTruthLabel.label != "-"
                query = (
                    select(
                        func.sum(case((and_(actual, predicted), 1), else_=0)),
                        func.sum(case((and_(~actual, predicted), 1), else_=0)),
                        func.sum(case((and_(actual, ~predicted), 1), else_=0)),
                        func.sum(case((and_(~actual, ~predicted), 1), else_=0)),
                        func.count(),
                    )
                    .select_from(LogEvent)
                    .join(
                        GroundTruthLabel,
                        (GroundTruthLabel.event_id == LogEvent.id)
                        & (GroundTruthLabel.dataset_id == LogEvent.dataset_id),
                    )
                    .outerjoin(predictions, predictions.c.event_id == LogEvent.id)
                    .where(
                        LogEvent.dataset_id == dataset_id,
                        GroundTruthLabel.source == "loghub-bgl",
                        GroundTruthLabel.version == "original",
                    )
                )
                if kind == "isolation_forest":
                    end = datetime.fromisoformat(run.configuration["training_end_utc"])
                    event_id = run.configuration["training_end_id"]
                    query = query.where(
                        or_(
                            LogEvent.timestamp > end,
                            and_(LogEvent.timestamp == end, LogEvent.id > event_id),
                        )
                    )
                tp, fp, fn, tn, labeled = session.execute(query).one()
                tp, fp, fn, tn = [int(v or 0) for v in (tp, fp, fn, tn)]
                assert labeled == run.evaluated_units
                assert tp + fp == result["anomaly_outputs"]
                precision = tp / (tp + fp) if tp + fp else None
                recall = tp / (tp + fn) if tp + fn else None
                f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
                item = dict(
                    **result,
                    dataset_id=dataset_id,
                    schema=db.engine.url.database,
                    wall_seconds=duration,
                    model_or_rule_version=version.version,
                    detection_unit="event",
                    features=version.feature_schema["names"],
                    threshold=run.configuration["threshold"],
                    comparison=run.configuration["comparison"],
                    training_count=run.configuration.get("training_count", 0),
                    training_distinct_vectors=run.configuration.get(
                        "training_distinct_vectors"
                    ),
                    evaluation="Original BGL label != dash; event-level; no point adjustment. Prefix case study only, no tuning or generalization claim.",
                    tp=tp,
                    fp=fp,
                    fn=fn,
                    tn=tn,
                    precision=precision,
                    recall=recall,
                    f1=f1,
                )
                first_id = session.scalar(
                    select(AnomalyOutput.id)
                    .where(
                        AnomalyOutput.dataset_id == dataset_id,
                        AnomalyOutput.run_id == run.id,
                    )
                    .order_by(AnomalyOutput.id)
                    .limit(1)
                )
            token = secrets.token_hex(32)
            app.config.update(
                DATABASE_READ_TOKEN=token, DATABASE_ALLOWED_DATASETS=(dataset_id,)
            )
            if first_id is not None:
                # This verifier deliberately retains an outer Flask app context.
                # End its previous read snapshot before making a new HTTP request.
                db.session.remove()
                response = app.test_client().get(
                    f"/api/v1/database/anomalies/{first_id}/evidence?dataset_id={dataset_id}",
                    headers={"Authorization": "Bearer " + token},
                )
                assert (
                    response.status_code == 200
                    and response.json["raw_event"]["source_line"] > 0
                )
                assert (
                    response.json["synthetic"] is False
                    and response.json["availability"]["raw"] == "available"
                )
                assert (
                    response.json["detector"]["version"]
                    == item["model_or_rule_version"]
                )
                item["real_evidence_api"] = "PASS"
            else:
                item["real_evidence_api"] = "NOT RUN: this run flagged no anomaly"
            item["existing_drawer_ui"] = (
                "NOT CONNECTED: existing workspace remains explicitly synthetic"
            )
            report.append(item)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=int, required=True)
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()
    result = verify(args.dataset, reuse=args.reuse)
    path = (REPO_ROOT / "docs/database/measurements/detectors.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
