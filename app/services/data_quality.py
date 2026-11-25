"""Data quality checks for one dataset, computed from import counters and parsed events.

Each check compares an observed value with a stated expectation and ends as pass, warn, fail or skipped
(not enough data to judge). The quality score is the mean of the judged checks (pass 100, warn 50, fail 0).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from statistics import median
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, scoped_session

from app.models import LogEvent, RawLogRecord, SourceArtifact

HOUR = timedelta(hours=1)
BLOCK_HOURS = 6  # the volume check compares the last 6 hours with earlier 6-hour blocks
BASELINE_BLOCKS = 4  # up to 24 hours of history for the volume baseline
GRID_DAYS = 14  # the hourly coverage grid shows at most the last two weeks
POINTS = {"pass": 100, "warn": 50, "fail": 0}

# (warn above, fail above) as fractions of the rows checked.
MALFORMED_LIMITS = (0.001, 0.01)
DUPLICATE_LIMITS = (0.001, 0.01)
MISSING_LIMITS = (0.01, 0.05)
LONGEST_GAP_WARN_HOURS = 3  # longer empty stretches fail
VOLUME_DROP_LIMITS = (0.25, 0.5)


@dataclass
class QualityStats:
    """Raw numbers for one dataset; everything the checks need, without a database."""

    lines: int = 0  # physical lines read from the source files
    malformed: int = 0  # lines the parser could not read
    raw_rows: int = 0  # stored raw lines
    duplicate_rows: int = 0  # raw lines identical to an earlier one
    events: int = 0
    missing: dict[str, int] = field(default_factory=lambda: {"host": 0, "service": 0, "severity": 0})
    missing_any: int = 0  # events lacking at least one of the fields above
    hourly: dict[datetime, int] = field(default_factory=dict)  # UTC hour start -> events


def ratio_status(count: int, total: int, limits: tuple[float, float]) -> str:
    share = count / total
    return "pass" if share <= limits[0] else "warn" if share <= limits[1] else "fail"


def hour_series(hourly: dict[datetime, int]) -> list[tuple[datetime, int]]:
    """Every hour from the first to the last observed one, with zero where no event arrived."""
    if not hourly:
        return []
    hour, last = min(hourly), max(hourly)
    series = []
    while hour <= last:
        series.append((hour, hourly.get(hour, 0)))
        hour += HOUR
    return series


def check_ratio(key: str, count: int, total: int, limits: tuple[float, float]) -> dict[str, Any]:
    if total == 0:
        return {"key": key, "status": "skipped", "count": 0, "total": 0, "share": None}
    return {
        "key": key,
        "status": ratio_status(count, total, limits),
        "count": count,
        "total": total,
        "share": count / total,
    }


def check_gaps(series: list[tuple[datetime, int]]) -> dict[str, Any]:
    if not series:
        return {"key": "time_gaps", "status": "skipped", "empty_hours": 0, "longest_hours": 0, "hours": 0}
    empty = longest = run = 0
    for _, count in series:
        run = run + 1 if count == 0 else 0
        empty += count == 0
        longest = max(longest, run)
    status = "pass" if empty == 0 else "warn" if longest <= LONGEST_GAP_WARN_HOURS else "fail"
    return {
        "key": "time_gaps",
        "status": status,
        "empty_hours": empty,
        "longest_hours": longest,
        "hours": len(series),
    }


def check_volume(series: list[tuple[datetime, int]]) -> dict[str, Any]:
    counts = [count for _, count in series]
    recent = sum(counts[-BLOCK_HOURS:])
    earlier = []
    for index in range(1, BASELINE_BLOCKS + 1):
        end = len(counts) - index * BLOCK_HOURS
        if end - BLOCK_HOURS < 0:
            break
        earlier.append(sum(counts[end - BLOCK_HOURS : end]))
    baseline = median(earlier) if earlier else 0
    if not earlier or baseline == 0:
        return {"key": "volume_drop", "status": "skipped", "recent": recent, "baseline": None, "drop": None}
    drop = max(0.0, 1 - recent / baseline)
    low, high = VOLUME_DROP_LIMITS
    return {
        "key": "volume_drop",
        "status": "pass" if drop < low else "warn" if drop < high else "fail",
        "recent": recent,
        "baseline": baseline,
        "drop": drop,
        "blocks": len(earlier),
    }


def coverage_grid(series: list[tuple[datetime, int]]) -> dict[str, Any]:
    """Days by 24 UTC hours for the last GRID_DAYS days: event count, or None outside the data range."""
    if not series:
        return {"days": [], "max": 0, "truncated": False}
    first, last = series[0][0], series[-1][0]
    counts = dict(series)
    last_day = last.replace(hour=0)
    first_day = max(first.replace(hour=0), last_day - timedelta(days=GRID_DAYS - 1))
    peak = max(counts.values())
    days = []
    day = first_day
    while day <= last_day:
        cells = []
        for hour in range(24):
            start = day + timedelta(hours=hour)
            count = counts.get(start) if first <= start <= last else None
            level = None if count is None else 0 if count == 0 else level_of(count, peak)
            cells.append({"hour": hour, "count": count, "level": level})
        days.append({"date": day.date().isoformat(), "cells": cells})
        day += timedelta(days=1)
    return {"days": days, "max": peak, "truncated": first.replace(hour=0) < first_day}


def level_of(count: int, peak: int) -> int:
    """1-4 on a log scale, so quiet hours stay visible next to bursts."""
    return max(1, min(4, math.ceil(4 * math.log1p(count) / math.log1p(peak))))


def evaluate(stats: QualityStats) -> dict[str, Any]:
    series = hour_series(stats.hourly)
    checks = [
        check_ratio("malformed", stats.malformed, stats.lines, MALFORMED_LIMITS),
        check_ratio("duplicates", stats.duplicate_rows, stats.raw_rows, DUPLICATE_LIMITS),
        {**check_ratio("missing_fields", stats.missing_any, stats.events, MISSING_LIMITS), **stats.missing},
        check_gaps(series),
        check_volume(series),
    ]
    judged = [POINTS[check["status"]] for check in checks if check["status"] != "skipped"]
    return {
        "score": round(sum(judged) / len(judged)) if judged else None,
        "passed": sum(check["status"] == "pass" for check in checks),
        "judged": len(judged),
        "checks": checks,
        "lines": stats.lines,
        "events": stats.events,
        "first_hour": series[0][0].isoformat() if series else None,
        "last_hour": series[-1][0].isoformat() if series else None,
        "grid": coverage_grid(series),
    }


def collect(session: Session | scoped_session[Any], dataset_id: int) -> QualityStats:
    lines, malformed = session.execute(
        select(
            func.coalesce(func.sum(SourceArtifact.checkpoint_line), 0),
            func.coalesce(func.sum(SourceArtifact.malformed_count), 0),
        ).where(SourceArtifact.dataset_id == dataset_id)
    ).one()
    raw_rows, distinct_rows = session.execute(
        select(func.count(), func.count(func.distinct(func.md5(RawLogRecord.raw_bytes)))).where(
            RawLogRecord.dataset_id == dataset_id
        )
    ).one()

    def missing(column: Any) -> Any:
        return func.coalesce(func.sum(case((column.is_(None), 1), else_=0)), 0)

    events, host, service, severity, any_missing = session.execute(
        select(
            func.count(),
            missing(LogEvent.host),
            missing(LogEvent.service),
            missing(LogEvent.severity),
            func.coalesce(
                func.sum(
                    case(
                        (
                            LogEvent.host.is_(None)
                            | LogEvent.service.is_(None)
                            | LogEvent.severity.is_(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(LogEvent.dataset_id == dataset_id)
    ).one()
    bucket = func.date_format(LogEvent.timestamp, "%Y-%m-%d %H")
    hourly = {
        datetime.strptime(hour, "%Y-%m-%d %H").replace(tzinfo=timezone.utc): count
        for hour, count in session.execute(
            select(bucket, func.count()).where(LogEvent.dataset_id == dataset_id).group_by(bucket)
        ).tuples()
    }
    return QualityStats(
        lines=int(lines),
        malformed=int(malformed),
        raw_rows=int(raw_rows),
        duplicate_rows=int(raw_rows) - int(distinct_rows),
        events=int(events),
        missing={"host": int(host), "service": int(service), "severity": int(severity)},
        missing_any=int(any_missing),
        hourly=hourly,
    )


def quality_report(session: Session | scoped_session[Any], dataset_id: int) -> dict[str, Any]:
    """The report depends only on the imported data, so it is reused until the next import batch."""
    from app.models import Dataset
    from app.services.report_cache import cached

    revision = session.scalar(select(Dataset.input_revision).where(Dataset.id == dataset_id))
    newest = session.scalar(select(func.max(RawLogRecord.id)).where(RawLogRecord.dataset_id == dataset_id))
    return cached(("quality", dataset_id, revision, newest), lambda: evaluate(collect(session, dataset_id)))
