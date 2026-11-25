"""Overview of one dataset: headline numbers, a "needs attention" list and the recent log volume.

Every number reuses an existing service (data quality, pipeline, Log Explorer insights) so the overview
never disagrees with the page it links to.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, scoped_session
from werkzeug.datastructures import MultiDict

from app.models import AnomalyOutput, Dataset, LogEvent
from app.services.report_cache import cached

SEVERE = ("ERROR", "FATAL", "SEVERE", "FAILURE")
VOLUME_HOURS = 48  # the volume chart shows the last 48 hours of data
RANK = {"critical": 0, "warn": 1, "info": 2}


def whole_second(value: str, *, up: bool) -> str:
    """An ISO instant at second precision (the Log Explorer time fields take at most milliseconds);
    ``up`` rounds the end of a range up so the range still covers every event."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    whole = moment.replace(microsecond=0)
    if up and whole != moment:
        whole += timedelta(seconds=1)
    return whole.strftime("%Y-%m-%dT%H:%M:%SZ")


def attention_items(
    *,
    quality: dict[str, Any],
    pipeline: dict[str, Any],
    insights: dict[str, Any] | None,
    open_alerts: int,
    high_anomalies: int,
    schedules: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """What an operator should look at first, most severe first. Each item names a page to open."""
    items: list[dict[str, Any]] = []
    for schedule in schedules or []:
        if schedule["last_error"]:
            items.append(
                {
                    "kind": "schedule_error",
                    "level": "critical",
                    "name": schedule["name"],
                    "error": schedule["last_error"],
                }
            )
        elif schedule["overdue"]:
            items.append({"kind": "schedule_overdue", "level": "warn", "name": schedule["name"]})
    for row in pipeline["grid"]:
        if row["latest"] == "failed":
            run = row["runs"][-1]
            items.append({"kind": "job_failed", "level": "critical", "type": row["type"], "job": run["id"]})
    for check in quality["checks"]:
        if check["status"] in {"fail", "warn"}:
            level = "critical" if check["status"] == "fail" else "warn"
            items.append({"kind": "quality", "level": level, "check": check["key"]})
    if open_alerts:
        items.append({"kind": "alerts", "level": "warn", "count": open_alerts})
    if high_anomalies:
        items.append({"kind": "anomalies", "level": "warn", "count": high_anomalies})
    if insights:
        for spike in insights["error_spikes"]:
            items.append(
                {
                    "kind": "spike",
                    "level": "warn",
                    "count": spike["count"],
                    "baseline": spike["baseline"],
                    "start": whole_second(spike["start"], up=False),
                    "end": whole_second(spike["end"], up=True),
                }
            )
        for pattern in insights["new_patterns"]:
            items.append(
                {
                    "kind": "new_pattern",
                    "level": "info",
                    "pattern": pattern["pattern"],
                    "count": pattern["count"],
                    "terms": pattern["filter_terms"],
                }
            )
    if pipeline["queued"]:
        items.append({"kind": "queued", "level": "info", "count": pipeline["queued"]})
    return sorted(items, key=lambda item: RANK[item["level"]])


def volume(hourly: dict[Any, tuple[int, int]]) -> list[dict[str, Any]]:
    """The last VOLUME_HOURS hours of data (empty hours included): total and severe events per hour."""
    if not hourly:
        return []
    last = max(hourly)
    hours = [last - timedelta(hours=offset) for offset in range(VOLUME_HOURS - 1, -1, -1)]
    first = min(hourly)
    return [
        {
            "hour": hour.isoformat(),
            "total": hourly.get(hour, (0, 0))[0],
            "severe": hourly.get(hour, (0, 0))[1],
        }
        for hour in hours
        if hour >= first
    ]


def event_summary(session: Session | scoped_session[Any], dataset_id: int) -> dict[str, Any]:
    """Event, host and severe counts, the time range and the last VOLUME_HOURS hours of volume."""
    from datetime import timezone

    events, hosts, severe, first, last = session.execute(
        select(
            func.count(),
            func.count(func.distinct(LogEvent.host)),
            func.coalesce(func.sum(case((LogEvent.severity.in_(SEVERE), 1), else_=0)), 0),
            func.min(LogEvent.timestamp),
            func.max(LogEvent.timestamp),
        ).where(LogEvent.dataset_id == dataset_id)
    ).one()
    bucket = func.date_format(LogEvent.timestamp, "%Y-%m-%d %H")
    hourly: dict[datetime, tuple[int, int]] = {}
    if last is not None:
        rows = session.execute(
            select(
                bucket,
                func.count(),
                func.coalesce(func.sum(case((LogEvent.severity.in_(SEVERE), 1), else_=0)), 0),
            )
            .where(
                LogEvent.dataset_id == dataset_id, LogEvent.timestamp > last - timedelta(hours=VOLUME_HOURS)
            )
            .group_by(bucket)
        ).tuples()
        for hour, total, severe_count in rows:
            stamp = datetime.strptime(hour, "%Y-%m-%d %H").replace(tzinfo=timezone.utc)
            hourly[stamp] = (int(total), int(severe_count))
    return {
        "events": events,
        "hosts": hosts,
        "severe": severe,
        "first": first,
        "last": last,
        "hourly": hourly,
    }


def overview_report(session: Session | scoped_session[Any], dataset_id: int) -> dict[str, Any]:
    from app.services.data_quality import quality_report
    from app.services.log_patterns import insights as log_insights
    from app.services.log_queries import parse_scope
    from app.services.pipeline import pipeline_report
    from app.services.schedules import list_schedules

    quality = quality_report(session, dataset_id)
    pipeline = pipeline_report(session, dataset_id, quality=quality)
    revision = session.scalar(select(Dataset.input_revision).where(Dataset.id == dataset_id))
    newest_event = session.scalar(select(func.max(LogEvent.id)).where(LogEvent.dataset_id == dataset_id))
    # Counts over every event only change with the data: reused until the next import batch.
    summary = cached(
        ("events", dataset_id, revision, newest_event), lambda: event_summary(session, dataset_id)
    )
    events, hosts, severe, first, last = (summary[k] for k in ("events", "hosts", "severe", "first", "last"))
    anomalies, high = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((AnomalyOutput.priority.in_(("High", "Critical")), 1), else_=0)), 0),
        ).where(AnomalyOutput.dataset_id == dataset_id)
    ).one()
    stages = {stage["key"]: stage for stage in pipeline["flow"]}
    insights = None
    if first is not None:
        # Log Explorer insights over the whole dataset (error spikes, new patterns).
        end = last + timedelta(seconds=1)
        start = max(first, end - timedelta(days=366))
        scope = parse_scope(
            session,
            MultiDict(
                {"dataset_id": str(dataset_id), "start_time": start.isoformat(), "end_time": end.isoformat()}
            ),
        )
        # Reused until an import batch (input_revision) or a detector run (newest anomaly) changes them.
        newest = session.scalar(
            select(func.max(AnomalyOutput.id)).where(AnomalyOutput.dataset_id == dataset_id)
        )
        key = ("insights", dataset_id, revision, newest, scope.maximum_id)
        insights = cached(key, lambda: log_insights(session, scope))
    open_alerts = int(stages["alerts"]["value"])
    return {
        "events": int(events),
        "hosts": int(hosts),
        "severe": int(severe),
        "severe_share": int(severe) / int(events) if events else None,
        "first": first.isoformat() if first else None,
        "last": last.isoformat() if last else None,
        "anomalies": int(anomalies),
        "high_anomalies": int(high),
        "open_alerts": open_alerts,
        "alerts": int(stages["alerts"]["total"]),
        "quality_score": quality["score"],
        "flow": pipeline["flow"],
        "attention": attention_items(
            quality=quality,
            pipeline=pipeline,
            insights=insights,
            open_alerts=open_alerts,
            high_anomalies=int(high),
            schedules=list_schedules(session, dataset_id),
        ),
        "volume": volume(summary["hourly"]),
    }
