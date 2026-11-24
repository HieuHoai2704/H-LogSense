"""Deterministic sampling and validation-only detector threshold calibration.

Features and model fitting stay label blind. ``choose_threshold`` is explicitly
supervised calibration on a caller-provided validation set, never a test set.
Native detector scores remain detector specific and are not probabilities.
"""

from numbers import Integral

import numpy as np
from sklearn.metrics import average_precision_score


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(name + " must be an integer.")
    return int(value)


def temporal_split(start_epoch, end_epoch, seconds):
    """Split a UTC [start, end) range 50/25/25 without splitting a time bin."""
    start_epoch = _integer(start_epoch, "start_epoch")
    end_epoch = _integer(end_epoch, "end_epoch")
    seconds = _integer(seconds, "seconds")
    if (
        seconds <= 0
        or end_epoch <= start_epoch
        or start_epoch % seconds
        or end_epoch % seconds
    ):
        raise ValueError("Use a positive UTC-aligned range and bin width.")
    span = end_epoch - start_epoch
    train_end = start_epoch + (span // 2 // seconds) * seconds
    validation_end = start_epoch + (span * 3 // 4 // seconds) * seconds
    if not start_epoch < train_end < validation_end < end_epoch:
        raise ValueError("Range is too short for disjoint temporal splits.")
    return {
        "train_start": start_epoch,
        "train_end": train_end,
        "validation_end": validation_end,
        "test_end": end_epoch,
    }


def reservoir_sample(records, limit=20000, seed=42):
    """Algorithm R: sample the entire input stream using O(limit) memory."""
    limit = _integer(limit, "limit")
    seed = _integer(seed, "seed")
    if limit <= 0 or seed < 0:
        raise ValueError("Use a positive limit and nonnegative seed.")
    random = np.random.default_rng(seed)
    sample = []
    for index, record in enumerate(records):
        if index < limit:
            sample.append(record)
        else:
            replace = int(random.integers(0, index + 1))
            if replace < limit:
                sample[replace] = record
    return sample


def _arrays(truth, scores):
    labels = np.asarray(truth)
    native = np.asarray(scores, dtype=float)
    if labels.ndim != 1 or native.ndim != 1 or len(labels) != len(native):
        raise ValueError("Labels and native scores must be equal-length vectors.")
    if not np.all(np.isin(labels, [0, 1])) or not np.all(np.isfinite(native)):
        raise ValueError("Use binary labels and finite native scores.")
    return labels.astype(bool), native


def _direction(direction):
    if direction not in {"lower", "higher"}:
        raise ValueError("Score direction must be lower or higher.")
    return "<" if direction == "lower" else ">"


def binary_metrics(truth, scores, threshold, direction="lower", comparison=None):
    """Evaluate native scores; AUPRC is average precision, not trapezoidal area.

    Undefined denominators and a one-class/empty AUPRC are represented by None.
    An explicit non-strict comparison is allowed only when it matches the native
    direction; callers must record it with the calibrated threshold.
    """
    strict = _direction(direction)
    comparison = strict if comparison is None else comparison
    if comparison not in ({"<", "<="} if strict == "<" else {">", ">="}):
        raise ValueError("Comparison does not match the native score direction.")
    if not np.isscalar(threshold) or not np.isfinite(threshold):
        raise ValueError("Threshold must be finite.")
    labels, native = _arrays(truth, scores)
    operators = {"<": np.less, "<=": np.less_equal, ">": np.greater, ">=": np.greater_equal}
    predicted = operators[comparison](native, threshold)
    tp = int(np.count_nonzero(labels & predicted))
    fp = int(np.count_nonzero(~labels & predicted))
    fn = int(np.count_nonzero(labels & ~predicted))
    tn = int(np.count_nonzero(~labels & ~predicted))
    return {
        "eligible_units": len(labels),
        "predicted_positive": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "fpr": fp / (fp + tn) if fp + tn else None,
        "auprc_average_precision": float(
            average_precision_score(labels, -native if direction == "lower" else native)
        )
        if len(np.unique(labels)) == 2
        else None,
    }


def choose_threshold(truth, native_scores, max_fpr=0.01, direction="lower"):
    """Calibrate on labeled validation only, with an explicit false-positive cap.

    Sort once, sweep whole native-score tie groups, then maximize validation F1
    subject to FPR <= max_fpr. Ties prefer lower FPR, then fewer alerts. No test
    scores or labels belong in this API. Both validation classes are required.
    """
    comparison = _direction(direction)
    labels, native = _arrays(truth, native_scores)
    if not np.isscalar(max_fpr) or not np.isfinite(max_fpr) or not 0 <= max_fpr <= 1:
        raise ValueError("max_fpr must be finite and between zero and one.")
    positives = int(np.count_nonzero(labels))
    negatives = len(labels) - positives
    if not positives or not negatives:
        raise ValueError("Calibration requires both classes in validation.")
    order = np.argsort(native if direction == "lower" else -native, kind="stable")
    sorted_scores = native[order]
    sorted_labels = labels[order]
    toward = -np.inf if direction == "lower" else np.inf
    threshold = float(np.nextafter(sorted_scores[0], toward))
    if not np.isfinite(threshold):
        threshold = float(sorted_scores[0])
    best = (0.0, 0.0, 0)
    best_threshold = threshold
    tp = fp = 0
    index = 0
    while index < len(labels):
        end = index + 1
        while end < len(labels) and sorted_scores[end] == sorted_scores[index]:
            end += 1
        tp += int(np.count_nonzero(sorted_labels[index:end]))
        fp = end - tp
        fpr = fp / negatives
        candidate = (2 * tp / (positives + end), -fpr, -end)
        # Moving one float toward the normal direction includes this entire tie
        # group using the same strict comparison used during inference.
        toward = np.inf if direction == "lower" else -np.inf
        boundary = float(np.nextafter(sorted_scores[index], toward))
        if fpr <= max_fpr and np.isfinite(boundary) and candidate > best:
            best = candidate
            best_threshold = boundary
        index = end
    return {
        "threshold": best_threshold,
        "comparison": comparison,
        "max_fpr": float(max_fpr),
        "policy": "labeled validation F1 maximum subject to FPR cap; no test tuning",
        "metrics": binary_metrics(labels, native, best_threshold, direction, comparison),
    }
