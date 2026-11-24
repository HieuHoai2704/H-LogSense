"""Log patterns, explorer insights and surrounding events for the Log Explorer.

A pattern is a message with numbers and hexadecimal tokens replaced by ``<*>``: the same transparent,
deterministic template policy the window detectors use (not an inferred clustering model). Insights are
simple, explainable checks over the current scope: error spikes against the scope's own median, patterns
that first appear late in the range, and detector anomalies already stored for the range.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import re
from statistics import median

from sqlalchemy import and_, func, or_, select

from app.models import AnomalyOutput, LogEvent
from app.services.investigation import iso
from app.services.log_queries import predicates, timeline
from app.services.redaction import redact

PLACEHOLDER = "<*>"
VARIABLE = re.compile(r"\b(?:0x[0-9a-fA-F]+|\d+)\b")
SEVERE = {"ERROR", "FATAL", "SEVERE", "FAILURE"}
SCAN_LIMIT = 50000
MESSAGE_PREFIX = 2000


def normalize(message):
    """The message template: numbers and hexadecimal tokens become ``<*>``."""
    return VARIABLE.sub(PLACEHOLDER, message)


@dataclass
class Pattern:
    text: str
    count: int = 0
    first: datetime | None = None
    last: datetime | None = None
    levels: Counter = field(default_factory=Counter)
    sample_id: int = 0


def scan(session, scope, limit=SCAN_LIMIT):
    """Patterns of the newest ``limit`` events in scope; returns (patterns, scanned, truncated)."""
    rows = session.execute(
        select(
            LogEvent.id, LogEvent.timestamp, LogEvent.severity, func.left(LogEvent.message, MESSAGE_PREFIX)
        )
        .where(*predicates(scope))
        .order_by(LogEvent.timestamp.desc(), LogEvent.id.desc())
        .limit(limit + 1)
        .execution_options(yield_per=2000)
    )
    patterns: dict[str, Pattern] = {}
    scanned = 0
    for event_id, stamp, severity, message in rows:
        if scanned == limit:
            return patterns, scanned, True
        scanned += 1
        text = normalize(message or "")
        pattern = patterns.get(text)
        if pattern is None:
            pattern = patterns[text] = Pattern(text, sample_id=event_id, last=stamp)
        pattern.count += 1
        pattern.first = stamp  # rows arrive newest first
        pattern.levels[severity or "UNKNOWN"] += 1
    return patterns, scanned, False


def filter_terms(text):
    """Up to two long literal parts of a pattern, usable as quoted search terms."""
    parts = sorted(
        {part.strip() for part in text.split(PLACEHOLDER) if len(part.strip()) >= 4 and '"' not in part},
        key=len,
        reverse=True,
    )
    return [part[:200] for part in parts[:2]]


def describe(pattern, total):
    return {
        "pattern": redact(pattern.text[:500]),
        "count": pattern.count,
        "share": round(pattern.count / total, 4) if total else 0,
        "first": iso(pattern.first),
        "last": iso(pattern.last),
        "levels": dict(pattern.levels.most_common()),
        "sample_id": pattern.sample_id,
        "filter_terms": [redact(term) for term in filter_terms(pattern.text)],
    }


def top_patterns(session, scope, size=50):
    patterns, scanned, truncated = scan(session, scope)
    ranked = sorted(patterns.values(), key=lambda p: (-p.count, p.text))[:size]
    return {
        "patterns": [describe(p, scanned) for p in ranked],
        "pattern_count": len(patterns),
        "scanned": scanned,
        "truncated": truncated,
        "policy": "numbers and hexadecimal tokens replaced by <*>",
    }


def error_spikes(bins, limit=3):
    """Bins whose severe-level count stands far above the scope's median (median + 3 x scaled MAD)."""
    counts = [sum(n for level, n in cell["levels"].items() if level in SEVERE) for cell in bins]
    if not counts:
        return []
    middle = median(counts)
    spread = median(abs(c - middle) for c in counts) * 1.4826
    threshold = max(middle + 3 * max(spread, 1.0), 10)
    spikes = [
        {"start": cell["start"], "end": cell["end"], "count": count, "baseline": round(middle, 1)}
        for cell, count in zip(bins, counts, strict=True)
        if count >= threshold
    ]
    return sorted(spikes, key=lambda spike: -spike["count"])[:limit]


def new_patterns(session, scope, limit=3):
    """Patterns whose first event falls in the last quarter of the range (needs a complete scan)."""
    patterns, scanned, truncated = scan(session, scope)
    if truncated or not patterns:
        return [], truncated
    cutoff = scope.start + (scope.end - scope.start) * 3 / 4
    fresh = [p for p in patterns.values() if p.first is not None and p.first >= cutoff and p.count >= 3]
    fresh.sort(key=lambda p: (-p.count, p.text))
    return [describe(p, scanned) for p in fresh[:limit]], False


def detector_anomalies(session, scope):
    rows = session.execute(
        select(AnomalyOutput.priority, func.count())
        .where(
            AnomalyOutput.dataset_id == scope.dataset_id,
            AnomalyOutput.anchor_time >= scope.start,
            AnomalyOutput.anchor_time < scope.end,
        )
        .group_by(AnomalyOutput.priority)
    ).all()
    by_priority = {priority or "Unranked": int(count) for priority, count in rows}
    return {"total": sum(by_priority.values()), "by_priority": by_priority}


def insights(session, scope):
    spikes = error_spikes(timeline(session, scope, bins=60))
    fresh, truncated = new_patterns(session, scope)
    return {
        "error_spikes": spikes,
        "new_patterns": fresh,
        "new_patterns_checked": not truncated,
        "detector_anomalies": detector_anomalies(session, scope),
        "investigation": {
            "source": f"db-{scope.dataset_id}",
            "range": "custom",
            "start_time": iso(scope.start),
            "end_time": iso(scope.end),
        },
    }


def surrounding(session, scope, event, size=10):
    """Events just before and after ``event`` from the same host (any filter), oldest first."""
    same_host = LogEvent.host.is_(None) if event.host is None else LogEvent.host == event.host
    base = (LogEvent.dataset_id == scope.dataset_id, LogEvent.id <= scope.maximum_id, same_host)
    before = list(
        session.scalars(
            select(LogEvent)
            .where(
                *base,
                or_(
                    LogEvent.timestamp < event.timestamp,
                    and_(LogEvent.timestamp == event.timestamp, LogEvent.id < event.id),
                ),
            )
            .order_by(LogEvent.timestamp.desc(), LogEvent.id.desc())
            .limit(size)
        )
    )
    after = list(
        session.scalars(
            select(LogEvent)
            .where(
                *base,
                or_(
                    LogEvent.timestamp > event.timestamp,
                    and_(LogEvent.timestamp == event.timestamp, LogEvent.id > event.id),
                ),
            )
            .order_by(LogEvent.timestamp.asc(), LogEvent.id.asc())
            .limit(size)
        )
    )
    return list(reversed(before)), after
