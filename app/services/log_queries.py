"""One UTC filter/snapshot contract for log pages, volume bins and CSV."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
import re

from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import and_, func, not_, or_, select, text
from werkzeug.exceptions import NotFound

from app.models import Dataset, LogEvent
from app.services.investigation import QueryError, instant, integer, iso


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
    services: list = field(default_factory=list)
    exclude_hosts: list = field(default_factory=list)
    exclude_services: list = field(default_factory=list)
    exclude_severities: list = field(default_factory=list)
    terms: list = field(default_factory=list)
    exclude_terms: list = field(default_factory=list)


# Search syntax in the style of log explorers: ``host:R02-M1 level:ERROR -service:KERNEL "exact phrase"
# word -word``. Field values ending in ``*`` match by prefix. All parts must match (AND).
QUERY_FIELDS = {
    "host": "hosts",
    "service": "services",
    "component": "services",
    "level": "severities",
    "severity": "severities",
    "status": "severities",
}
QUERY_TOKEN = re.compile(r'(-?)(?:([A-Za-z_]+):)?(?:"([^"]*)"|(\S+))')
MAX_QUERY = 500


def parse_query(query):
    """Split a search string into field filters, exclusions and text terms."""
    parsed = {
        key: []
        for key in (
            "hosts",
            "services",
            "severities",
            "exclude_hosts",
            "exclude_services",
            "exclude_severities",
            "terms",
            "exclude_terms",
        )
    }
    if len(query) > MAX_QUERY:
        raise QueryError("Search is limited to 500 characters.")
    for negative, name, quoted, bare in QUERY_TOKEN.findall(query):
        value = quoted if quoted or not bare else bare
        if not value or value == "-":
            continue
        key = QUERY_FIELDS.get(name.lower()) if name else None
        if name and key is None:
            value = name + ":" + value  # an unknown field is plain text, e.g. a URL
        if key == "severities":
            value = value.upper()
        target = key or "terms"
        parsed[("exclude_" + target) if negative else target].append(value)
    return parsed


def field_filter(column, values):
    """Exact values, plus prefixes for values that end in ``*``."""
    exact = [value for value in values if not value.endswith("*")]
    parts = [column.in_(exact)] if exact else []
    parts += [column.startswith(value[:-1], autoescape=True) for value in values if value.endswith("*")]
    return or_(*parts)


def signer():
    return URLSafeTimedSerializer(current_app.config["EVIDENCE_CURSOR_SECRET"], salt="logs-snapshot-1")


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
    parsed = parse_query(args.get("query", "").strip())
    hosts = sorted(set(args.getlist("host")) | set(parsed["hosts"]))
    severities = sorted(set(args.getlist("severity")) | set(parsed["severities"]))
    services = sorted(set(parsed["services"]))
    excluded = {
        key: sorted(set(parsed[key])) for key in ("exclude_hosts", "exclude_services", "exclude_severities")
    }
    if (
        len(hosts) > 50
        or len(severities) > 20
        or len(services) > 50
        or any(len(values) > 50 for values in excluded.values())
        or any(
            not x or len(x) > 128
            for x in hosts + services + excluded["exclude_hosts"] + excluded["exclude_services"]
        )
        or any(not x or len(x) > 32 for x in severities + excluded["exclude_severities"])
        or any(x in {"*", ""} for x in hosts + services)
    ):
        raise QueryError("Invalid host or severity filter.")
    search = args.get("q", "").strip()
    if len(search) > 200:
        raise QueryError("Search is limited to 200 characters.")
    terms = sorted(set(parsed["terms"] + ([search] if search else [])))
    exclude_terms = sorted(set(parsed["exclude_terms"]))
    if len(terms) > 10 or len(exclude_terms) > 10 or any(len(x) > 200 for x in terms + exclude_terms):
        raise QueryError("Use at most 10 search terms of 200 characters each.")
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
                services,
                excluded,
                terms,
                exclude_terms,
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
                session.scalar(select(func.max(LogEvent.id)).where(LogEvent.dataset_id == dataset_id)) or 0
            )
            revision = dataset.input_revision
            snapshot = signer().dumps({"scope": scope_hash, "maximum": maximum, "revision": revision})
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
        raise QueryError("Snapshot/cursor expired or belongs to another filter scope.") from error
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
        services=services,
        exclude_hosts=excluded["exclude_hosts"],
        exclude_services=excluded["exclude_services"],
        exclude_severities=excluded["exclude_severities"],
        terms=terms,
        exclude_terms=exclude_terms,
    )


def predicates(scope):
    clauses = [
        LogEvent.dataset_id == scope.dataset_id,
        LogEvent.id <= scope.maximum_id,
        LogEvent.timestamp >= scope.start,
        LogEvent.timestamp < scope.end,
    ]
    for column, values, excluded in (
        (LogEvent.host, scope.hosts, scope.exclude_hosts),
        (LogEvent.service, scope.services, scope.exclude_services),
        (LogEvent.severity, scope.severities, scope.exclude_severities),
    ):
        if values:
            clauses.append(field_filter(column, values))
        if excluded:
            clauses.append(or_(column.is_(None), not_(field_filter(column, excluded))))
    for term in scope.terms:
        clauses.append(LogEvent.message.contains(term, autoescape=True))
    for term in scope.exclude_terms:
        clauses.append(not_(LogEvent.message.contains(term, autoescape=True)))
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
    count = session.scalar(select(func.count()).select_from(LogEvent).where(*predicates(scope)))
    return rows[: scope.limit], cursor, count


def timeline(session, scope, bins=60):
    duration = scope.end - scope.start
    micros = (duration.days * 86400 + duration.seconds) * 1000000 + duration.microseconds
    step = max(1000000, (micros + bins - 1) // bins)
    bucket = func.timestampdiff(text("MICROSECOND"), scope.start.replace(tzinfo=None), LogEvent.timestamp).op(
        "DIV", precedence=100
    )(step)
    levels: dict[int, dict[str, int]] = {}
    for index, severity, count in session.execute(
        select(bucket, LogEvent.severity, func.count())
        .where(*predicates(scope))
        .group_by(bucket, LogEvent.severity)
    ).all():
        levels.setdefault(int(index), {})[severity or "UNKNOWN"] = int(count)
    result = []
    for index in range((micros + step - 1) // step):
        start = scope.start + timedelta(microseconds=index * step)
        by_level = levels.get(index, {})
        result.append(
            {
                "start": iso(start),
                "end": iso(min(scope.end, start + timedelta(microseconds=step))),
                "event_count": sum(by_level.values()),
                "levels": by_level,
                "coverage": "unknown",
            }
        )
    return result


FACETS = (("level", LogEvent.severity), ("host", LogEvent.host), ("service", LogEvent.service))


def facets(session, scope, size=10):
    """Most frequent levels, hosts and components in the scope, with counts."""
    result = {}
    for name, column in FACETS:
        rows = session.execute(
            select(column, func.count().label("count"))
            .where(*predicates(scope))
            .group_by(column)
            .order_by(text("count DESC"), column)
            .limit(size)
        ).all()
        distinct = session.scalar(select(func.count(func.distinct(column))).where(*predicates(scope)))
        result[name] = {
            "values": [{"value": value, "count": int(count)} for value, count in rows],
            "distinct": int(distinct or 0),
        }
    return result
