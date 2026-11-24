"""Typed shapes shared by the API, services and workers.

These are the dictionaries that cross layer boundaries (and reach the browser as JSON), described for
type checkers. They add no runtime validation: the services that build them stay the single place where
input is checked.
"""

from typing import Literal, TypedDict

DATASET_PREFIX = "db-"
MAX_ID = 2**63 - 1  # BIGINT primary keys


class QueryError(ValueError):
    """A query the client must correct, rather than a backend outage."""


# Investigation sources: the synthetic fixtures by name, or a persisted dataset as "db-<id>".


def is_dataset_source(source: str) -> bool:
    return source.startswith(DATASET_PREFIX)


def dataset_source(dataset_id: int) -> str:
    return f"{DATASET_PREFIX}{dataset_id}"


def dataset_id_of(source: str) -> int:
    """The dataset id of a "db-<id>" source; QueryError for anything else."""
    digits = source[len(DATASET_PREFIX) :] if is_dataset_source(source) else ""
    if not (digits.isascii() and digits.isdigit()) or not 1 <= int(digits) <= MAX_ID:
        raise QueryError(f"Dataset must be between 1 and {MAX_ID}.")
    return int(digits)


# Persisted anomalies are identified to the client as "DB-<anomaly id>" (fixtures use "LS-...").
ANOMALY_PREFIX = "DB-"


def anomaly_identity(anomaly_id: int) -> str:
    return f"{ANOMALY_PREFIX}{anomaly_id}"


def anomaly_id_of(identity: str) -> int:
    """The anomaly id of a "DB-<id>" identity; QueryError for anything else."""
    if not identity.startswith(ANOMALY_PREFIX):
        raise QueryError("Invalid database anomaly ID.")
    digits = identity[len(ANOMALY_PREFIX) :]
    if not (digits.isascii() and digits.isdigit()) or not 1 <= int(digits) <= MAX_ID:
        raise QueryError(f"Anomaly must be between 1 and {MAX_ID}.")
    return int(digits)


TimeRange = Literal["full", "recent", "early", "15m", "1h", "6h", "24h", "7d", "30d", "custom"]
ZoneKey = Literal["local", "utc", "America/New_York"]
DetectorSort = Literal["priority", "count", "recent"]
ChartMode = Literal["severity", "volume"]


class _InvestigationScope(TypedDict):
    source: str
    range: TimeRange
    start_time: str  # ISO 8601 UTC ("...Z"); the end is exclusive
    end_time: str
    base_start_time: str  # range to return to on "reset zoom"
    base_end_time: str
    timezone: ZoneKey
    q: str
    host: list[str]
    service: list[str]
    severity: list[str]
    detector: list[str]
    selection_start: str  # "" when nothing is selected on the timeline
    selection_end: str
    selection_detector: str
    width: int
    page: int
    limit: int
    row_page: int
    sort: DetectorSort
    mode: ChartMode
    resolution: int | Literal["auto"]


class InvestigationState(_InvestigationScope, total=False):
    """Validated investigation scope, echoed to the client so every follow-up request is identical."""

    dataset_mode: str  # persisted datasets only
    run_id: list[str]  # persisted datasets: the completed runs in scope, one per detector
    runs_pinned: Literal["1"]


DetectorKind = Literal["rule", "isolation_forest"]


class JobConfiguration(TypedDict, total=False):
    """Analysis job configuration as accepted by POST /api/v1/jobs.

    Exactly one shape is used: a window baseline (detector, window_seconds, seed and optional aligned
    UTC bounds), a frozen study (detector + study_id) or the validated model (detector + model_id).
    """

    detector: DetectorKind
    window_seconds: Literal[60, 300, 900, 3600]
    seed: int
    start_time: str
    end_time: str
    study_id: str
    model_id: str
