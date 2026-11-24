"""Preregister, validate, then independently test BGL observed-window detectors.

DATABASE_URL is read from the environment. No credentials or raw logs enter
curated reports. Each stage is explicit; test refuses an unfrozen selection.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time
from uuid import uuid4

import joblib
import numpy as np
import psutil
import sklearn
from sklearn.ensemble import IsolationForest
from sqlalchemy import case, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models import Dataset, GroundTruthLabel, LogEvent
from app.paths import IF_STUDIES_DIR
from app.services.detector_calibration import (
    binary_metrics,
    choose_threshold,
    reservoir_sample,
    temporal_split,
)
from app.services.window_detection import EPOCH, FEATURE_NAMES, aggregate_windows, second
from app.services.window_features import TrainReference

ROOT = IF_STUDIES_DIR
CANDIDATES = [
    {"id": "base-100-256", "features": "base", "n_estimators": 100, "max_samples": 256, "seed": 42},
    {"id": "context-100-256", "features": "context", "n_estimators": 100, "max_samples": 256, "seed": 42},
    {"id": "base-200-1024", "features": "base", "n_estimators": 200, "max_samples": 1024, "seed": 42},
    {"id": "context-200-1024", "features": "context", "n_estimators": 200, "max_samples": 1024, "seed": 42},
]


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, data):
    # Exclusive creation prevents accidentally replacing a preregistration/result.
    with Path(path).open("x", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def records(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def stamp(epoch):
    return EPOCH + timedelta(seconds=int(epoch))


def verify_snapshot(engine, manifest):
    with Session(engine) as session:
        ds = session.get(Dataset, manifest["dataset_id"])
        maximum = session.scalar(
            select(func.max(LogEvent.id)).where(LogEvent.dataset_id == manifest["dataset_id"])
        )
        if (
            ds is None
            or ds.input_revision != manifest["input_revision"]
            or maximum != manifest["maximum_event_id"]
        ):
            raise ValueError("Dataset snapshot changed; create a new study.")


def prepare(engine, dataset_id, study_id):
    root = ROOT / study_id
    root.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    with Session(engine) as session:
        ds = session.get(Dataset, dataset_id)
        if ds is None or ds.state not in {"partial", "imported"}:
            raise ValueError("Dataset unavailable.")
        first, last, maximum, event_count = session.execute(
            select(
                func.min(LogEvent.timestamp),
                func.max(LogEvent.timestamp),
                func.max(LogEvent.id),
                func.count(),
            ).where(LogEvent.dataset_id == dataset_id)
        ).one()
        if first is None:
            raise ValueError("No events.")
        seconds = 300
        splits = temporal_split(
            second(first) // seconds * seconds, (second(last) // seconds + 1) * seconds, seconds
        )
        protocol = {
            "study_id": study_id,
            "dataset_id": dataset_id,
            "input_revision": ds.input_revision,
            "maximum_event_id": maximum,
            "parsed_event_count": event_count,
            "seconds": seconds,
            "splits": splits,
            "split_iso_utc": {k: stamp(v).isoformat() for k, v in splits.items()},
            "registered_at_utc": datetime.now(timezone.utc).isoformat(),
            "unit": "completed observed UTC host-window; any original BGL alert among ALL observed events",
            "coverage": "unknown; observed imported prefix only; no invented zero-event windows",
            "candidate_grid": CANDIDATES,
            "reservoir_limit": 20000,
            "reservoir_seed": 42,
            "validation_objective": "maximum F1 subject to empirical FPR <= 0.01; then AP, lower FPR, candidate ID",
            "threshold_policy": "strict native score < threshold; validation labels used ONLY for calibration/selection",
            "minimum_validation_each_class": 20,
            "max_fpr": 0.01,
            "threshold_sensitivity_quantiles": [0.001, 0.005, 0.01, 0.02, 0.05],
            "seed_sensitivity": [17, 73],
            "baseline": "legacy first-20000 IF(100 trees/256 samples/seed42), first-20000 validation p01; rule train p99 count",
            "test_policy": "same untouched later chronological holdout for all primary methods; no tuning or reselection after test",
            "software": {
                "python": platform.python_version(),
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
        }
    # This is written before feature extraction or ANY label query.
    write_json(root / "protocol.json", protocol)
    streams = {
        phase: (root / (phase + ".jsonl")).open("x", encoding="utf-8", newline="\n")
        for phase in ("train", "validation", "test")
    }
    counts = dict.fromkeys(streams, 0)
    event_counts = dict.fromkeys(streams, 0)
    singleton = dict.fromkeys(streams, 0)
    try:
        with Session(engine) as session:
            query = (
                select(LogEvent.id, LogEvent.timestamp, LogEvent.host, LogEvent.severity, LogEvent.message)
                .where(
                    LogEvent.dataset_id == dataset_id,
                    LogEvent.id <= maximum,
                    LogEvent.timestamp >= stamp(splits["train_start"]),
                    LogEvent.timestamp < stamp(splits["test_end"]),
                )
                .order_by(LogEvent.timestamp, LogEvent.id)
                .execution_options(yield_per=2000)
            )
            for unit in aggregate_windows(session.execute(query), seconds, include_templates=True):
                epoch = unit["bucket"] * seconds
                phase = (
                    "train"
                    if epoch < splits["train_end"]
                    else "validation"
                    if epoch < splits["validation_end"]
                    else "test"
                )
                streams[phase].write(json.dumps(unit, separators=(",", ":")) + "\n")
                counts[phase] += 1
                event_counts[phase] += unit["count"]
                singleton[phase] += unit["count"] == 1
    finally:
        for stream in streams.values():
            stream.close()
    verify_snapshot(engine, protocol)
    manifest = dict(
        protocol,
        protocol_sha256=digest(root / "protocol.json"),
        cache={
            p: {"key": p + ".jsonl", "sha256": digest(root / (p + ".jsonl")), "count": counts[p]}
            for p in counts
        },
        phase_event_counts=event_counts,
        singleton_units=singleton,
        prepare_seconds=time.perf_counter() - started,
    )
    write_json(root / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "study_id": study_id,
                "splits": protocol["split_iso_utc"],
                "units": counts,
                "events": event_counts,
                "prepare_seconds": manifest["prepare_seconds"],
            }
        ),
        flush=True,
    )


def checked_manifest(engine, root):
    manifest = read_json(root / "manifest.json")
    if digest(root / "protocol.json") != manifest["protocol_sha256"]:
        raise ValueError("Protocol checksum mismatch.")
    protocol = read_json(root / "protocol.json")
    if any(manifest.get(key) != value for key, value in protocol.items()):
        raise ValueError("Manifest differs from preregistered protocol.")
    verify_snapshot(engine, manifest)
    return manifest


def checked_cache(root, manifest, phase):
    cache = manifest["cache"][phase]
    path = root / (phase + ".jsonl")
    if cache["key"] != path.name or digest(path) != cache["sha256"]:
        raise ValueError("Feature snapshot checksum mismatch.")
    return path


def labels(engine, manifest, phase, path):
    # Phase-specific SQL: validation stage never requests test labels.
    lo, hi = {
        "train": ("train_start", "train_end"),
        "validation": ("train_end", "validation_end"),
        "test": ("validation_end", "test_end"),
    }[phase]
    micros = func.timestampdiff(text("MICROSECOND"), EPOCH.replace(tzinfo=None), LogEvent.timestamp)
    divisor = manifest["seconds"] * 1000000
    bucket = micros.op("DIV", precedence=100)(divisor) - case(
        ((micros < 0) & (func.mod(micros, divisor) != 0), 1), else_=0
    )
    with Session(engine) as session:
        rows = session.execute(
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
                LogEvent.dataset_id == manifest["dataset_id"],
                LogEvent.id <= manifest["maximum_event_id"],
                LogEvent.timestamp >= stamp(manifest["splits"][lo]),
                LogEvent.timestamp < stamp(manifest["splits"][hi]),
                GroundTruthLabel.source == "loghub-bgl",
                GroundTruthLabel.version == "original",
            )
            .group_by(LogEvent.host, bucket)
        )
        known = {(r[0], int(r[1])): (int(r[2]), int(r[3])) for r in rows}
    truth = []
    for unit in records(path):
        value = known.get((unit["host"], unit["bucket"]))
        if value is None or value[0] != unit["count"]:
            raise ValueError("Incomplete ground truth: no silent exclusion from primary cohort.")
        truth.append(value[1])
    return np.asarray(truth, dtype=np.int8)


def matrix(path_or_records, reference=None):
    rows = records(path_or_records) if isinstance(path_or_records, Path) else path_or_records
    return np.asarray(
        [r["features"] if reference is None else reference.transform(r) for r in rows], dtype=np.float64
    )


def fit_model(spec, x):
    return IsolationForest(
        n_estimators=spec["n_estimators"],
        max_samples=min(spec["max_samples"], len(x)),
        contamination="auto",
        random_state=spec["seed"],
        n_jobs=1,
    ).fit(x)


def validate(engine, study_id):
    root = ROOT / study_id
    if (root / "selection.json").exists():
        raise ValueError("Selection already frozen; create a new preregistered study.")
    started = time.perf_counter()
    manifest = checked_manifest(engine, root)
    train = checked_cache(root, manifest, "train")
    val = checked_cache(root, manifest, "validation")
    truth = labels(engine, manifest, "validation", val)
    if min(np.count_nonzero(truth), np.count_nonzero(truth == 0)) < manifest["minimum_validation_each_class"]:
        raise ValueError("Insufficient validation classes; no test-based fallback.")
    reference = TrainReference.fit(records(train))
    sampled = reservoir_sample(
        records(train), limit=manifest["reservoir_limit"], seed=manifest["reservoir_seed"]
    )
    if len(sampled) < 16:
        raise ValueError("Insufficient training units.")
    legacy_train = []
    for unit in records(train):
        legacy_train.append(unit)
        if len(legacy_train) == 20000:
            break
    legacy = fit_model(CANDIDATES[0], matrix(legacy_train))
    val_base = matrix(val)
    legacy_threshold = float(np.quantile(legacy.score_samples(val_base[:20000]), 0.01))
    rule_threshold = float(np.quantile(np.expm1(matrix(legacy_train)[:, 0]), 0.99))
    joblib.dump(
        {"model": legacy, "if_threshold": legacy_threshold, "rule_threshold": rule_threshold},
        root / "baselines.joblib",
    )
    candidates, fitted, threshold_sensitivity = [], {}, []
    for spec in manifest["candidate_grid"]:
        ref = reference if spec["features"] == "context" else None
        x, v = matrix(sampled, ref), val_base if ref is None else matrix(val, ref)
        begin = time.perf_counter()
        model = fit_model(spec, x)
        scores = model.score_samples(v)
        calibration = choose_threshold(truth, scores, max_fpr=manifest["max_fpr"], direction="lower")
        candidate = dict(
            spec=spec,
            calibration=calibration,
            validation_seconds=time.perf_counter() - begin,
            distinct_training_vectors=len(np.unique(x, axis=0)),
        )
        candidates.append(candidate)
        fitted[spec["id"]] = (model, ref)
        for quantile in manifest["threshold_sensitivity_quantiles"]:
            threshold = float(np.quantile(scores, quantile))
            threshold_sensitivity.append(
                {
                    "candidate": spec["id"],
                    "policy": "label-blind validation quantile",
                    "quantile": quantile,
                    "threshold": threshold,
                    "metrics": binary_metrics(truth, scores, threshold, direction="lower"),
                }
            )
        threshold_sensitivity.append(
            {
                "candidate": spec["id"],
                "policy": "sklearn auto offset",
                "threshold": float(model.offset_),
                "metrics": binary_metrics(truth, scores, float(model.offset_), direction="lower"),
            }
        )
        print(json.dumps({"validation_candidate": spec["id"], "calibration": calibration}), flush=True)
    # Candidate selection uses validation ONLY, deterministic registered tie-break.
    chosen = sorted(
        candidates,
        key=lambda c: (
            -float(c["calibration"]["metrics"]["f1"] or 0),
            -float(c["calibration"]["metrics"]["auprc_average_precision"] or 0),
            float(c["calibration"]["metrics"]["fpr"]),
            c["spec"]["id"],
        ),
    )[0]
    model, selected_reference = fitted[chosen["spec"]["id"]]
    seed_results = []
    for seed in manifest["seed_sensitivity"]:
        spec = dict(chosen["spec"], seed=seed)
        scores = fit_model(spec, matrix(sampled, selected_reference)).score_samples(
            matrix(val, selected_reference)
        )
        seed_results.append(
            {"seed": seed, "calibration": choose_threshold(truth, scores, max_fpr=manifest["max_fpr"])}
        )
    artifact = root / "selected.joblib"
    joblib.dump(
        {"model": model, "reference": selected_reference, "features": chosen["spec"]["features"]}, artifact
    )
    report = {
        "scope": "validation only; no test labels or test scores accessed",
        "eligible_units": len(truth),
        "positives": int(truth.sum()),
        "negatives": int((truth == 0).sum()),
        "reference": reference.summary(),
        "training_used": len(sampled),
        "candidates": candidates,
        "threshold_sensitivity": threshold_sensitivity,
        "seed_sensitivity": seed_results,
        "legacy_if": binary_metrics(truth, legacy.score_samples(val_base), legacy_threshold),
        "legacy_rule": binary_metrics(truth, np.expm1(val_base[:, 0]), rule_threshold, direction="higher"),
        "selected": chosen["spec"]["id"],
        "validation_seconds": time.perf_counter() - started,
    }
    write_json(root / "validation.json", report)
    selection = {
        "selected": chosen["spec"],
        "threshold": chosen["calibration"]["threshold"],
        "comparison": "<",
        "score_direction": "lower",
        "feature_names": FEATURE_NAMES if selected_reference is None else selected_reference.names,
        "manifest_sha256": digest(root / "manifest.json"),
        "validation_sha256": digest(root / "validation.json"),
        "model_artifact": {"key": artifact.name, "sha256": digest(artifact)},
        "baseline_artifact_sha256": digest(root / "baselines.joblib"),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "threshold_policy": chosen["calibration"]["policy"],
        "threshold_uses_validation_labels": True,
    }
    verify_snapshot(engine, manifest)
    write_json(root / "selection.json", selection)
    print(
        json.dumps(
            {
                "frozen_selection": selection,
                "validation_summary": {
                    k: report[k] for k in ("eligible_units", "positives", "negatives", "validation_seconds")
                },
            }
        ),
        flush=True,
    )


def test(engine, study_id):
    root = ROOT / study_id
    # Exclusive marker makes repeat evaluation an explicit protocol violation.
    if (root / "test-access.json").exists():
        raise ValueError("Test already accessed. Never revise selection using this holdout.")
    manifest = checked_manifest(engine, root)
    selection = read_json(root / "selection.json")
    if (
        digest(root / "manifest.json") != selection["manifest_sha256"]
        or digest(root / "validation.json") != selection["validation_sha256"]
    ):
        raise ValueError("Frozen configuration changed.")
    if (
        digest(root / "selected.joblib") != selection["model_artifact"]["sha256"]
        or digest(root / "baselines.joblib") != selection["baseline_artifact_sha256"]
    ):
        raise ValueError("Trusted local artifact checksum mismatch.")
    validation = read_json(root / "validation.json")
    chosen = next(c for c in validation["candidates"] if c["spec"]["id"] == validation["selected"])
    if (
        selection["selected"] != chosen["spec"]
        or selection["threshold"] != chosen["calibration"]["threshold"]
        or selection.get("comparison") != "<"
    ):
        raise ValueError("Selection differs from frozen validation result.")
    path = checked_cache(root, manifest, "test")
    write_json(
        root / "test-access.json",
        {
            "selection_sha256": digest(root / "selection.json"),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    started = time.perf_counter()
    bundle = joblib.load(root / "selected.joblib")
    baseline = joblib.load(root / "baselines.joblib")
    truth = labels(engine, manifest, "test", path)
    base = matrix(path)
    before_scores = baseline["model"].score_samples(base)
    rule_scores = np.expm1(base[:, 0])
    selected_matrix = base if bundle["reference"] is None else matrix(path, bundle["reference"])
    after_scores = bundle["model"].score_samples(selected_matrix)
    results = {
        "legacy_rule": binary_metrics(truth, rule_scores, baseline["rule_threshold"], direction="higher"),
        "legacy_if": binary_metrics(truth, before_scores, baseline["if_threshold"]),
        "selected_if": binary_metrics(truth, after_scores, selection["threshold"]),
    }
    # Predictions are private but checksummed, allowing reproducibility without raw log export.
    prediction_file = root / "test-predictions.npz"
    np.savez_compressed(
        prediction_file,
        truth=truth,
        rule_scores=rule_scores,
        legacy_if_scores=before_scores,
        selected_if_scores=after_scores,
    )
    report = {
        "study_id": study_id,
        "dataset_id": manifest["dataset_id"],
        "input_revision": manifest["input_revision"],
        "maximum_event_id": manifest["maximum_event_id"],
        "parsed_event_count": manifest["parsed_event_count"],
        "selection_sha256": digest(root / "selection.json"),
        "manifest_sha256": digest(root / "manifest.json"),
        "prediction_sha256": digest(prediction_file),
        "splits": manifest["split_iso_utc"],
        "phase_units": {p: info["count"] for p, info in manifest["cache"].items()},
        "phase_events": manifest["phase_event_counts"],
        "singleton_units": manifest["singleton_units"],
        "test_positives": int(truth.sum()),
        "test_negatives": int((truth == 0).sum()),
        "test_prevalence": float(truth.mean()),
        "selected": selection,
        "baseline_thresholds": {"if": baseline["if_threshold"], "rule": baseline["rule_threshold"]},
        "metrics": results,
        "test_seconds": time.perf_counter() - started,
        "peak_working_set_mib": psutil.Process().memory_info().peak_wset / 1048576
        if os.name == "nt"
        else None,
        "software": manifest["software"],
        "semantics": {
            "unit": manifest["unit"],
            "coverage": manifest["coverage"],
            "auprc": "sklearn average precision, not trapezoid PR area",
            "score": "native lower score more anomalous; not probability; no point adjustment",
            "generalization": "one BGL prefix, one temporal split; no cross-dataset claim",
        },
        "status": "MEASURED; no selection changes permitted after this evaluation",
    }
    verify_snapshot(engine, manifest)
    write_json(root / "test-results.json", report)
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=["prepare", "validate", "test"])
    parser.add_argument("--dataset-id", type=int)
    parser.add_argument("--study-id")
    args = parser.parse_args()
    study_id = args.study_id or uuid4().hex
    if len(study_id) != 32 or any(c not in "0123456789abcdef" for c in study_id):
        parser.error("study-id must be 32 lowercase hex characters.")
    engine = create_engine(os.environ["DATABASE_URL"], hide_parameters=True)
    if engine.dialect.name != "mysql":
        parser.error("Real MySQL required.")
    try:
        if args.stage == "prepare":
            if not args.dataset_id:
                parser.error("--dataset-id is required for prepare.")
            prepare(engine, args.dataset_id, study_id)
        elif args.stage == "validate":
            validate(engine, study_id)
        else:
            test(engine, study_id)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
