"""Frozen, label-blind context for observed BGL host-window features.

Call ``fit`` on training windows only. Validation/test windows are transformed
against that frozen reference; transforming never updates counts or moments.
Template keys must be the deterministic hashes supplied by the window builder.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import math
from numbers import Integral, Real


BASE_FEATURE_NAMES = [
    "log1p_event_count",
    "high_severity_fraction",
    "distinct_template_fraction",
    "dominant_template_fraction",
    "log1p_mean_message_length",
]
CONTEXT_FEATURE_NAMES = [
    "mean_template_surprisal",
    "unseen_template_fraction",
    "host_log_count_deviation",
    "unseen_host_indicator",
]
FEATURE_NAMES = BASE_FEATURE_NAMES + CONTEXT_FEATURE_NAMES
MAX_TEMPLATES = 100_000
MAX_HOSTS = 50_000


@dataclass
class _Moments:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value):
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def std(self):
        # Population moments of observed training windows, without empty bins.
        return math.sqrt(max(0.0, self.m2 / self.count)) if self.count else 0.0


def _validate_record(record):
    """Read only declared observed fields, never ground-truth labels."""
    count = record["count"]
    if isinstance(count, bool) or not isinstance(count, Integral) or count <= 0:
        raise ValueError("Window count must be a positive integer")
    host = record["host"]
    if not isinstance(host, str) or not host:
        raise ValueError("An observed host-window requires a nonempty host")
    histogram = record["templates"]
    if not isinstance(histogram, Mapping) or not histogram:
        raise ValueError("Template histogram must be a nonempty mapping")
    total = 0
    for key, value in histogram.items():
        if not isinstance(key, str) or not key:
            raise ValueError("Template keys must be nonempty strings")
        if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
            raise ValueError("Template counts must be positive integers")
        total += value
    if total != count:
        raise ValueError("Template histogram count does not match window count")
    base = record["features"]
    if len(base) != len(BASE_FEATURE_NAMES):
        raise ValueError("Expected five base window features")
    if any(
        isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) for value in base
    ):
        raise ValueError("Base window features must be finite numbers")
    return int(count), host, histogram, [float(value) for value in base]


class TrainReference:
    """Bounded training-only reference, serializable with pickle/joblib.

    No label or phase is inferred here: the caller must supply only training
    records to ``fit``. Reference identifiers belong in private model artifacts,
    while ``summary`` deliberately exposes only aggregate metadata.
    """

    @classmethod
    def fit(cls, records, *, max_templates=MAX_TEMPLATES, max_hosts=MAX_HOSTS):
        for name, limit, maximum in (
            ("max_templates", max_templates, MAX_TEMPLATES),
            ("max_hosts", max_hosts, MAX_HOSTS),
        ):
            if isinstance(limit, bool) or not isinstance(limit, Integral) or not 1 <= limit <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")
        result = cls()
        result._templates = {}
        result._hosts = {}
        result._global = _Moments()
        result._total_events = 0
        result._max_templates = int(max_templates)
        result._max_hosts = int(max_hosts)
        for record in records:
            count, host, histogram, _ = _validate_record(record)
            if host not in result._hosts:
                if len(result._hosts) >= max_hosts:
                    raise ValueError("Training host reference exceeds bounded capacity")
                result._hosts[host] = _Moments()
            for key, value in histogram.items():
                if key not in result._templates and len(result._templates) >= max_templates:
                    raise ValueError("Training template reference exceeds bounded capacity")
                result._templates[key] = result._templates.get(key, 0) + int(value)
            log_count = math.log1p(count)
            result._hosts[host].add(log_count)
            result._global.add(log_count)
            result._total_events += count
        if not result._global.count:
            raise ValueError("A training reference requires at least one window")
        return result

    @property
    def names(self):
        return list(FEATURE_NAMES)

    def transform(self, record):
        count, host, histogram, base = _validate_record(record)
        denominator = self._total_events + len(self._templates) + 1
        log_denominator = math.log(denominator)
        surprisal = math.fsum(
            (value / count) * (log_denominator - math.log(self._templates.get(key, 0) + 1))
            for key, value in sorted(histogram.items())
        )
        unseen = sum(value for key, value in histogram.items() if key not in self._templates)
        host_moments = self._hosts.get(host)
        mean = host_moments.mean if host_moments else self._global.mean
        std = max(host_moments.std if host_moments else 0.0, self._global.std, 0.1)
        transformed = base + [
            surprisal,
            unseen / count,
            (math.log1p(count) - mean) / std,
            float(host_moments is None),
        ]
        if not all(math.isfinite(value) for value in transformed):
            raise ValueError("Context transformation produced nonfinite features")
        return transformed

    def summary(self):
        return {
            "train_unit_count": self._global.count,
            "total_train_events": self._total_events,
            "template_vocabulary_size": len(self._templates),
            "host_count": len(self._hosts),
            "max_templates": self._max_templates,
            "max_hosts": self._max_hosts,
            "policy": "frozen_train_only_laplace_template_frequency_host_welford_v1",
            "template_probability": "(train_count + 1) / (total_train_events + vocabulary_size + 1)",
            "host_statistics": "population mean/std of log1p(count) over observed training host-windows",
            "host_scale_floor": 0.1,
            "unknown_host_reference": "global training mean and std",
        }
