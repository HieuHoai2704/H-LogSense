"""One UTC filter/snapshot contract for log pages, volume bins and CSV."""

from werkzeug.exceptions import NotFound

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib, json, math

from itsdangerous import URLSafeTimedSerializer, BadData
from sqlalchemy import select, func, or_, and_, text
from flask import current_app

from app.models import Dataset, LogEvent
from app.services.investigation import instant, integer, iso, QueryError


@dataclass
class LogScope:
    dataset_id: int
    start: datetime
    end: datetime
    hosts: list
    severities: list
    search: str
    direction: str
    limit: int
    maximum_id: int
    revision: int
    token: str
    after: tuple | None


def signer():
    return URLSafeTimedSerializer(
        current_app.config["EVIDENCE_CURSOR_SECRET"], salt="logs-snapshot-1"
    )


def parse_scope(session, args):
    dataset_id = integer(args.get("dataset_id"), 1, 2**63 - 1, "Dataset")
    from app.security import require_dataset

    require_dataset(dataset_id)
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise NotFound()
    start, end = instant(args.get("start_time")), instant(args.get("end_time"))
    if start >= end or end - start > timedelta(days=366):
        raise QueryError("Choose a positive interval of at most 366 days.")
    hosts = sorted(set(args.getlist("host")))
    severities = sorted(set(args.getlist("severity")))
    if (
        len(hosts) > 50
        or len(severities) > 20
        or any(not x or len(x) > 128 for x in hosts)
        or any(not x or len(x) > 32 for x in severities)
    ):
        raise QueryError("Invalid host or severity filter.")
    search = args.get("q", "").strip()
    if len(search) > 200:
        raise QueryError("Search is limited to 200 characters.")
    direction = args.get("sort", "desc")
    if direction not in {"asc", "desc"}:
        raise QueryError("Sort must be asc or desc.")
    limit = integer(args.get("limit", "50"), 1, 100, "Page size")
    scope_hash = hashlib.sha256(
        json.dumps(
            [
                dataset_id,
                iso(start),
                iso(end),
                hosts,
                severities,
                search,
                direction,
                limit,
            ]
        ).encode()
    ).hexdigest()
    snapshot = args.get("scope_token")
    after = None
    try:
        if snapshot:
            if len(snapshot) > 2048:
                raise ValueError()
            pinned = signer().loads(snapshot, max_age=1800)
            if pinned["scope"] != scope_hash:
                raise ValueError()
            maximum, revision = int(pinned["maximum"]), int(pinned["revision"])
        else:
            maximum = (
                session.scalar(
                    select(func.max(LogEvent.id)).where(
                        LogEvent.dataset_id == dataset_id
                    )
                )
                or 0
            )
            revision = dataset.input_revision
            snapshot = signer().dumps(
                {"scope": scope_hash, "maximum": maximum, "revision": revision}
            )
        cursor = args.get("cursor")
        if cursor:
            if len(cursor) > 4096:
                raise ValueError()
            position = signer().loads(cursor, max_age=1800)
            if position["snapshot"] != snapshot:
                raise ValueError()
            after = (
                instant(position["time"]),
                integer(position["id"], 1, 2**63 - 1, "Cursor ID"),
            )
    except (BadData, KeyError, ValueError, TypeError) as error:
        raise QueryError(
            "Snapshot/cursor expired or belongs to another filter scope."
        ) from error
    return LogScope(
        dataset_id,
        start,
        end,
        hosts,
        severities,
        search,
        direction,
        limit,
        maximum,
        revision,
        snapshot,
        after,
    )


def predicates(scope):
    clauses = [
        LogEvent.dataset_id == scope.dataset_id,
        LogEvent.id <= scope.maximum_id,
        LogEvent.timestamp >= scope.start,
        LogEvent.timestamp < scope.end,
    ]
    if scope.hosts:
        clauses.append(LogEvent.host.in_(scope.hosts))
    if scope.severities:
        clauses.append(LogEvent.severity.in_(scope.severities))
    if scope.search:
        clauses.append(LogEvent.message.contains(scope.search, autoescape=True))
    return clauses


def page(session, scope):
    query = select(LogEvent).where(*predicates(scope))
    if scope.after:
        stamp, identity = scope.after
        query = query.where(
            or_(
                LogEvent.timestamp > stamp,
                and_(LogEvent.timestamp == stamp, LogEvent.id > identity),
            )
            if scope.direction == "asc"
            else or_(
                LogEvent.timestamp < stamp,
                and_(LogEvent.timestamp == stamp, LogEvent.id < identity),
            )
        )
    order = (
        (LogEvent.timestamp.asc(), LogEvent.id.asc())
        if scope.direction == "asc"
        else (LogEvent.timestamp.desc(), LogEvent.id.desc())
    )
    rows = list(session.scalars(query.order_by(*order).limit(scope.limit + 1)))
    cursor = (
        signer().dumps(
            {
                "snapshot": scope.token,
                "time": iso(rows[scope.limit - 1].timestamp),
                "id": rows[scope.limit - 1].id,
            }
        )
        if len(rows) > scope.limit
        else None
    )
    count = session.scalar(
        select(func.count()).select_from(LogEvent).where(*predicates(scope))
    )
    return rows[: scope.limit], cursor, count


def timeline(session, scope, bins=60):
    duration = scope.end - scope.start
    micros = (
        duration.days * 86400 + duration.seconds
    ) * 1000000 + duration.microseconds
    step = max(1000000, (micros + bins - 1) // bins)
    bucket = func.timestampdiff(
        text("MICROSECOND"), scope.start.replace(tzinfo=None), LogEvent.timestamp
    ).op("DIV", precedence=100)(step)
    counts = dict(
        session.execute(
            select(bucket, func.count()).where(*predicates(scope)).group_by(bucket)
        ).all()
    )
    result = []
    for index in range((micros + step - 1) // step):
        start = scope.start + timedelta(microseconds=index * step)
        result.append(
            {
                "start": iso(start),
                "end": iso(min(scope.end, start + timedelta(microseconds=step))),
                "event_count": int(counts.get(index, 0)),
                "coverage": "unknown",
            }
        )
    return result
