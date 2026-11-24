"""Inference-only profile from a frozen later BGL validation study.

Only trusted operator-created local joblib artifacts may be loaded. Inference
uses actual dataset event IDs; offline study source-line references are never
persisted as database membership. No fitting or threshold selection occurs here.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from uuid import uuid4

import joblib
from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.models import Dataset, Detector, DetectorRun, DetectorVersion, LogEvent
from app.paths import IF_HOLDOUT_DIR, VALIDATED_IF_INPUTS_DIR
from app.services.bgl_ingestion import fingerprint, import_lease
from app.services.window_detection import (
    EPOCH,
    FEATURE_NAMES,
    aggregate_windows,
    evaluate_windows,
    persist_predictions,
    second,
)
from app.services.window_features import FEATURE_NAMES as CONTEXT_FEATURE_NAMES

DEFAULT_MODEL_ID = "f3e5a88403ab48fb84ea36904214e867"
STUDY_ROOT = IF_HOLDOUT_DIR
INPUT_ROOT = VALIDATED_IF_INPUTS_DIR


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _inspect(model_id):
    if not isinstance(model_id, str) or not re.fullmatch(r"[a-f0-9]{32}", model_id):
        raise ValueError("Invalid validated model identifier.")
    root = STUDY_ROOT.resolve()
    directory = (root / model_id).resolve()
    if directory.parent != root:
        raise ValueError("Model path escapes trusted study storage.")
    files = {}
    for name in ("protocol.json", "manifest.json", "validation.json", "selection.json", "selected.joblib"):
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise ValueError("Validated model artifact unavailable.")
        files[name] = path
    protocol, manifest, validation, selection = (
        _json(files[name]) for name in ("protocol.json", "manifest.json", "validation.json", "selection.json")
    )
    if (
        fingerprint(files["protocol.json"]) != manifest.get("protocol_sha256")
        or any(manifest.get(k) != value for k, value in protocol.items())
        or fingerprint(files["manifest.json"]) != selection.get("manifest_sha256")
        or fingerprint(files["validation.json"]) != selection.get("validation_sha256")
        or fingerprint(files["selected.joblib"]) != selection.get("selected_artifact_sha256")
    ):
        raise ValueError("Frozen model integrity check failed.")
    chosen = next(
        (c for c in validation.get("candidates", []) if c["spec"]["id"] == validation.get("selected")), None
    )
    spec = selection.get("selected", {})
    threshold = selection.get("threshold")
    import math

    if (
        chosen is None
        or chosen["spec"] != spec
        or chosen["calibration"]["threshold"] != threshold
        or isinstance(threshold, bool)
        or not isinstance(threshold, (float, int))
        or not math.isfinite(threshold)
        or selection.get("comparison") != "<"
        or selection.get("score_direction") != "lower"
        or selection.get("threshold_uses_validation_labels") is not True
        or spec.get("features") not in {"base", "context"}
        or manifest.get("seconds") != 300
    ):
        raise ValueError("Invalid frozen inference contract.")
    bounds = manifest.get("splits", {})
    ordered = [bounds.get(k) for k in ("train_start", "train_end", "validation_end", "test_end")]
    if not all(
        isinstance(v, int) and not isinstance(v, bool) and v % 300 == 0 for v in ordered
    ) or ordered != sorted(set(ordered)):
        raise ValueError("Invalid frozen chronological boundaries.")
    names = FEATURE_NAMES if spec["features"] == "base" else CONTEXT_FEATURE_NAMES
    return directory, manifest, validation, selection, list(names)


def model_card(model_id=DEFAULT_MODEL_ID):
    try:
        return _model_card(model_id)
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        # A malformed frozen bundle is "unavailable" (callers handle ValueError), never a 500.
        raise ValueError("Validated model bundle is malformed.") from error


def _model_card(model_id):
    directory, manifest, validation, selection, names = _inspect(model_id)
    version = fingerprint(directory / "selection.json")
    result = {
        "id": model_id,
        "version": version,
        "detector": "isolation_forest",
        "name": "Validation-calibrated BGL IF",
        "feature_names": names,
        "model_specification": selection["selected"],
        "window_seconds": 300,
        "score_direction": "lower",
        "comparison": "<",
        "threshold": selection["threshold"],
        "score_is_probability": False,
        "training": {
            "start": datetime.fromtimestamp(manifest["splits"]["train_start"], timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(manifest["splits"]["train_end"], timezone.utc).isoformat(),
            "fit_uses_labels": False,
        },
        "calibration": {
            "uses_validation_labels": True,
            "policy": "validation F1 maximum subject to empirical FPR cap",
            "max_fpr": manifest.get("max_fpr"),
            "units": validation.get("eligible_units"),
            "start": datetime.fromtimestamp(manifest["splits"]["train_end"], timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(manifest["splits"]["validation_end"], timezone.utc).isoformat(),
        },
        "inference_start_utc": datetime.fromtimestamp(
            manifest["splits"]["validation_end"], timezone.utc
        ).isoformat(),
        "eligible_scope": "closed observed host-windows at/after frozen validation end; never earlier training/calibration windows",
        "coverage": "unknown source completeness; observed parsed host-window target",
        "source_qualification": {
            "parser_rejected_selected_rows": manifest.get("malformed_selected_events"),
            "missing_host_events": manifest.get("missing_host_events"),
            "target": "observed parsed host-windows; no complete-raw-window ground-truth claim",
        },
        "software": manifest.get("software"),
        "report": "docs/ml/IF_JULY_HOLDOUT.md",
    }
    test_path = (directory / "test-results.json").resolve()
    if test_path.parent == directory and test_path.is_file():
        measured = _json(test_path)
        if measured.get("selection_sha256") != version:
            raise ValueError("Independent model report refers to another frozen selection.")
        result["independent_test"] = {
            "unit": "observed parsed host-window",
            "start": datetime.fromtimestamp(manifest["splits"]["validation_end"], timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(manifest["splits"]["test_end"], timezone.utc).isoformat(),
            "metrics": measured.get("metrics", {}).get("selected_if"),
            "note": "Measured on the July BGL holdout, not a promise for another dataset; root cause unconfirmed.",
        }
    return result


def load_frozen_model(model_id):
    directory, manifest, validation, selection, names = _inspect(model_id)
    # Checksums detect changes to trusted artifacts, not malicious pickle files.
    bundle = joblib.load(directory / "selected.joblib")
    if (
        not isinstance(bundle, dict)
        or bundle.get("features") != selection["selected"]["features"]
        or not callable(getattr(bundle.get("model"), "score_samples", None))
        or getattr(bundle["model"], "n_features_in_", None) != len(names)
        or getattr(bundle["model"], "n_estimators", None) != selection["selected"]["n_estimators"]
        or getattr(bundle["model"], "random_state", None) != selection["selected"]["seed"]
        or (
            bundle["features"] == "context"
            and (bundle.get("reference") is None or bundle["reference"].names != names)
        )
    ):
        raise ValueError("Frozen artifact feature schema mismatch.")
    return bundle, model_card(model_id)


def _unit_count(session, predicates):
    micros = func.timestampdiff(text("MICROSECOND"), EPOCH.replace(tzinfo=None), LogEvent.timestamp)
    divisor = 300000000
    bucket = micros.op("DIV", precedence=100)(divisor) - case(
        ((micros < 0) & (func.mod(micros, divisor) != 0), 1), else_=0
    )
    groups = (
        select(LogEvent.host, bucket)
        .where(*predicates, LogEvent.host.is_not(None))
        .group_by(LogEvent.host, bucket)
        .subquery()
    )
    return session.scalar(select(func.count()).select_from(groups))


def run_validated(engine, dataset_id, job_key, configuration):
    if set(configuration) != {"detector", "model_id"} or configuration.get("detector") != "isolation_forest":
        raise ValueError("Validated inference accepts only detector and frozen model_id.")
    lease = "validated-if-" + str(dataset_id) + "-" + hashlib.sha256(job_key.encode()).hexdigest()[:24]
    with import_lease(engine, lease):
        return _run(engine, dataset_id, job_key, configuration["model_id"])


def _run(engine, dataset_id, job_key, model_id):
    bundle, card = load_frozen_model(model_id)
    cutoff = datetime.fromisoformat(card["inference_start_utc"])
    version = card["version"]
    names = card["feature_names"]
    with Session(engine) as session:
        dataset = session.get(Dataset, dataset_id)
        if dataset is None or dataset.state not in {"partial", "imported"}:
            raise ValueError("Dataset is unavailable for validated inference.")
        revision = dataset.input_revision
        maximum, last = session.execute(
            select(func.max(LogEvent.id), func.max(LogEvent.timestamp)).where(
                LogEvent.dataset_id == dataset_id
            )
        ).one()
        if last is None or last < cutoff:
            raise ValueError(
                "No events after model calibration cutoff; earlier data would cause temporal leakage."
            )
        existing = session.scalar(
            select(DetectorRun).where(DetectorRun.dataset_id == dataset_id, DetectorRun.run_key == job_key)
        )
        if existing is not None:
            if (
                existing.input_revision != revision
                or existing.configuration.get("maximum_event_id") != maximum
                or existing.configuration.get("model_version") != version
            ):
                raise ValueError("Retry input/model changed; create a new job.")
            if existing.state == "completed":
                return {"run_id": existing.id, "state": "completed", "retry": "idempotent"}
            config = existing.configuration
            run_id = existing.id
        else:
            config = None
    if config is None:
        now_closed = (second(datetime.now(timezone.utc)) // 300) * 300
        end_epoch = min(now_closed, (second(last) // 300 + 1) * 300)
        end = EPOCH + timedelta(seconds=end_epoch)
        if end <= cutoff:
            raise ValueError("No eligible closed windows after model calibration cutoff.")
        INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        cache = INPUT_ROOT / (uuid4().hex + ".jsonl")
        observed_units = 0
        with Session(engine) as session, cache.open("x", encoding="utf-8", newline="\n") as stream:
            snapshot = [LogEvent.dataset_id == dataset_id, LogEvent.id <= maximum]
            counts = {
                "excluded_pre_cutoff_events": session.scalar(
                    select(func.count()).select_from(LogEvent).where(*snapshot, LogEvent.timestamp < cutoff)
                ),
                "excluded_pre_cutoff_units": _unit_count(session, snapshot + [LogEvent.timestamp < cutoff]),
                "excluded_open_or_future_events": session.scalar(
                    select(func.count()).select_from(LogEvent).where(*snapshot, LogEvent.timestamp >= end)
                ),
                "unknown_host_events_in_eligible_time": session.scalar(
                    select(func.count())
                    .select_from(LogEvent)
                    .where(
                        *snapshot,
                        LogEvent.timestamp >= cutoff,
                        LogEvent.timestamp < end,
                        LogEvent.host.is_(None),
                    )
                ),
            }
            rows = session.execute(
                select(LogEvent.id, LogEvent.timestamp, LogEvent.host, LogEvent.severity, LogEvent.message)
                .where(*snapshot, LogEvent.timestamp >= cutoff, LogEvent.timestamp < end)
                .order_by(LogEvent.timestamp, LogEvent.id)
                .execution_options(yield_per=500)
            )
            for unit in aggregate_windows(rows, 300, include_templates=bundle["features"] == "context"):
                stream.write(json.dumps(unit, separators=(",", ":")) + "\n")
                observed_units += 1
        if not observed_units:
            raise ValueError("No eligible observed host-windows; no fabricated host or evidence.")
        config = {
            "detector": "isolation_forest",
            "model_id": model_id,
            "model_version": version,
            "model_artifact": {
                "key": "selected.joblib",
                "sha256": _json(STUDY_ROOT / model_id / "selection.json")["selected_artifact_sha256"],
            },
            "window_seconds": 300,
            "features": names,
            "feature_version": "validated-host-window-if-1",
            "threshold": card["threshold"],
            "score_direction": "lower",
            "comparison": "<",
            "threshold_policy": "frozen labeled-validation calibration; no fitting on this inference dataset",
            "threshold_uses_validation_labels": True,
            "input_revision": revision,
            "maximum_event_id": maximum,
            "inference_start": cutoff.isoformat(),
            "inference_end": end.isoformat(),
            "eligible_units": observed_units,
            "scope_counts": counts,
            "feature_cache_key": cache.name,
            "feature_cache_sha256": fingerprint(cache),
            "availability": "closed observed window; prediction available after window end; source completeness unknown",
        }
        with Session(engine) as session, session.begin():
            ds = session.scalar(select(Dataset).where(Dataset.id == dataset_id).with_for_update())
            if ds.input_revision != revision or ds.state not in {"partial", "imported"}:
                raise ValueError("Dataset changed during feature extraction.")
            statement = insert(Detector).values(
                detector_key="host-window-if-validated", family="classical_ml"
            )
            session.execute(statement.on_duplicate_key_update(id=Detector.id))
            detector = session.scalar(
                select(Detector).where(Detector.detector_key == "host-window-if-validated").with_for_update()
            )
            frozen_version = session.scalar(
                select(DetectorVersion).where(
                    DetectorVersion.detector_id == detector.id, DetectorVersion.version == version
                )
            )
            if frozen_version is None:
                frozen_version = DetectorVersion(
                    detector_id=detector.id,
                    version=version,
                    configuration=card,
                    feature_schema={
                        "names": names,
                        "version": "validated-1",
                        "label_free": True,
                        "threshold_uses_validation_labels": True,
                    },
                    score_direction="lower",
                )
                session.add(frozen_version)
                session.flush()
            run = DetectorRun(
                dataset_id=dataset_id,
                detector_id=detector.id,
                version_id=frozen_version.id,
                run_key=job_key,
                state="running",
                input_revision=revision,
                configuration=config,
            )
            session.add(run)
            session.flush()
            run_id = run.id
    cache = (INPUT_ROOT.resolve() / config["feature_cache_key"]).resolve()
    try:
        if (
            cache.parent != INPUT_ROOT.resolve()
            or not cache.is_file()
            or fingerprint(cache) != config["feature_cache_sha256"]
        ):
            raise ValueError("Inference input cache integrity check failed.")
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "running"
        reference = {
            "threshold": card["threshold"],
            "model_version": version,
            "calibration": card["calibration"],
            "training": card["training"],
            "inference_cutoff": card["inference_start_utc"],
        }
        if bundle.get("reference") is not None:
            reference["training_reference"] = bundle["reference"].summary()
        batch = []
        with cache.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if (
                    not cutoff
                    <= EPOCH + timedelta(seconds=row["bucket"] * 300)
                    < datetime.fromisoformat(config["inference_end"])
                ):
                    raise ValueError("Cached unit outside frozen eligible range.")
                if bundle["features"] == "context":
                    row["features"] = bundle["reference"].transform(row)
                batch.append(row)
                if len(batch) == 200:
                    persist_predictions(
                        engine,
                        dataset_id,
                        revision,
                        maximum,
                        run_id,
                        batch,
                        bundle["model"],
                        card["threshold"],
                        reference,
                        300,
                        feature_names=names,
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
                    bundle["model"],
                    card["threshold"],
                    reference,
                    300,
                    feature_names=names,
                )
        evaluate_windows(engine, dataset_id, run_id)
        with Session(engine) as session, session.begin():
            run = session.get(DetectorRun, run_id)
            if run.evaluated_units != config["eligible_units"]:
                raise ValueError("Persisted inference count differs from frozen input.")
            run.state = "completed"
    except Exception:
        with Session(engine) as session, session.begin():
            session.get(DetectorRun, run_id).state = "failed"
        raise
    return {
        "run_id": run_id,
        "state": "completed",
        "eligible_units": config["eligible_units"],
        "scope_counts": config["scope_counts"],
    }
