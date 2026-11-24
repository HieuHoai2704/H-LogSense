"""Label-blind observed host-window baselines; deterministic chronological split."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib, json, math, re
from uuid import uuid4

import joblib, numpy as np, sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score
from sqlalchemy import select, func, case, text
from sqlalchemy.orm import Session

from app.paths import WINDOW_FEATURES_DIR
from app.models import (
    Dataset,
    LogEvent,
    DetectionUnit,
    UnitEvent,
    Detector,
    DetectorVersion,
    DetectorRun,
    AnomalyOutput,
    GroundTruthLabel,
)
from app.domain import DetectionPrediction, EvaluationReport

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
FEATURE_NAMES = [
    "log1p_event_count",
    "high_severity_fraction",
    "distinct_template_fraction",
    "dominant_template_fraction",
    "log1p_mean_message_length",
]
SEVERE = {"ERROR", "FATAL", "SEVERE", "FAILURE"}


def template(message):
    # A transparent deterministic template policy, not an inferred Drain model.
    normalized = re.sub(r"\b(?:0x[0-9a-fA-F]+|\d+)\b", "<*>", message)
    return hashlib.sha256(normalized.encode()).hexdigest()


def second(stamp):
    delta = stamp - EPOCH
    return delta.days * 86400 + delta.seconds


def aggregate_windows(rows, seconds=300, include_templates=False):
    current = None
    groups = {}

    def emit():
        for host, group in sorted(groups.items()):
            n = group["n"]
            templates = group["templates"]
            unit = {
                "host": host,
                "bucket": current,
                "count": n,
                "sample_ids": group["sample"],
                "features": [
                    math.log1p(n),
                    group["errors"] / n,
                    len(templates) / n,
                    max(templates.values()) / n,
                    math.log1p(group["chars"] / n),
                ],
            }
            if include_templates:
                unit["templates"] = dict(templates)
            yield unit

    for row in rows:
        bucket = second(row.timestamp) // seconds
        if current is not None and bucket != current:
            yield from emit()
            groups = {}
        current = bucket
        if row.host is None:
            continue
        group = groups.setdefault(
            row.host,
            {"n": 0, "errors": 0, "chars": 0, "templates": Counter(), "sample": []},
        )
        group["n"] += 1
        group["errors"] += row.severity in SEVERE
        group["chars"] += len(row.message)
        group["templates"][template(row.message)] += 1
        if len(group["sample"]) < 20:
            group["sample"].append(row.id)
        if len(groups) > 50000 or len(group["templates"]) > 50000:
            raise ValueError(
                "Observed window exceeds bounded feature resources; choose shorter windows."
            )
    if current is not None:
        yield from emit()


def run_windows(engine, dataset_id, job_key, configuration):
    if "model_id" in configuration:
        from app.services.validated_if import run_validated

        return run_validated(engine, dataset_id, job_key, configuration)
    if "study_id" in configuration:
        from app.services.window_deployment import run_study

        return run_study(engine, dataset_id, job_key, configuration)
    kind = configuration.get("detector", "rule")
    seconds = int(configuration.get("window_seconds", 300))
    seed = int(configuration.get("seed", 42))
    if kind not in {"rule", "isolation_forest"} or seconds not in {60, 300, 900, 3600}:
        raise ValueError("Invalid window detector.")
    from app.services.investigation import instant, iso

    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None or dataset.state not in {"partial", "imported"}:
            raise ValueError("Dataset unavailable.")
        revision = dataset.input_revision
        maximum = session.scalar(
            select(func.max(LogEvent.id)).where(LogEvent.dataset_id == dataset_id)
        )
        first, last = session.execute(
            select(func.min(LogEvent.timestamp), func.max(LogEvent.timestamp)).where(
                LogEvent.dataset_id == dataset_id
            )
        ).one()
        if first is None:
            raise ValueError("No parsed events.")
    start = (
        instant(configuration["start_time"])
        if configuration.get("start_time")
        else EPOCH + timedelta(seconds=(second(first) // seconds) * seconds)
    )
    end = (
        instant(configuration["end_time"])
        if configuration.get("end_time")
        else EPOCH + timedelta(seconds=(second(last) // seconds + 1) * seconds)
    )
    if (
        start >= end
        or end - start > timedelta(days=366)
        or start.microsecond
        or end.microsecond
        or second(start) % seconds
        or second(end) % seconds
    ):
        raise ValueError("Use positive UTC-aligned whole windows, at most 366 days.")
    span = second(end) - second(start)
    train_end = EPOCH + timedelta(
        seconds=second(start) + (span // 2 // seconds) * seconds
    )
    validation_end = EPOCH + timedelta(
        seconds=second(start) + (span * 3 // 4 // seconds) * seconds
    )
    if not start < train_end < validation_end < end:
        raise ValueError("Range too short for disjoint temporal splits.")
    root = WINDOW_FEATURES_DIR
    root.mkdir(parents=True, exist_ok=True)
    file = root / (uuid4().hex + ".jsonl")
    training = []
    validation = []
    counts = {"train": 0, "validation": 0, "test": 0}
    with Session(engine) as session, file.open("w", encoding="utf-8") as output:
        rows = session.execute(
            select(
                LogEvent.id,
                LogEvent.timestamp,
                LogEvent.host,
                LogEvent.severity,
                LogEvent.message,
            )
            .where(
                LogEvent.dataset_id == dataset_id,
                LogEvent.id <= maximum,
                LogEvent.timestamp >= start,
                LogEvent.timestamp < end,
            )
            .order_by(LogEvent.timestamp, LogEvent.id)
            .execution_options(yield_per=500)
        )
        for unit in aggregate_windows(rows, seconds):
            stamp = EPOCH + timedelta(seconds=unit["bucket"] * seconds)
            phase = (
                "train"
                if stamp < train_end
                else "validation"
                if stamp < validation_end
                else "test"
            )
            unit["phase"] = phase
            counts[phase] += 1
            output.write(json.dumps(unit) + "\n")
            if phase == "train" and len(training) < 20000:
                training.append(unit["features"])
            if phase == "validation" and len(validation) < 20000:
                validation.append(unit["features"])
    if len(training) < 16 or not validation or not counts["test"]:
        raise ValueError("Insufficient observed train/validation/test windows.")
    x = np.asarray(training)
    v = np.asarray(validation)
    model = None
    if kind == "isolation_forest":
        model = IsolationForest(
            n_estimators=100,
            max_samples=min(256, len(training)),
            contamination="auto",
            random_state=seed,
            n_jobs=1,
        ).fit(x)
        threshold = float(np.quantile(model.score_samples(v), 0.01))
        model_path = root / (uuid4().hex + ".joblib")
        joblib.dump(model, model_path)
        artifact = {
            "key": model_path.name,
            "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        }
    else:
        threshold = float(np.quantile(np.expm1(x[:, 0]), 0.99))
        artifact = None
    reference = {
        "mean_event_count": float(np.expm1(x[:, 0]).mean()),
        "threshold": threshold,
    }
    config = dict(
        detector=kind,
        window_seconds=seconds,
        seed=seed,
        features=FEATURE_NAMES,
        feature_version="observed-host-window-1",
        template_policy="replace whole decimal/hex tokens with <*> then SHA256; v1",
        train_start=iso(start),
        train_end=iso(train_end),
        validation_end=iso(validation_end),
        test_end=iso(end),
        split_counts=counts,
        training_used=len(training),
        validation_used=len(validation),
        threshold=threshold,
        threshold_policy="training count p99"
        if model is None
        else "validation native-score p01, no labels",
        score_direction="higher" if model is None else "lower",
        reference=reference,
        model_artifact=artifact,
        sklearn=sklearn.__version__,
        input_revision=revision,
        maximum_event_id=maximum,
        feature_file_sha256=__import__(
            "app.services.bgl_ingestion", fromlist=["fingerprint"]
        ).fingerprint(file),
    )
    version_key = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    with Session(engine) as session, session.begin():
        ds = session.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
        if ds.input_revision != revision:
            raise ValueError("Dataset changed during feature creation.")
        detector = session.scalar(
            select(Detector).where(Detector.detector_key == "host-window-" + kind)
        )
        if detector is None:
            detector = Detector(
                detector_key="host-window-" + kind,
                family="rule" if model is None else "classical_ml",
            )
            session.add(detector)
            session.flush()
        run = session.scalar(
            select(DetectorRun).where(
                DetectorRun.dataset_id == dataset_id, DetectorRun.run_key == job_key
            )
        )
        if run is None:
            version = DetectorVersion(
                detector_id=detector.id,
                version=version_key,
                configuration=config,
                feature_schema={
                    "names": FEATURE_NAMES,
                    "version": "1",
                    "label_free": True,
                },
                score_direction=config["score_direction"],
            )
            session.add(version)
            session.flush()
            run = DetectorRun(
                dataset_id=dataset_id,
                detector_id=detector.id,
                version_id=version.id,
                run_key=job_key,
                state="running",
                input_revision=revision,
                configuration=config,
            )
            session.add(run)
            session.flush()
        elif run.input_revision != revision or any(
            run.configuration.get(k) != config.get(k)
            for k in (
                "detector",
                "window_seconds",
                "seed",
                "feature_file_sha256",
                "threshold",
            )
        ):
            raise ValueError(
                "Cannot retry against a different input or detector configuration."
            )
        if run.state == "completed":
            return {"run_id": run.id, "state": "completed", "retry": "idempotent"}
        run.state = "running"
        run_id = run.id
    try:
        with file.open(encoding="utf-8") as stream:
            batch = []
            for line in stream:
                record = json.loads(line)
                if record["phase"] != "test":
                    continue
                batch.append(record)
                if len(batch) == 200:
                    persist_predictions(
                        engine,
                        dataset_id,
                        revision,
                        maximum,
                        run_id,
                        batch,
                        model,
                        threshold,
                        reference,
                        seconds,
                    )
                    batch = []
            if batch:
                persist_predictions(
                    engine,
                    dataset_id,
                    revision,
                    maximum,
                    run_id,
                    batch,
                    model,
                    threshold,
                    reference,
                    seconds,
                )
        with Session(engine) as session, session.begin():
            run = session.get(DetectorRun, run_id)
            run.state = "completed"
        evaluate_windows(engine, dataset_id, run_id)
    except Exception:
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "failed"
        raise
    return {"run_id": run_id, "state": "completed", "split_counts": counts}


def persist_predictions(
    engine,
    dataset_id,
    revision,
    maximum,
    run_id,
    rows,
    model,
    threshold,
    reference,
    seconds,
    feature_names=None,
):
    feature_names = FEATURE_NAMES if feature_names is None else feature_names
    matrix = np.asarray([r["features"] for r in rows])
    scores = np.expm1(matrix[:, 0]) if model is None else model.score_samples(matrix)
    with Session(engine) as session, session.begin():
        dataset = session.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
        if dataset.input_revision != revision or dataset.state == "archived":
            raise ValueError("Input revision changed.")
        run = session.get(DetectorRun, run_id)
        for row, score in zip(rows, scores):
            if not math.isfinite(score):
                raise ValueError("Nonfinite score.")
            key = (
                f"hw1:{seconds}:{revision}:{row['bucket']}:"
                + hashlib.sha256(row["host"].encode()).hexdigest()[:32]
            )
            unit = session.scalar(
                select(DetectionUnit).where(
                    DetectionUnit.dataset_id == dataset_id,
                    DetectionUnit.unit_key == key,
                )
            )
            if unit is None:
                start = EPOCH + timedelta(seconds=row["bucket"] * seconds)
                unit = DetectionUnit(
                    dataset_id=dataset_id,
                    unit_key=key,
                    kind="window",
                    host=row["host"],
                    start_time=start,
                    end_time=start + timedelta(seconds=seconds),
                    definition={
                        "version": "observed-host-window-1",
                        "observed_event_count": row["count"],
                        "sampled_membership": True,
                        "maximum_event_id": maximum,
                        "input_revision": revision,
                    },
                )
                session.add(unit)
                session.flush()
                session.add_all(
                    [
                        UnitEvent(dataset_id=dataset_id, unit_id=unit.id, event_id=i)
                        for i in row["sample_ids"]
                    ]
                )
            existing = session.scalar(
                select(DetectionPrediction.id).where(
                    DetectionPrediction.dataset_id == dataset_id,
                    DetectionPrediction.run_id == run_id,
                    DetectionPrediction.unit_id == unit.id,
                )
            )
            if existing is not None:
                continue
            flagged = bool(score > threshold if model is None else score < threshold)
            session.add(
                DetectionPrediction(
                    dataset_id=dataset_id,
                    run_id=run_id,
                    unit_id=unit.id,
                    score=float(score),
                    predicted=flagged,
                    features={"names": feature_names, "values": row["features"]},
                )
            )
            if flagged:
                session.add(
                    AnomalyOutput(
                        dataset_id=dataset_id,
                        run_id=run_id,
                        unit_id=unit.id,
                        anchor_time=unit.start_time,
                        priority="High" if model is None else "Medium",
                        score=float(score),
                        evidence={
                            "observed_event_count": row["count"],
                            "reference": reference,
                            "threshold": threshold,
                            "comparison": ">" if model is None else "<",
                            "feature_names": feature_names,
                            "feature_values": row["features"],
                            "explanation": "Configured count threshold exceeded"
                            if model is None
                            else "Explanation unavailable",
                        },
                    )
                )
            run.evaluated_units += 1
        if run.run_key.startswith("job:") and run.run_key[4:].isdigit():
            from app.models import ProcessingJob

            job = session.get(ProcessingJob, int(run.run_key[4:]))
            if job is not None and job.dataset_id == dataset_id:
                job.processed_count = run.evaluated_units
                job.result = {"run_id": run.id, "evaluated_units": run.evaluated_units}


def evaluate_windows(engine, dataset_id, run_id):
    with Session(engine) as session, session.begin():
        run = session.get(DetectorRun, run_id)
        config = run.configuration
        seconds = config["window_seconds"]
        micros = func.timestampdiff(
            text("MICROSECOND"), EPOCH.replace(tzinfo=None), LogEvent.timestamp
        )
        divisor = seconds * 1000000
        bucket = micros.op("DIV", precedence=100)(divisor) - case(
            ((micros < 0) & (func.mod(micros, divisor) != 0), 1), else_=0
        )
        labels = session.execute(
            select(
                LogEvent.host,
                bucket,
                func.count(),
                func.max(case((GroundTruthLabel.label != "-", 1), else_=0)),
            )
            .join(
                GroundTruthLabel,
                (GroundTruthLabel.dataset_id == LogEvent.dataset_id)
                & (GroundTruthLabel.event_id == LogEvent.id),
            )
            .where(
                LogEvent.dataset_id == dataset_id,
                LogEvent.id <= config["maximum_event_id"],
                GroundTruthLabel.source == "loghub-bgl",
                GroundTruthLabel.version == "original",
            )
            .group_by(LogEvent.host, bucket)
        ).all()
        known = {(r[0], int(r[1])): (r[2], r[3]) for r in labels}
        truth = []
        predictions = []
        ranks = []
        skipped = 0
        for prediction, unit in session.execute(
            select(DetectionPrediction, DetectionUnit)
            .join(
                DetectionUnit,
                (DetectionUnit.dataset_id == DetectionPrediction.dataset_id)
                & (DetectionUnit.id == DetectionPrediction.unit_id),
            )
            .where(
                DetectionPrediction.dataset_id == dataset_id,
                DetectionPrediction.run_id == run_id,
            )
        ):
            label = known.get((unit.host, second(unit.start_time) // seconds))
            if label is None or label[0] != unit.definition["observed_event_count"]:
                skipped += 1
                continue
            truth.append(int(label[1]))
            predictions.append(prediction.predicted)
            ranks.append(
                prediction.score
                if config["score_direction"] == "higher"
                else -prediction.score
            )
        tp = sum(t and p for t, p in zip(truth, predictions))
        fp = sum(not t and p for t, p in zip(truth, predictions))
        fn = sum(t and not p for t, p in zip(truth, predictions))
        tn = sum(not t and not p for t, p in zip(truth, predictions))
        metrics = {
            "unit": "observed host-window",
            "label_policy": "any original BGL alert among ALL observed events in this window",
            "label_source": "loghub-bgl original",
            "scope": "chronological test split only",
            "eligible_units": len(truth),
            "unlabeled_units": skipped,
            "tp": int(tp),
            "fp": int(fp),
            "fn": int(fn),
            "tn": int(tn),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None,
            "auprc_average_precision": float(average_precision_score(truth, ranks))
            if len(set(truth)) == 2
            else None,
            "no_event_level_comparison": True,
            "source_time_completeness": "unknown; imported observations only",
        }
        report = session.scalar(
            select(EvaluationReport).where(
                EvaluationReport.dataset_id == dataset_id,
                EvaluationReport.run_id == run_id,
            )
        )
        if report is None:
            session.add(
                EvaluationReport(dataset_id=dataset_id, run_id=run_id, metrics=metrics)
            )
        else:
            report.metrics = metrics
        return metrics
