"""UTC query contract and server-side aggregation over explicitly synthetic fixtures.

The repository boundary deliberately does not claim a MySQL connection. A real
repository must implement source authorization, revision snapshots and run coverage.
"""

from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timedelta, timezone
from math import ceil, expm1, floor, log1p
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.contracts import (
    ChartMode,
    DetectorSort,
    InvestigationState,
    QueryError,  # re-exported: callers import it from here
    TimeRange,
    ZoneKey,
)
from app.demo import ANOMALIES, PRIORITIES
from app.services.redaction import redact

Record = dict[str, Any]  # one anomaly record (fixture or persisted), as served to the client

UTC = timezone.utc
START = datetime(2026, 11, 3, 6, 50, tzinfo=UTC)
END = START + timedelta(hours=1)
REVISION = "synthetic-fixture-v2.1"
DETECTORS = {
    "error-burst": ("Error burst", "Rules"),
    "timeout-frequency": ("Timeout frequency", "Rules"),
    "isolation-forest": ("Isolation Forest", "Statistical / pattern"),
    "event-novelty": ("Event novelty", "Statistical / pattern"),
}
SOURCES = {
    "demo": "Synthetic fixture",
    "empty": "Empty synthetic source",
    "partial": "Partial-coverage fixture",
    "unprocessed": "Unprocessed source fixture",
}
DURATIONS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 43200, 86400, 172800, 604800]
ZONES = {"local": "Asia/Ho_Chi_Minh", "utc": "UTC", "America/New_York": "America/New_York"}


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("offset required")
        return parsed.astimezone(UTC)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise QueryError("Timestamps must be ISO 8601 with an explicit UTC offset.") from exc


def integer(value: object, lower: int, upper: int, name: str) -> int:
    try:
        if isinstance(value, (bool, float)):
            raise ValueError()  # JSON true/1.9 must not silently become 1
        number = int(value)  # type: ignore[call-overload]  # any input; failures become QueryError
        if not lower <= number <= upper:
            raise ValueError()
        return number
    except (ValueError, TypeError, OverflowError) as exc:
        raise QueryError(f"{name} must be between {lower} and {upper}.") from exc


def iter_records(source: str) -> Iterator[Record]:
    """Adapt existing presentation records; no new detector evidence is invented."""
    if source in {"empty", "unprocessed"}:
        return
    names = {name: key for key, (name, _) in DETECTORS.items()}
    for event in ANOMALIES:
        item = dict(event)
        item["timestamp"] = iso(datetime.fromisoformat(f"2026-11-03T{event['time']}+07:00"))
        item["detector_id"] = names[event["detector"]]
        yield redact(item)


def records(source: str) -> list[Record]:
    return list(iter_records(source))


# Preset ranges in seconds, ending at the latest data (persisted datasets) or the fixture end. "full" is
# the whole fixture hour here and the whole dataset for persisted data, so it is not listed.
RANGE_SECONDS = {
    "recent": 2100,
    "early": 1500,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
}
MAX_RANGE = timedelta(days=366)


def choice(args: Mapping[str, Any], key: str, default: str, allowed: Iterable[str], message: str) -> str:
    value = args.get(key, default)
    if value not in allowed:
        raise QueryError(message)
    return cast(str, value)


def query_range(args: Mapping[str, Any], preset: str) -> tuple[datetime, datetime]:
    """The half-open UTC range: explicit start_time/end_time, or the preset over the fixture hour."""
    if preset not in {"full", *RANGE_SECONDS, "custom"}:
        raise QueryError("Unknown time range.")
    if bool(args.get("start_time")) != bool(args.get("end_time")):
        raise QueryError("Both start_time and end_time are required.")
    if preset == "custom" and not args.get("start_time"):
        raise QueryError("Custom ranges require explicit start_time and end_time.")
    if args.get("start_time"):
        start, end = instant(args["start_time"]), instant(args["end_time"])
    elif preset == "early":
        start, end = START, START + timedelta(minutes=25)
    else:
        start, end = END - timedelta(seconds=RANGE_SECONDS.get(preset, 3600)), END
    if start >= end or end - start > MAX_RANGE:
        raise QueryError("Time range must be positive and no longer than 366 days.")
    return start, end


def reset_range(args: Mapping[str, Any], start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """The range "reset zoom" returns to; defaults to the current range."""
    base_start = instant(args.get("base_start_time") or iso(start))
    base_end = instant(args.get("base_end_time") or iso(end))
    if base_start >= base_end or base_end - base_start > MAX_RANGE:
        raise QueryError("Invalid reset-zoom range.")
    return base_start, base_end


def facet_filters(args: Mapping[str, Any]) -> dict[str, list[str]]:
    """Repeated facet keys, de-duplicated and sorted; detectors may be given by display name."""
    vocabulary: dict[str, list[str]] = {
        "host": sorted({e["host"] for e in ANOMALIES}),
        "service": sorted({e["service"] for e in ANOMALIES}),
        "severity": list(PRIORITIES),
        "detector": list(DETECTORS),
    }
    aliases = {name: did for did, (name, _) in DETECTORS.items()}
    facets: dict[str, list[str]] = {}
    for key, choices in vocabulary.items():
        values = args.getlist(key) if hasattr(args, "getlist") else args.get(key, [])
        if isinstance(values, str):
            values = [values]
        if key == "detector":
            values = [aliases.get(v, v) for v in values]
        values = sorted({v for v in values if v and v != "all"})
        if len(values) > 100 or any(v not in choices for v in values):
            raise QueryError(f"Unknown {key} value.")
        facets[key] = values
    return facets


def timeline_selection(
    args: Mapping[str, Any], start: datetime, end: datetime, detectors: list[str]
) -> tuple[str, str, str]:
    """A brushed timeline interval (and optionally one detector lane) inside the query range."""
    s0, s1 = args.get("selection_start"), args.get("selection_end")
    if bool(s0) != bool(s1):
        raise QueryError("Both timeline selection boundaries are required.")
    if s0 and s1:
        a, b = instant(s0), instant(s1)
        if not start <= a < b <= end:
            raise QueryError("Timeline selection must be inside the query range.")
        interval = (iso(a), iso(b))
    else:
        interval = ("", "")
    lane = args.get("selection_detector", "")
    if lane and (lane not in DETECTORS or not s0 or (detectors and lane not in detectors)):
        raise QueryError("Invalid selected detector.")
    return interval[0], interval[1], lane


def query(args: Mapping[str, Any]) -> InvestigationState:
    """Validate repeated query keys; AND dimensions, OR values within a dimension.

    Checks run in a fixed order, so a request with several problems always reports the same one.
    """
    source = choice(
        args, "source", "demo", SOURCES, "Unknown source. Only labelled synthetic sources are connected."
    )
    zone = choice(args, "timezone", "local", ZONES, "Unsupported display timezone.")
    try:
        ZoneInfo(ZONES[zone])
    except ZoneInfoNotFoundError as exc:
        raise QueryError("Timezone database unavailable. Install requirements.txt.") from exc
    preset = args.get("range", "full")
    start, end = query_range(args, preset)
    search = args.get("q", "").strip()
    if len(search) > 200:
        raise QueryError("Search is limited to 200 characters.")
    base_start, base_end = reset_range(args, start, end)
    facets = facet_filters(args)
    selection_start, selection_end, selection_detector = timeline_selection(
        args, start, end, facets["detector"]
    )
    sort = choice(args, "sort", "priority", {"priority", "count", "recent"}, "Invalid detector sort.")
    mode = choice(args, "mode", "severity", {"severity", "volume"}, "Invalid visualization mode.")
    requested = args.get("resolution", "auto")
    return InvestigationState(
        source=source,
        range=cast(TimeRange, preset),
        start_time=iso(start),
        end_time=iso(end),
        base_start_time=iso(base_start),
        base_end_time=iso(base_end),
        timezone=cast(ZoneKey, zone),
        q=search,
        host=facets["host"],
        service=facets["service"],
        severity=facets["severity"],
        detector=facets["detector"],
        selection_start=selection_start,
        selection_end=selection_end,
        selection_detector=selection_detector,
        width=integer(args.get("width", 1000), 240, 4000, "Chart width"),
        page=integer(args.get("page", 1), 1, 100000, "Page"),
        limit=integer(args.get("limit", 50), 1, 100, "Page size"),
        row_page=integer(args.get("row_page", 1), 1, 100000, "Detector page"),
        sort=cast(DetectorSort, sort),
        mode=cast(ChartMode, mode),
        resolution="auto" if requested == "auto" else integer(requested, 60, 604800, "Resolution"),
    )


def matches(event: Record, state: InvestigationState, excluded: str | None = None) -> bool:
    stamp = instant(event["timestamp"])
    if not instant(state["start_time"]) <= stamp < instant(state["end_time"]):
        return False
    for key, field in [
        ("host", "host"),
        ("service", "service"),
        ("severity", "severity"),
        ("detector", "detector_id"),
    ]:
        values = cast(Mapping[str, list[str]], state)[key]
        if key != excluded and values and event.get(field) not in values:
            return False
    return not state["q"] or state["q"].casefold() in " ".join(str(v) for v in event.values()).casefold()


def selected(event: Record, state: InvestigationState) -> bool:
    return not state["selection_start"] or (
        instant(state["selection_start"]) <= instant(event["timestamp"]) < instant(state["selection_end"])
        and (not state["selection_detector"] or state["selection_detector"] == event["detector_id"])
    )


def resolution(state: InvestigationState) -> int:
    a, b = instant(state["start_time"]).timestamp(), instant(state["end_time"]).timestamp()
    budget = min(120, max(8, state["width"] // 28))
    requested = state["resolution"]
    if isinstance(requested, int):
        duration = requested
    else:  # "auto". Five minutes is the fixture's meaningful minimum; no sub-minute accuracy claim.
        duration = next((d for d in DURATIONS if d >= 300 and ceil(b / d) - floor(a / d) <= budget), 604800)
    if ceil(b / duration) - floor(a / duration) > 120:
        raise QueryError("Resolution produces more than 120 bins. Choose Auto or a coarser interval.")
    return duration


def coverage(a: datetime, b: datetime, source: str) -> str:
    if source == "unprocessed":
        return "unprocessed"
    if source == "empty":
        return "no_data"
    covered_end = END - timedelta(minutes=15) if source == "partial" else END
    if a >= covered_end or b <= START:
        return "missing"
    if a < START or b > covered_end:
        return "partial"
    return "complete"


def display_time(stamp: str, zone: str, include_date: bool = False) -> str:
    date = instant(stamp).astimezone(ZoneInfo(ZONES[zone]))
    return date.strftime("%d %b %Y %H:%M:%S %z" if include_date else "%H:%M")


def summary(event: Record, state: InvestigationState) -> Record:
    """Result rows carry identity and summary only; raw evidence loads on demand."""
    return {
        key: event.get(key)
        for key in [
            "id",
            "timestamp",
            "host",
            "service",
            "severity",
            "score",
            "detector",
            "detector_id",
            "unit",
            "message",
        ]
    } | {"display_time": display_time(event["timestamp"], state["timezone"], True), "synthetic": True}


VOLUME_BANDS = 4
LANES_PER_PAGE = 12


def volume_scale(maximum: int) -> list[dict[str, int]]:
    """Log-spaced count bands for the volume view; bands that would be empty are left out."""
    scale = []
    previous = 0
    for band in range(1, VOLUME_BANDS + 1):
        upper = maximum if band == VOLUME_BANDS else floor(expm1(log1p(maximum) * band / VOLUME_BANDS))
        if upper > previous:
            scale.append(dict(band=band, lower=previous + 1, upper=upper))
        previous = upper
    return scale


def volume_band(count: int, maximum: int) -> int:
    """The volume_scale band (1-4) a cell's count falls in; 0 for an empty cell."""
    if not count:
        return 0
    return min(VOLUME_BANDS, max(1, ceil(VOLUME_BANDS * log1p(count) / log1p(maximum))))


def cell_selected(cell: Record, lane_id: str, state: InvestigationState) -> bool:
    """Whether a timeline cell lies in the current selection on its lane ("" is the overall lane)."""
    return bool(
        state["selection_start"]
        and lane_id == state["selection_detector"]
        and instant(cell["start"]) < instant(state["selection_end"])
        and instant(cell["end"]) > instant(state["selection_start"])
    )


def time_bins(state: InvestigationState, duration: int) -> list[Record]:
    """Half-open bins of ``duration`` seconds aligned to the epoch, clipped to the query range."""
    start, end = instant(state["start_time"]), instant(state["end_time"])
    zone = state["timezone"]
    bins: list[Record] = []
    lower = floor(start.timestamp() / duration) * duration
    while lower < end.timestamp():
        a = max(start, datetime.fromtimestamp(lower, UTC))
        b = min(end, datetime.fromtimestamp(lower + duration, UTC))
        bins.append(
            dict(
                start=iso(a),
                end=iso(b),
                label=display_time(iso(a), zone),
                full_label=f"{display_time(iso(a), zone, True)} – {display_time(iso(b), zone, True)}",
                coverage=coverage(a, b, state["source"]),
                partial_bin=(b - a).total_seconds() != duration,
            )
        )
        lower += duration
    return bins


def count_cells(
    scope: list[Record], bins: list[Record], origin: int, duration: int
) -> tuple[list[Record], dict[str, list[Record]]]:
    """Per-bin counts, severity mix and highest priority: the overall lane and one lane per detector."""

    def empty() -> list[Record]:
        return [dict(meta, count=0, severity=dict.fromkeys(PRIORITIES, 0), priority=0) for meta in bins]

    by_detector = {did: empty() for did in DETECTORS}
    overall = empty()
    for event in scope:
        index = floor((instant(event["timestamp"]).timestamp() - origin) / duration)
        for cell in [by_detector[event["detector_id"]][index], overall[index]]:
            cell["count"] += 1
            cell["severity"][event["severity"]] += 1
            cell["priority"] = max(cell["priority"], PRIORITIES[event["severity"]])
    return overall, by_detector


def detector_lanes(
    state: InvestigationState, scope: list[Record], by_detector: dict[str, list[Record]]
) -> tuple[list[Record], int, int]:
    """The requested page of detector lanes in the chosen order, the lane count and the clamped page."""
    lanes: list[Record] = [
        dict(
            id=did,
            name=name,
            group=group,
            cells=by_detector[did],
            count=sum(c["count"] for c in by_detector[did]),
            priority=max((c["priority"] for c in by_detector[did]), default=0),
            recent=max((e["timestamp"] for e in scope if e["detector_id"] == did), default=""),
        )
        for did, (name, group) in DETECTORS.items()
        if not state["detector"] or did in state["detector"]
    ]
    order = state["sort"]
    lanes.sort(key=lambda r: (-(r["priority"] if order == "priority" else r["count"]), r["name"]))
    if order == "recent":
        lanes.sort(key=lambda r: (r["recent"], r["name"]), reverse=True)
    row_count = len(lanes)
    row_page = min(state["row_page"], max(1, ceil(row_count / LANES_PER_PAGE)))
    return lanes[(row_page - 1) * LANES_PER_PAGE : row_page * LANES_PER_PAGE], row_count, row_page


def facet_counts(state: InvestigationState, source_rows: list[Record]) -> dict[str, list[Record]]:
    """Each facet's values with counts under every other active filter (a facet never filters itself)."""
    facets: dict[str, list[Record]] = {}
    chosen = cast(Mapping[str, list[str]], state)  # the four facet keys
    fields = {"host": "host", "service": "service", "severity": "severity", "detector": "detector_id"}
    for key, field in fields.items():
        counts = Counter(e[field] for e in source_rows if matches(e, state, excluded=key))
        if key == "detector":
            values = list(DETECTORS)
        elif key == "severity":
            values = list(PRIORITIES)
        else:
            values = sorted({e[field] for e in ANOMALIES})
        facets[key] = [
            dict(
                value=v,
                label=DETECTORS[v][0] if key == "detector" else v,
                count=counts[v],
                selected=v in chosen[key],
            )
            for v in values
        ]
    return facets


def empty_reason(source: str, query_coverage: str) -> str:
    """Why an empty result is empty; missing coverage is never presented as "no anomalies"."""
    if source == "unprocessed":
        return "No detection results — this synthetic source has not been analysed."
    if source == "empty":
        return "No data available — this synthetic source contains no records."
    if query_coverage == "missing":
        return "No data coverage for this interval. Absence of anomalies is not evidence of health."
    return "No anomalies match the selected scope."


def coverage_summary(source: str, query_coverage: str, source_rows: list[Record]) -> Record:
    covered_end = END - timedelta(minutes=15) if source == "partial" else END
    return dict(
        status=query_coverage,
        dataset=SOURCES[source],
        interval=f"{iso(START)} – {iso(covered_end)}" if source in {"demo", "partial"} else "Unavailable",
        last_processed=None,
        last_event=max((e["timestamp"] for e in source_rows), default=None),
        ingestion="Not connected — synthetic fixture",
        analysis="Not run — presentation records only",
        freshness="Historical fixture; no live freshness measurement",
        raw_log_count=None,
        parsed_event_count=None,
    )


def build(state: InvestigationState) -> dict[str, Any]:
    """The full investigation view over the fixtures: timeline lanes, facets, one result page, coverage."""
    source_rows = records(state["source"])
    scope = [e for e in source_rows if matches(e, state)]
    results = sorted(
        (e for e in scope if selected(e, state)), key=lambda e: (e["timestamp"], e["id"]), reverse=True
    )
    duration = resolution(state)
    start, end = instant(state["start_time"]), instant(state["end_time"])
    bins = time_bins(state, duration)
    origin = floor(start.timestamp() / duration) * duration
    overall, by_detector = count_cells(scope, bins, origin, duration)
    maximum = max((c["count"] for c in overall), default=0)
    for lane_id, cells in [("", overall), *by_detector.items()]:
        for cell in cells:
            cell["volume"] = volume_band(cell["count"], maximum)
            cell["selected"] = cell_selected(cell, lane_id, state)
    lanes, row_count, row_page = detector_lanes(state, scope, by_detector)
    page = min(state["page"], max(1, ceil(len(results) / state["limit"])))
    state = state.copy()  # the returned scope reports the clamped pages
    state["page"], state["row_page"] = page, row_page
    first = (page - 1) * state["limit"]
    query_coverage = coverage(start, end, state["source"])
    zone = state["timezone"]
    return dict(
        state=state,
        revision=REVISION,
        mode="demo",
        scope_count=len(scope),
        result_count=len(results),
        high_critical_count=sum(e["severity"] in {"High", "Critical"} for e in scope),
        events=[summary(e, state) for e in results[first : first + state["limit"]]],
        page_count=max(1, ceil(len(results) / state["limit"])),
        row_count=row_count,
        row_page_count=max(1, ceil(row_count / LANES_PER_PAGE)),
        facets=facet_counts(state, source_rows),
        timeline=dict(
            resolution=duration,
            bins=len(bins),
            overall=overall,
            lanes=lanes,
            volume_max=maximum,
            volume_scale=volume_scale(maximum),
        ),
        range_label=f"{display_time(iso(start), zone, True)} – {display_time(iso(end), zone, True)}",
        coverage=coverage_summary(state["source"], query_coverage, source_rows),
        empty_reason=empty_reason(state["source"], query_coverage),
        sources=SOURCES,
    )


def detail(anomaly_id: str, source: str = "demo") -> dict[str, Any] | None:
    rows = records(source)
    event = next((e for e in rows if e["id"] == anomaly_id), None)
    if not event:
        return None
    # Related records are actual fixture records sharing a host, not generated prose.
    related = [
        dict(id=e["id"], timestamp=e["timestamp"], message=e["message"])
        for e in rows
        if e["host"] == event["host"] and e["id"] != event["id"]
    ]
    return dict(
        event,
        synthetic=True,
        raw_log=f"2026-11-03T{event['time']}+07:00 [DEMO] {event['host']} {event['service']}: {event['message']}",
        parsed_fields={"host": event["host"], "service": event["service"], "timestamp": event["timestamp"]},
        parsed_fields_note="Fixture fields; no parser executed.",
        model_version=None,
        score_interpretation="Illustrative detector ranking on a 0–100 scale, not a calibrated probability or evidence of root cause.",
        evidence_note="Observed/reference and raw text below belong to this synthetic presentation record, not a model run.",
        related_events=related,
    )


def export_rows(state: InvestigationState) -> list[Record]:
    return sorted(
        (e for e in records(state["source"]) if matches(e, state) and selected(e, state)),
        key=lambda e: (e["timestamp"], e["id"]),
        reverse=True,
    )
