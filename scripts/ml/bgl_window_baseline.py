"""Evaluate H-logsen BGL detectors with disjoint temporal selection, calibration and test."""

import argparse
from array import array
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import time
from zipfile import ZipFile

import joblib
import numpy as np
import psutil
from scipy.sparse import csr_matrix, hstack
import sklearn
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from app.parsers.bgl import (
    LEGACY_VERSION as PARSER_VERSION,  # documented results use bgl-1.0.0
    parse_line,
)
from app.services.detector_calibration import binary_metrics
from app.services.window_detection import SEVERE

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]

SEED = 42
SECONDS = 300
MAX_FPR = 0.002
ARCHIVE_SHA = "d67fd82a711aea0157a9b83175892c6ee60e384a2ddf5bc51f39118453816da8"
RANGES = {
    "train": ("2005-06-03", "2005-08-01"),
    "selection": ("2005-08-01", "2005-08-18"),
    "calibration": ("2005-08-18", "2005-09-01"),
    "test": ("2005-09-01", "2005-10-01"),
    "later_test": ("2005-10-01", "2006-01-05"),
}
NORMALIZE = re.compile(r"\b(?:0x[0-9a-fA-F]+|\d+)\b")
SUPERVISED = ("count-lr", "count-xgb", "window-lr", "window-xgb")
MODELS = ("count-rule", "isolation-forest", *SUPERVISED)
NEGATIVE_LIMIT = 400_000
IF_LIMIT = 20_000
THREADS = 6
XGB_PARAMS = {
    "tree_method": "hist",
    "n_estimators": 120,
    "max_depth": 5,
    "learning_rate": 0.10,
    "max_bin": 128,
    "min_child_weight": 5,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "reg_lambda": 2,
    "n_jobs": THREADS,
    "random_state": SEED,
    "eval_metric": "logloss",
}


@dataclass
class Window:
    templates: Counter = field(default_factory=Counter)
    size: int = 0
    severe: int = 0
    chars: int = 0
    anomaly: bool = False
    first_line: int = 0

    def add(self, row, template_id):
        self.templates[template_id] += 1
        self.size += 1
        self.severe += row.attributes["level"].upper() in SEVERE
        self.chars += len(row.message)
        self.anomaly |= row.label != "-"
        if not self.first_line:
            self.first_line = row.line_number

    def features(self):
        size = self.size
        return (
            math.log1p(size),
            self.severe / size,
            len(self.templates) / size,
            max(self.templates.values()) / size,
            math.log1p(self.chars / size),
        )


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def epoch(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def raw_stamp(line):
    tokens = line.split(None, 2)
    return int(tokens[1]) if len(tokens) > 1 and tokens[1].isdigit() else None


def collect(archive, date_range):
    start, end = map(epoch, date_range)
    seen, dropped, invalid_epoch, byte_offset, parsed = 0, Counter(), 0, 0, 0
    labels, buckets, sample = array("B"), array("i"), array("i")
    features, indices, counts, offsets = array("f"), array("i"), array("i"), array("i", [0])
    catalog, groups = {}, {}
    source = hashlib.sha256()
    last_stamp, current = -1, None

    def emit(bucket):
        for _, group in sorted(groups.items()):
            features.extend(group.features())
            for key, count in sorted(group.templates.items()):
                indices.append(key)
                counts.append(count)
            offsets.append(len(indices))
            labels.append(group.anomaly)
            buckets.append(bucket)
            sample.append(group.first_line)

    with ZipFile(archive) as zip_file, zip_file.open("BGL.log") as stream:
        for line_number, line in enumerate(stream, 1):
            stamp = raw_stamp(line)
            offset = byte_offset
            byte_offset += len(line)
            if stamp is None:
                invalid_epoch += 1
                continue
            if stamp < last_stamp:
                raise ValueError("BGL source ordering changed.")
            last_stamp = stamp
            if stamp < start:
                continue
            if stamp >= end:
                break
            seen += 1
            source.update(line)
            row = parse_line(line, line_number, offset, PARSER_VERSION)
            if row.error or not row.host:
                dropped[row.error or "missing_host"] += 1
                continue
            bucket = stamp // SECONDS
            if current is not None and bucket != current:
                emit(current)
                groups.clear()
            current = bucket
            normalized = NORMALIZE.sub("<*>", row.message)
            template_id = catalog.setdefault(normalized, len(catalog))
            if row.host not in groups:
                groups[row.host] = Window()
            groups[row.host].add(row, template_id)
            parsed += 1
    if current is not None:
        emit(current)
    y = np.frombuffer(labels, dtype=np.uint8)
    matrix = csr_matrix(
        (
            np.frombuffer(counts, dtype=np.int32),
            np.frombuffer(indices, dtype=np.int32),
            np.frombuffer(offsets, dtype=np.int32),
        ),
        shape=(len(y), len(catalog)),
    )
    if int(matrix.sum(dtype=np.int64)) != parsed or seen != parsed + sum(dropped.values()):
        raise ValueError("Source rows and window counts do not reconcile.")
    meta = {
        "utc": date_range,
        "raw_rows": seen,
        "parsed_rows": parsed,
        "dropped": dict(dropped),
        "invalid_epoch_unassigned_seen_in_prefix": invalid_epoch,
        "source_slice_sha256": source.hexdigest(),
        "windows": len(y),
        "positives": int(y.sum()),
        "negatives": len(y) - int(y.sum()),
        "templates": len(catalog),
    }
    return {
        "catalog": list(catalog),
        "counts": matrix,
        "base": np.frombuffer(features, dtype=np.float32).reshape(-1, 5),
        "y": y,
        "bucket": np.frombuffer(buckets, dtype=np.int32),
        "first_source_line": np.frombuffer(sample, dtype=np.int32),
        "source": meta,
    }


def fit_representation(train):
    catalog = train["catalog"]
    presence = np.bincount(train["counts"].indices, minlength=len(catalog))
    top = sorted(range(len(catalog)), key=lambda i: (-presence[i], catalog[i]))[:256]
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=8192, dtype=np.float32
    )
    vectors = vectorizer.fit_transform(catalog)
    reducer = TruncatedSVD(n_components=24, n_iter=7, random_state=SEED).fit(vectors)
    return {
        "top": {catalog[i]: j for j, i in enumerate(top)},
        "template_df": dict(zip(catalog, presence.tolist(), strict=True)),
        "train_windows": train["counts"].shape[0],
        "vectorizer": vectorizer,
        "reducer": reducer,
    }


def transform(data, representation):
    catalog, counts, base = data["catalog"], data["counts"], data["base"]
    top, df = representation["top"], representation["template_df"]
    embedding = representation["reducer"].transform(representation["vectorizer"].transform(catalog))
    totals = np.asarray(counts.sum(axis=1)).ravel()
    text = np.asarray(counts @ embedding, dtype=np.float32) / totals[:, None].astype(np.float32)
    rarity = np.array(
        [math.log((1 + representation["train_windows"]) / (1 + df.get(key, 0))) for key in catalog],
        dtype=np.float32,
    )
    mean_rarity = (counts @ rarity) / totals
    rows = np.repeat(np.arange(counts.shape[0], dtype=np.int32), np.diff(counts.indptr))
    mapping = np.array([top.get(key, -1) for key in catalog], dtype=np.int32)[counts.indices]
    keep = mapping >= 0
    known = csr_matrix(
        (np.log1p(counts.data[keep]).astype(np.float32), (rows[keep], mapping[keep])),
        shape=(len(base), len(top)),
    )
    core = np.column_stack((base, mean_rarity.astype(np.float32)))
    count = hstack((csr_matrix(core), known), format="csr")
    hybrid = hstack((count, csr_matrix(text)), format="csr")
    return {"base": base, "count": count, "hybrid": hybrid}


def calibrate(y, scores):
    """Maximize recall at a fixed FPR, including or excluding each score tie as a whole."""
    y, scores = np.asarray(y), np.asarray(scores, dtype=np.float64)
    if (
        y.ndim != 1
        or scores.shape != y.shape
        or not np.isin(y, (0, 1)).all()
        or not np.isfinite(scores).all()
    ):
        raise ValueError("Calibration requires binary labels and aligned finite scores.")
    positive = int(y.sum())
    negative = len(y) - positive
    if not positive or not negative:
        raise ValueError("Both classes are required for threshold calibration.")
    order = np.argsort(-scores, kind="stable")
    ranked = scores[order]
    end = np.r_[np.flatnonzero(ranked[:-1] != ranked[1:]), len(ranked) - 1]
    tp = np.cumsum(y[order], dtype=np.int64)[end]
    fp = end + 1 - tp
    allowed = np.flatnonzero(fp <= math.floor(negative * MAX_FPR))
    cutoff = float(ranked[0])
    if allowed.size and tp[allowed[-1]] > 0:
        best = allowed[np.flatnonzero(tp[allowed] == tp[allowed[-1]])[0]]
        cutoff = float(np.nextafter(ranked[end[best]], -np.inf))
    return cutoff, binary_metrics(y, scores, cutoff, "higher")


def fit_models(values, y, xgb_classifier):
    rng = np.random.default_rng(SEED)
    neg = np.flatnonzero(y == 0)
    pos = np.flatnonzero(y == 1)
    if not len(neg) or not len(pos):
        raise ValueError("Both classes required for supervised training.")
    chosen = np.sort(np.r_[pos, rng.choice(neg, size=min(len(neg), NEGATIVE_LIMIT), replace=False)])
    if_sample = rng.choice(len(y), size=min(len(y), IF_LIMIT), replace=False)
    models = {
        "count-rule": None,
        "isolation-forest": IsolationForest(
            n_estimators=100, max_samples=256, random_state=SEED, n_jobs=THREADS
        ).fit(values["base"][if_sample]),
    }
    for name in SUPERVISED:
        started = time.perf_counter()
        x = values["hybrid" if name.startswith("window-") else "count"][chosen]
        labels = y[chosen]
        if name.endswith("-lr"):
            scaler = StandardScaler(with_mean=False)
            x = scaler.fit_transform(x)
            estimator = LogisticRegression(
                C=1.0, solver="liblinear", random_state=SEED, max_iter=300, class_weight="balanced"
            ).fit(x, labels)
            models[name] = (scaler, estimator)
        else:
            weight = math.sqrt((len(labels) - int(labels.sum())) / int(labels.sum()))
            models[name] = xgb_classifier(**XGB_PARAMS, scale_pos_weight=weight).fit(x, labels)
        print(f"fit {name} {time.perf_counter() - started:.1f}s", flush=True)
    return models, {
        "supervised_windows": len(chosen),
        "positive_windows": len(pos),
        "if_sample": len(if_sample),
    }


def score(name, model, values):
    if name == "count-rule":
        result = values["base"][:, 0]
    elif name == "isolation-forest":
        result = -model.score_samples(values["base"])
    else:
        x = values["hybrid" if name.startswith("window-") else "count"]
        if name.endswith("-lr"):
            scaler, lr = model
            result = lr.decision_function(scaler.transform(x))
        else:
            result = model.predict(x, output_margin=True)
    return np.asarray(result, dtype=np.float64)


def memory_mib():
    info = psutil.Process().memory_info()
    return {
        "rss_mib": round(info.rss / 2**20, 2),
        "peak_working_set_mib": round(info.peak_wset / 2**20, 2) if hasattr(info, "peak_wset") else None,
    }


def collect_timed(archive, phase):
    started = time.perf_counter()
    data = collect(archive, RANGES[phase])
    data["source"]["parse_seconds"] = round(time.perf_counter() - started, 3)
    print(f"{phase}: {data['source']}", flush=True)
    return data


def prepare(archive, out, archive_sha):
    import xgboost

    started = time.perf_counter()
    out.mkdir(parents=True)
    protocol = {
        "archive_sha256": archive_sha,
        "code_sha256": sha(Path(__file__)),
        "parser_version": PARSER_VERSION,
        "unit_seconds": SECONDS,
        "ranges_utc_half_open": RANGES,
        "max_fpr": MAX_FPR,
        "seed": SEED,
        "models": MODELS,
        "select_among": SUPERVISED,
        "negative_sample_limit": NEGATIVE_LIMIT,
        "if_sample_limit": IF_LIMIT,
        "xgboost": XGB_PARAMS,
        "selection_order": "recall, AP, lower FPR, ID",
        "threshold": "maximize recall on calibration at empirical FPR cap; ties prefer fewer FP",
        "fit_access": "train only; selection/calibration after fit; both tests after freeze",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "sklearn": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "platform": platform.platform(),
    }
    write_json(out / "protocol.json", protocol)
    train = collect_timed(archive, "train")
    representation = fit_representation(train)
    models, sample = fit_models(transform(train, representation), train["y"], xgboost.XGBClassifier)
    train_meta = train["source"]
    del train

    selection = collect_timed(archive, "selection")
    selection_values = transform(selection, representation)
    candidates = {
        name: calibrate(selection["y"], score(name, models[name], selection_values))[1] for name in MODELS
    }
    champion = max(
        SUPERVISED,
        key=lambda name: (
            candidates[name]["recall"],
            candidates[name]["auprc_average_precision"],
            -candidates[name]["fpr"],
            name,
        ),
    )
    selection_meta = selection["source"]
    del selection, selection_values

    calibration = collect_timed(archive, "calibration")
    calibration_values = transform(calibration, representation)
    thresholds, calibrated = {}, {}
    for name in MODELS:
        thresholds[name], calibrated[name] = calibrate(
            calibration["y"], score(name, models[name], calibration_values)
        )
    frozen = {
        "champion": champion,
        "thresholds": thresholds,
        "models": models,
        "representation": representation,
    }
    path = out / "models.joblib"
    joblib.dump(frozen, path, compress=3)
    write_json(
        out / "freeze.json",
        {
            "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": sha(out / "protocol.json"),
            "artifact_sha256": sha(path),
            "selected": champion,
            "thresholds": thresholds,
            "selection": candidates,
            "calibration": calibrated,
            "train_sampling": sample,
            "train": train_meta,
            "selection_source": selection_meta,
            "calibration_source": calibration["source"],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "memory": memory_mib(),
        },
    )
    print(f"Frozen champion: {champion}", flush=True)


def evaluate(archive, out, archive_sha):
    protocol = read_json(out / "protocol.json")
    freeze = read_json(out / "freeze.json")
    path = out / "models.joblib"
    if (
        protocol["archive_sha256"] != archive_sha
        or protocol["code_sha256"] != sha(Path(__file__))
        or freeze["protocol_sha256"] != sha(out / "protocol.json")
        or freeze["artifact_sha256"] != sha(path)
    ):
        raise ValueError("Frozen inputs changed. Use an unchanged registered experiment.")
    # Only open this locally generated and hash-checked experiment artifact.
    frozen = joblib.load(path)
    write_json(
        out / "test-access.json",
        {"opened_at_utc": datetime.now(timezone.utc).isoformat(), "freeze_sha256": sha(out / "freeze.json")},
    )
    report = {"champion": frozen["champion"], "fpr_budget": MAX_FPR, "partitions": {}}
    for phase in ("test", "later_test"):
        started = time.perf_counter()
        data = collect_timed(archive, phase)
        values = transform(data, frozen["representation"])
        scores = {name: score(name, frozen["models"][name], values) for name in MODELS}
        results = {
            name: binary_metrics(data["y"], native, frozen["thresholds"][name], "higher")
            for name, native in scores.items()
        }
        np.savez_compressed(
            out / (phase + "-scores.npz"),
            y=data["y"],
            bucket=data["bucket"],
            first_source_line=data["first_source_line"],
            **scores,
        )
        report["partitions"][phase] = {
            "source": data["source"],
            "models": results,
            "seconds": round(time.perf_counter() - started, 3),
            "memory": memory_mib(),
        }
        print(phase, json.dumps(results), flush=True)
        del data, values, scores
    write_json(out / "test-results.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=(REPO_ROOT / "data/raw/BGL.zip"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage", choices=("fit", "test"), required=True)
    options = parser.parse_args()
    archive_sha = sha(options.archive)
    if archive_sha != ARCHIVE_SHA:
        raise ValueError("Expected the checksummed original Loghub BGL archive.")
    with threadpool_limits(limits=THREADS):
        operation = prepare if options.stage == "fit" else evaluate
        operation(options.archive, options.out, archive_sha)


if __name__ == "__main__":
    main()
