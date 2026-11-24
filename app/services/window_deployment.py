"""Persist predictions from a locally frozen, validation-selected IF study.

Study artifacts are trusted operator-created joblib files, never upload input.
Hashes detect accidental changes; they do not authenticate an untrusted pickle.
The study snapshot and test interval are immutable. A new import needs a new study.
"""

from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import re

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Dataset, Detector, DetectorVersion, DetectorRun, LogEvent


STUDY_ROOT = Path(".local/if_studies")


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def inspect_study(study_id, dataset_id):
    """Check bounded identifiers, fixed paths and hashes before loading pickle."""
    if not isinstance(study_id, str) or not re.fullmatch(r"[a-f0-9]{32}", study_id):
        raise ValueError("Invalid study ID.")
    root = STUDY_ROOT.resolve()
    directory = (root / study_id).resolve()
    if directory.parent != root:
        raise ValueError("Study path escapes the trusted root.")
    paths = {}
    for name in ("selection.json", "manifest.json", "selected.joblib", "test.jsonl"):
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise ValueError("Frozen study artifact unavailable.")
        paths[name] = path
    selection = json.loads(paths["selection.json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest.json"].read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != dataset_id:
        raise ValueError("Study belongs to a different dataset.")
    if digest(paths["manifest.json"]) != selection.get("manifest_sha256"):
        raise ValueError("Frozen manifest changed.")
    artifact = selection.get("model_artifact", {})
    cache = manifest.get("cache", {}).get("test", {})
    if (
        artifact.get("key") != "selected.joblib"
        or artifact.get("sha256") != digest(paths["selected.joblib"])
        or cache.get("key") != "test.jsonl"
        or cache.get("sha256") != digest(paths["test.jsonl"])
    ):
        raise ValueError("Frozen artifact checksum mismatch.")
    threshold = selection.get("threshold")
    names = selection.get("feature_names")
    features = selection.get("selected", {}).get("features")
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (float, int))
        or not math.isfinite(threshold)
        or selection.get("comparison") != "<"
        or selection.get("score_direction") != "lower"
        or features not in {"base", "context"}
        or not isinstance(names, list)
        or len(names) != (5 if features == "base" else 9)
        or not all(isinstance(name, str) for name in names)
    ):
        raise ValueError("Invalid frozen scoring contract.")
    seconds = manifest.get("seconds")
    splits = manifest.get("splits", {})
    bounds = [splits.get(key) for key in (
        "train_start", "train_end", "validation_end", "test_end"
    )]
    if (
        not isinstance(seconds, int)
        or isinstance(seconds, bool)
        or seconds not in {60, 300, 900, 3600}
        or not all(isinstance(value, int) and not isinstance(value, bool)
                   and value % seconds == 0 for value in bounds)
        or bounds != sorted(set(bounds))
        or not isinstance(cache.get("count"), int)
        or cache["count"] < 1
    ):
        raise ValueError("Invalid frozen temporal scope.")
    return manifest, selection, paths


def run_study(engine, dataset_id, job_key, configuration):
    """Score only the frozen test scope; never fit or calibrate in a worker."""
    from app.services.investigation import iso
    from app.services.window_detection import EPOCH, persist_predictions, evaluate_windows

    if set(configuration) != {"detector", "study_id"} or configuration.get(
        "detector"
    ) != "isolation_forest":
        raise ValueError("Frozen study configuration cannot override its model or scope.")
    manifest, selection, paths = inspect_study(configuration["study_id"], dataset_id)
    selection_hash = digest(paths["selection.json"])
    revision = manifest["input_revision"]
    maximum = manifest["maximum_event_id"]
    seconds = manifest["seconds"]
    splits = manifest["splits"]
    threshold = selection["threshold"]
    names = selection["feature_names"]
    config = {
        "detector": "isolation_forest",
        "study_id": configuration["study_id"],
        "selection_sha256": selection_hash,
        "manifest_sha256": selection["manifest_sha256"],
        "window_seconds": seconds,
        "input_revision": revision,
        "maximum_event_id": maximum,
        "features": names,
        "feature_version": "observed-host-window-if-v2",
        "score_direction": "lower",
        "threshold": threshold,
        "threshold_policy": "validation labels: constrained F1; frozen before test",
        "comparison": "<",
        "model_artifact": selection["model_artifact"],
        "selected_candidate": selection["selected"],
        "availability": "closed observed window; score is available after window end",
    }
    for key, value in splits.items():
        config[key] = iso(EPOCH + timedelta(seconds=value))
    with Session(engine) as session, session.begin():
        dataset = session.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
        actual_maximum = session.scalar(
            select(func.max(LogEvent.id)).where(LogEvent.dataset_id == dataset_id)
        )
        if (
            dataset is None
            or dataset.state not in {"partial", "imported"}
            or dataset.input_revision != revision
            or actual_maximum != maximum
        ):
            raise ValueError("Frozen study input snapshot changed or is unavailable.")
        existing = session.scalar(select(DetectorRun).where(
            DetectorRun.dataset_id == dataset_id, DetectorRun.run_key == job_key
        ))
        if existing is not None:
            if existing.configuration != config:
                raise ValueError("Run key already refers to a different configuration.")
            if existing.state == "completed":
                return {"run_id": existing.id, "state": "completed", "retry": "idempotent"}
            existing.state = "running"
            run_id = existing.id
        else:
            detector = session.scalar(select(Detector).where(
                Detector.detector_key == "host-window-isolation_forest-v2"
            ))
            if detector is None:
                detector = Detector(
                    detector_key="host-window-isolation_forest-v2", family="classical_ml"
                )
                session.add(detector)
                session.flush()
            version = session.scalar(select(DetectorVersion).where(
                DetectorVersion.detector_id == detector.id,
                DetectorVersion.version == selection_hash,
            ))
            if version is None:
                version = DetectorVersion(
                    detector_id=detector.id,
                    version=selection_hash,
                    configuration=config,
                    feature_schema={
                        "names": names, "version": "2", "label_free": True,
                        "threshold_uses_validation_labels": True,
                    },
                    score_direction="lower",
                )
                session.add(version)
                session.flush()
            run = DetectorRun(
                dataset_id=dataset_id, detector_id=detector.id, version_id=version.id,
                run_key=job_key, state="running", input_revision=revision,
                configuration=config,
            )
            session.add(run)
            session.flush()
            run_id = run.id
    try:
        # This is the sole pickle-loading boundary. Only locally generated files
        # under the trusted study root with the frozen checksum reach it.
        bundle = joblib.load(paths["selected.joblib"])
        if (
            not isinstance(bundle, dict)
            or bundle.get("features") != selection["selected"]["features"]
            or not callable(getattr(bundle.get("model"), "score_samples", None))
            or (bundle["features"] == "context" and bundle.get("reference") is None)
        ):
            raise ValueError("Invalid frozen model bundle.")
        reference = {
            "threshold": threshold,
            "selection_sha256": selection_hash,
            "source": "frozen train-only references; validation-label calibration",
        }
        if bundle.get("reference") is not None:
            reference["training_reference"] = bundle["reference"].summary()
        count = 0
        batch = []
        previous = None
        with paths["test.jsonl"].open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                bucket = record["bucket"]
                host = record["host"]
                order = (bucket, host)
                if (
                    not isinstance(bucket, int)
                    or not isinstance(host, str)
                    or not host
                    or not splits["validation_end"] <= bucket * seconds < splits["test_end"]
                    or (previous is not None and order <= previous)
                    or not isinstance(record["count"], int)
                    or record["count"] < 1
                    or len(record.get("sample_ids", [])) > 20
                    or any(not isinstance(i, int) or not 0 < i <= maximum
                           for i in record.get("sample_ids", []))
                ):
                    raise ValueError("Cached unit is outside frozen test scope.")
                previous = order
                values = (record["features"] if bundle["features"] == "base"
                          else bundle["reference"].transform(record))
                if len(values) != len(names) or not all(math.isfinite(x) for x in values):
                    raise ValueError("Invalid frozen feature vector.")
                row = dict(record, features=values)
                batch.append(row)
                count += 1
                if len(batch) == 200:
                    persist_predictions(
                        engine, dataset_id, revision, maximum, run_id, batch,
                        bundle["model"], threshold, reference, seconds, feature_names=names,
                    )
                    batch = []
        if count != manifest["cache"]["test"]["count"]:
            raise ValueError("Cached test count differs from frozen manifest.")
        if batch:
            persist_predictions(
                engine, dataset_id, revision, maximum, run_id, batch,
                bundle["model"], threshold, reference, seconds, feature_names=names,
            )
        evaluate_windows(engine, dataset_id, run_id)
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "completed"
    except Exception:
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "failed"
        raise
    return {"run_id": run_id, "state": "completed", "evaluated_units": count}
