"""Investigation V2 adapter backed by bounded MySQL queries, never raw fixtures."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any, cast

from sqlalchemy import Row, Select, func, or_, select, text
from werkzeug.datastructures import MultiDict

from app.contracts import (
    InvestigationState,
    anomaly_identity,
    dataset_id_of,
    dataset_source,
)
from app.extensions import db
from app.models import (
    AnomalyOutput as A,
    CoverageInterval,
    Dataset,
    DetectionUnit as U,
    Detector as D,
    DetectorRun as R,
    DetectorVersion as V,
    LogEvent as E,
)
from app.security import authorized_datasets, require_dataset
from app.services.investigation import (
    PRIORITIES,
    RANGE_SECONDS,
    QueryError,
    cell_selected,
    display_time,
    instant,
    integer,
    iso,
    query,
    resolution,
    volume_band,
    volume_scale,
)
from app.services.redaction import redact

Record = dict[str, Any]

HOST = func.coalesce(U.host, E.host)
FIELDS = {
    "host": HOST,
    "service": E.service,
    "severity": func.coalesce(A.priority, "Unknown"),
    "detector": D.id,
}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def state(args: MultiDict[str, str]) -> InvestigationState:
    """Validated scope for a MySQL investigation request. The API validates it in before_request and
    again in each view; within one request the result is reused instead of re-running its scans."""
    from flask import g, has_request_context, request

    if has_request_context() and args is request.args:
        cached: InvestigationState | None = g.get("_mysql_investigation_state")
        if cached is None:
            cached = g._mysql_investigation_state = _state(args)
        return deepcopy(cached)
    return _state(args)


def _state(args: MultiDict[str, str]) -> InvestigationState:
    source = args.get("source", "")
    dataset_id = dataset_id_of(source)
    require_dataset(dataset_id)
    from flask import current_app

    if "sqlalchemy" not in current_app.extensions:
        from werkzeug.exceptions import ServiceUnavailable

        raise ServiceUnavailable(description="Database is not configured.")
    dataset = db.session.get(Dataset, dataset_id)
    if dataset is None:
        raise QueryError("Dataset not found.")
    safe = MultiDict(
        (k, v)
        for k, v in args.items(multi=True)
        if k
        not in {
            "source",
            "host",
            "service",
            "detector",
            "severity",
            "selection_detector",
        }
    )
    safe["source"] = "demo"
    if bool(safe.get("start_time")) != bool(safe.get("end_time")):
        raise QueryError("Both UTC range boundaries are required.")
    if not safe.get("start_time"):
        if safe.get("range") == "custom":
            raise QueryError("Custom ranges require explicit UTC boundaries.")
        first, last = db.session.execute(
            select(func.min(E.timestamp), func.max(E.timestamp)).where(E.dataset_id == dataset_id)
        ).one()
        # A window is anchored at its start, which can precede the first raw
        # record (e.g. 03:10:00 vs 03:10:30). Include completed output anchors
        # in an implicit full range; never rewrite explicit user boundaries.
        anomaly_first, anomaly_last = db.session.execute(
            select(func.min(A.anchor_time), func.max(A.anchor_time))
            .join(R, (R.dataset_id == A.dataset_id) & (R.id == A.run_id))
            .where(A.dataset_id == dataset_id, R.state == "completed")
        ).one()
        first = min((value for value in (first, anomaly_first) if value is not None), default=EPOCH)
        last = max((value for value in (last, anomaly_last) if value is not None), default=first)
        end = last + timedelta(seconds=1)
        spans = RANGE_SECONDS
        preset = safe.get("range", "full")
        if preset not in {"full", *spans}:
            raise QueryError("Unsupported dataset time range.")
        if preset == "early":
            end = min(end, first + timedelta(seconds=spans[preset]))
        elif preset in spans:
            first = end - timedelta(seconds=spans[preset])
        safe.update(
            {
                "start_time": iso(first),
                "end_time": iso(end),
                "range": preset,
            }
        )
    result = query(safe)
    result["source"] = source
    result["dataset_mode"] = dataset.data_mode
    for key in ("host", "service", "detector", "severity"):
        values = sorted(set(args.getlist(key)))
        if len(values) > 100 or any(len(x) > 128 for x in values):
            raise QueryError("Too many or invalid facet values.")
        if key == "detector":
            values = [str(integer(x, 1, 2**63 - 1, "Detector")) for x in values]
        if key == "severity" and any(x not in {*PRIORITIES, "Unknown"} for x in values):
            raise QueryError("Invalid anomaly priority.")
        result[key] = values
    result["selection_detector"] = args.get("selection_detector", "")
    if result["selection_detector"]:
        integer(result["selection_detector"], 1, 2**63 - 1, "Selected detector")
    requested = args.getlist("run_id")
    runs_query = select(R).where(R.dataset_id == dataset_id, R.state == "completed")
    if requested:
        ids = [integer(x, 1, 2**63 - 1, "Run") for x in requested]
        if len(ids) > 100:
            raise QueryError("Too many runs.")
        runs = list(db.session.scalars(runs_query.where(R.id.in_(ids))))
        if len(runs) != len(set(ids)):
            raise QueryError("Run unavailable in this dataset.")
    else:
        latest = (
            select(func.max(R.id))
            .where(R.dataset_id == dataset_id, R.state == "completed")
            .group_by(R.detector_id)
        )
        runs = list(db.session.scalars(runs_query.where(R.id.in_(latest))))
        if args.get("runs_pinned") == "1":
            runs = []
    if len({r.detector_id for r in runs}) != len(runs):
        raise QueryError("Select one completed run per logical detector to avoid replay duplicates.")
    if args.get("version_id"):
        version_id = integer(args["version_id"], 1, 2**63 - 1, "Version")
        runs = [r for r in runs if r.version_id == version_id]
    result["run_id"] = [str(r.id) for r in sorted(runs, key=lambda r: r.id)]
    result["runs_pinned"] = "1"
    return result


def base(state: InvestigationState, *, excluded: str | None = None, selection: bool = False) -> Select[Any]:
    dataset_id = dataset_id_of(state["source"])
    q = (
        select(A, U, E, D, R, V)
        .join(U, (U.dataset_id == A.dataset_id) & (U.id == A.unit_id))
        .outerjoin(E, (E.dataset_id == U.dataset_id) & (E.id == U.event_id))
    )
    q = (
        q.join(R, (R.dataset_id == A.dataset_id) & (R.id == A.run_id))
        .join(D, D.id == R.detector_id)
        .join(V, V.id == R.version_id)
    )
    q = q.where(
        A.dataset_id == dataset_id,
        A.run_id.in_([int(i) for i in state["run_id"]]),
        R.state == "completed",
        A.anchor_time >= instant(state["start_time"]),
        A.anchor_time < instant(state["end_time"]),
    )
    chosen = cast(Mapping[str, list[str]], state)  # the facet keys of FIELDS
    for key, column in FIELDS.items():
        if key != excluded and chosen[key]:
            q = q.where(column.in_([int(v) for v in chosen[key]] if key == "detector" else chosen[key]))
    if state["q"]:
        q = q.where(
            or_(
                E.message.contains(state["q"], autoescape=True),
                HOST.contains(state["q"], autoescape=True),
                D.detector_key.contains(state["q"], autoescape=True),
            )
        )
    if selection and state["selection_start"]:
        q = q.where(
            A.anchor_time >= instant(state["selection_start"]),
            A.anchor_time < instant(state["selection_end"]),
        )
        if state["selection_detector"]:
            q = q.where(D.id == int(state["selection_detector"]))
    return q


def count(q: Select[Any]) -> int:
    return db.session.scalar(select(func.count()).select_from(q.subquery())) or 0


def row_summary(row: Row[Any], state: InvestigationState) -> dict[str, Any]:
    anomaly, unit, event, detector, run, version = row
    return dict(
        id=anomaly_identity(anomaly.id),
        timestamp=iso(anomaly.anchor_time),
        display_time=display_time(iso(anomaly.anchor_time), state["timezone"], True),
        host=redact(unit.host or (event.host if event else None)),
        service=redact(event.service if event else None),
        severity=anomaly.priority or "Unknown",
        score=anomaly.score,
        detector=detector.detector_key,
        detector_id=str(detector.id),
        unit=unit.kind,
        message=redact(
            event.message[:1024]
            if event
            else f"Observed host-window: {unit.definition.get('observed_event_count', 'unavailable')} events"
        )
        if unit.definition or event
        else "Observed detection unit",
        synthetic=True
        if state.get("dataset_mode") == "synthetic"
        else False
        if state.get("dataset_mode") == "real"
        else None,
        run_id=run.id,
        version_id=version.id,
    )


def epoch_us(moment: datetime) -> int:
    """Exact integer microseconds since the Unix epoch (the SQL bucket arithmetic uses the same unit)."""
    return (moment - EPOCH) // timedelta(microseconds=1)


MICROSECONDS = 1000000
LANES_PER_PAGE = 12
MAX_COVERAGE_ROWS = 5000


def empty_cells(
    state: InvestigationState, start: datetime, end: datetime, origin: int, duration: int
) -> list[Record]:
    """Zero-count timeline cells of ``duration`` seconds from ``origin`` (epoch microseconds), clipped to the range."""
    zone = state["timezone"]
    cells: list[Record] = []
    lower = origin
    while lower < epoch_us(end):
        a = max(start, EPOCH + timedelta(microseconds=lower))
        b = min(end, EPOCH + timedelta(microseconds=lower + duration * MICROSECONDS))
        cells.append(
            dict(
                start=iso(a),
                end=iso(b),
                label=display_time(iso(a), zone),
                full_label=f"{display_time(iso(a), zone, True)} – {display_time(iso(b), zone, True)}",
                coverage="unknown",
                partial_bin=(b - a).total_seconds() != duration,
                count=0,
                severity={**dict.fromkeys(PRIORITIES, 0), "Unknown": 0},
                priority=0,
            )
        )
        lower += duration * MICROSECONDS
    return cells


def new_lane(detector_id: str, name: str, family: str, cells: list[Record]) -> Record:
    return dict(
        id=detector_id, name=name, group=family, cells=deepcopy(cells), count=0, priority=0, recent=""
    )


def count_lanes(
    state: InvestigationState, cells: list[Record], origin: int, duration: int
) -> tuple[list[Record], dict[str, Record]]:
    """Per-bin counts grouped in SQL: the overall lane and one lane per detector of the selected runs."""
    bucket = (func.timestampdiff(text("MICROSECOND"), EPOCH.replace(tzinfo=None), A.anchor_time) - origin).op(
        "DIV", precedence=100
    )(duration * MICROSECONDS)
    grouped = db.session.execute(
        base(state)
        .with_only_columns(
            D.id,
            D.detector_key,
            D.family,
            bucket,
            func.coalesce(A.priority, "Unknown"),
            func.count(),
            func.max(A.anchor_time),
        )
        .group_by(D.id, D.detector_key, D.family, bucket, A.priority)
    ).all()
    overall = deepcopy(cells)
    lanes: dict[str, Record] = {}
    for did, name, family in db.session.execute(
        select(D.id, D.detector_key, D.family)
        .join(R, R.detector_id == D.id)
        .where(R.dataset_id == dataset_id_of(state["source"]), R.id.in_([int(x) for x in state["run_id"]]))
    ):
        lanes[str(did)] = new_lane(str(did), name, family, cells)
    for detector_id, name, family, index, priority, n, recent in grouped:
        lane = lanes.setdefault(str(detector_id), new_lane(str(detector_id), name, family, cells))
        rank = PRIORITIES.get(priority, 0)
        for cell in (overall[int(index)], lane["cells"][int(index)]):
            cell["count"] += n
            cell["severity"][priority] += n
            cell["priority"] = max(cell["priority"], rank)
        lane["count"] += n
        lane["priority"] = max(lane["priority"], rank)
        lane["recent"] = max(lane["recent"], iso(recent))
    return overall, lanes


def coverage_rows(state: InvestigationState, start: datetime, end: datetime) -> list[CoverageInterval]:
    return list(
        db.session.scalars(
            select(CoverageInterval)
            .where(
                CoverageInterval.dataset_id == dataset_id_of(state["source"]),
                CoverageInterval.start_time < end,
                CoverageInterval.end_time > start,
            )
            .order_by(CoverageInterval.start_time, CoverageInterval.id)  # deterministic cut-off
            .limit(MAX_COVERAGE_ROWS)
        )
    )


def cell_coverage(cell: Record, intervals: list[CoverageInterval], run_ids: list[int]) -> str:
    """Coverage proven for one cell: complete only when ingestion, parsing and every selected run cover it."""
    a, b = instant(cell["start"]), instant(cell["end"])
    proofs = [
        r
        for r in intervals
        if r.start_time <= a and r.end_time >= b and (r.layer != "analysis" or r.run_id in run_ids)
    ]
    if any(r.state == "failed" for r in proofs):
        return "missing"
    if any(r.state == "not_processed" for r in proofs):
        return "unprocessed"
    complete = {r.layer for r in proofs if r.state == "complete"}
    analyzed = {r.run_id for r in proofs if r.layer == "analysis" and r.state == "complete"}
    if {"ingestion", "parsing", "analysis"} <= complete and set(run_ids) <= analyzed:
        return "complete"
    return "partial" if any(r.state == "partial" for r in proofs) else "unknown"


def facet_counts(state: InvestigationState, lanes: dict[str, Record]) -> dict[str, list[Record]]:
    """Each facet's top values under every other filter; selected values and in-scope detectors always listed."""
    facets: dict[str, list[Record]] = {}
    chosen = cast(Mapping[str, list[str]], state)
    labels: dict[int, str] = dict(db.session.execute(select(D.id, D.detector_key)).tuples().all())
    for key, column in FIELDS.items():
        counted = base(state, excluded=key).with_only_columns(column, func.count()).group_by(column)
        # Ties are ordered by value so the list does not reshuffle between requests.
        values = db.session.execute(counted.order_by(func.count().desc(), column).limit(100)).all()
        names = labels if key == "detector" else {}
        facets[key] = [
            dict(value=str(v), label=names.get(v, str(v)), count=n, selected=str(v) in chosen[key])
            for v, n in values
            if v is not None
        ]
        present = {f["value"] for f in facets[key]}
        facets[key] += [
            dict(value=v, label=names.get(int(v), v) if key == "detector" else v, count=0, selected=True)
            for v in chosen[key]
            if v not in present
        ]
        if key == "detector":
            known = {f["value"] for f in facets[key]}
            facets[key] += [
                dict(value=k, label=lane["name"], count=0, selected=k in chosen[key])
                for k, lane in lanes.items()
                if k not in known
            ]
    return facets


def lane_page(state: InvestigationState, lanes: dict[str, Record]) -> tuple[list[Record], int, int]:
    """The requested page of lanes in the chosen order, the lane count and the clamped page."""
    sort = state["sort"]
    ordered = sorted(
        lanes.values(),
        key=lambda r: (
            r["recent"] if sort == "recent" else r["count"] if sort == "count" else r["priority"],
            r["name"],
        ),
        reverse=True,
    )
    row_count = len(ordered)
    row_page = min(state["row_page"], max(1, ceil(row_count / LANES_PER_PAGE)))
    return ordered[(row_page - 1) * LANES_PER_PAGE : row_page * LANES_PER_PAGE], row_count, row_page


def evaluation_rows(dataset_id: int, run_ids: list[str]) -> list[Record]:
    """Stored evaluations of the selected runs; user-supplied labels are a separate, unverified row."""
    from app.domain import EvaluationReport

    rows: list[Record] = []
    for r in db.session.scalars(
        select(EvaluationReport).where(
            EvaluationReport.dataset_id == dataset_id, EvaluationReport.run_id.in_([int(i) for i in run_ids])
        )
    ):
        rows.append({"run_id": r.run_id, "metrics": r.metrics})
        if isinstance(r.metrics.get("supplied_labels"), dict):
            rows.append(
                {
                    "run_id": f"{r.run_id} · supplied labels (unverified)",
                    "metrics": r.metrics["supplied_labels"],
                }
            )
    return rows


def build(state: InvestigationState) -> dict[str, Any]:
    """The investigation view over persisted runs: timeline lanes, facets, one result page and coverage."""
    start, end = instant(state["start_time"]), instant(state["end_time"])
    duration = resolution(state)
    step = duration * MICROSECONDS
    origin = epoch_us(start) // step * step
    cells = empty_cells(state, start, end, origin, duration)
    overall, lanes = count_lanes(state, cells, origin, duration)
    maximum = max((c["count"] for c in overall), default=0)
    intervals = coverage_rows(state, start, end)
    run_ids = [int(x) for x in state["run_id"]]
    for lane_id, grid in [("", overall)] + [(k, v["cells"]) for k, v in lanes.items()]:
        for cell in grid:
            cell["coverage"] = cell_coverage(cell, intervals, run_ids)
            cell["volume"] = volume_band(cell["count"], maximum)
            cell["selected"] = cell_selected(cell, lane_id, state)
    facets = facet_counts(state, lanes)
    page_lanes, row_count, row_page = lane_page(state, lanes)
    results = base(state, selection=True)
    result_count = count(results)
    page = min(state["page"], max(1, ceil(result_count / state["limit"])))
    rows = db.session.execute(
        results.order_by(A.anchor_time.desc(), A.id.desc())
        .offset((page - 1) * state["limit"])
        .limit(state["limit"])
    ).all()
    dataset = db.session.get(Dataset, dataset_id_of(state["source"]))
    if dataset is None:  # deleted after the scope was validated
        raise QueryError("Dataset not found.")
    sources = {
        dataset_source(d.id): d.name + " · MySQL"
        for d in db.session.scalars(select(Dataset).where(Dataset.id.in_(authorized_datasets())))
    }
    zone = state["timezone"]
    return dict(
        state=dict(state, page=page, row_page=row_page),
        revision="mysql-runs-" + ",".join(state["run_id"]),
        mode="database",
        is_database=True,
        evaluations=evaluation_rows(dataset.id, state["run_id"]),
        dataset_mode=dataset.data_mode,
        scope_count=sum(c["count"] for c in overall),
        result_count=result_count,
        high_critical_count=sum(c["severity"]["High"] + c["severity"]["Critical"] for c in overall),
        events=[row_summary(r, state) for r in rows],
        page_count=max(1, ceil(result_count / state["limit"])),
        row_count=row_count,
        row_page_count=max(1, ceil(row_count / LANES_PER_PAGE)),
        facets=facets,
        timeline=dict(
            resolution=duration,
            bins=len(cells),
            overall=overall,
            lanes=page_lanes,
            volume_max=maximum,
            volume_scale=volume_scale(maximum),
        ),
        range_label=f"{display_time(iso(start), zone, True)} – {display_time(iso(end), zone, True)}",
        coverage=dict(
            status="unknown",
            dataset=dataset.name,
            interval=f"{iso(start)} – {iso(end)}",
            last_event=None,
            ingestion=dataset.state,
            analysis="Completed selected runs: " + ",".join(state["run_id"]),
            freshness="Historical imported observations; completeness unknown",
        ),
        empty_reason="No persisted anomalies match. Unknown coverage is not evidence of health.",
        sources=sources,
    )
