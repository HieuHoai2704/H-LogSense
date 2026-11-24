"""Evidence contracts over the bounded demo repository; never generated causation.

Related pages retain at most limit+1 records while scanning the fixture iterator.
A future SQL adapter must push scope, time bounds, ordering and cursor into SQL.
"""

from datetime import timedelta
import hashlib
import heapq
import json
import re

from itsdangerous import BadData

from app.services.investigation import (
    REVISION,
    SOURCES,
    QueryError,
    instant,
    integer,
    iso,
    iter_records,
    matches,
    selected,
)
from app.services.redaction import redact

ID = re.compile(r"LS-[0-9]{4,12}\Z")
RELATIONS = {"same_host", "same_service", "before", "after", "context_window", "same_session", "same_window"}
RAW_PAGE_MAX = 8192


def find_record(anomaly_id, source):
    if not ID.fullmatch(anomaly_id):
        raise QueryError("Invalid anomaly reference.")
    return next((e for e in iter_records(source) if e["id"] == anomaly_id), None)


def raw_text(event):
    # This is the existing synthetic presentation text, not an imported raw log.
    supplied = event.get("raw_log")
    if supplied is None:
        supplied = f"2026-11-03T{event.get('time', '')}+07:00 [DEMO] {event.get('host', 'Unavailable')} {event.get('service', 'Unavailable')}: {event.get('message', 'Unavailable')}"
    if isinstance(supplied, bytes):
        supplied = supplied.decode("utf-8", errors="replace")
    elif not isinstance(supplied, str):
        supplied = json.dumps(supplied, ensure_ascii=False, default=str)
    return redact(supplied)


def bounded_fields(value, limit=8192):
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return json.loads(encoded), False
    return {
        "availability": "truncated",
        "preview_text": encoded[:limit],
        "total_chars": len(encoded),
        "note": "This field exceeds the evidence response limit; full attribute storage is not connected.",
    }, True


def raw_page(event, args):
    offset = integer(args.get("raw_offset", 0), 0, 10000000, "Raw offset")
    limit = integer(args.get("raw_limit", 2048), 128, RAW_PAGE_MAX, "Raw page size")
    text = raw_text(event)
    if offset > len(text):
        raise QueryError("Raw offset is beyond the available evidence.")
    end = min(len(text), offset + limit)
    return dict(
        text=text[offset:end],
        offset=offset,
        limit=limit,
        total_chars=len(text),
        has_more=end < len(text),
        next_offset=end if end < len(text) else None,
        synthetic=True,
        redacted=True,
        redaction_note="Credential assignments, bearer/JWT tokens, private keys and email patterns are redacted before pagination. This is not exhaustive PII detection.",
    )


def navigation(event, state):
    anchor = (instant(event["timestamp"]), event["id"])
    previous = following = None
    count = 0
    in_scope = False
    for candidate in iter_records(state["source"]):
        if not matches(candidate, state) or not selected(candidate, state):
            continue
        count += 1
        key = (instant(candidate["timestamp"]), candidate["id"])
        if candidate["id"] == event["id"]:
            in_scope = True
        elif key > anchor and (previous is None or key < previous[0]):
            previous = (key, candidate["id"])
        elif key < anchor and (following is None or key > following[0]):
            following = (key, candidate["id"])
    return dict(
        previous_id=previous[1] if previous and in_scope else None,
        next_id=following[1] if following and in_scope else None,
        in_result_scope=in_scope,
        result_count=count,
        order="newest_first",
        note="Previous/next use the complete current result scope, including timeline selection, across table pages."
        if in_scope
        else "This related record is outside the current result scope; global filters have not changed.",
    )


def relation_options(event):
    return [
        dict(
            value=key,
            available=(
                bool(event.get("session_id") or event.get("block_id"))
                if key == "same_session"
                else bool(event.get("observation_start") and event.get("observation_end"))
                if key == "same_window"
                else True
            ),
        )
        for key in [
            "same_host",
            "same_service",
            "before",
            "after",
            "context_window",
            "same_session",
            "same_window",
        ]
    ]


CURSOR_MAX_AGE = 900  # seconds a related-events cursor stays valid
MAX_CONTEXT_WINDOW = timedelta(hours=2)


def context_interval(event, kind, args):
    """The half-open interval searched for related events: +/- context_seconds, or the event's window."""
    seconds = integer(args.get("context_seconds", 1800), 1, 3600, "Context window in seconds")
    center = instant(event["timestamp"])
    start, end = center - timedelta(seconds=seconds), center + timedelta(seconds=seconds)
    if kind == "same_window":
        start, end = instant(event["observation_start"]), instant(event["observation_end"])
        if start >= end or end - start > MAX_CONTEXT_WINDOW:
            raise QueryError("Observation window is invalid or exceeds the context query limit.")
    return seconds, start, end


def cursor_position(args, signer, fingerprint):
    """Where the previous page ended, from a signed cursor bound to this exact query; None on page 1."""
    cursor = args.get("context_cursor")
    if not cursor:
        return None
    if len(cursor) > 2048:
        raise QueryError("Invalid context cursor.")
    try:
        token = signer.loads(cursor, max_age=CURSOR_MAX_AGE)
        if (
            token["scope"] != fingerprint
            or not isinstance(token["position"], list)
            or len(token["position"]) != 2
        ):
            raise ValueError()
        return (float(token["position"][0]), str(token["position"][1]))
    except (BadData, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise QueryError(
            "Context cursor expired or belongs to another query. Reload the first page."
        ) from exc


def related(candidate, event, kind, center):
    """Whether ``candidate`` stands in relationship ``kind`` to ``event`` (time bounds checked by the caller)."""
    stamp = instant(candidate["timestamp"])
    if kind == "same_host":
        return candidate.get("host") == event.get("host")
    if kind == "same_service":
        return candidate.get("service") == event.get("service")
    if kind == "before":
        return stamp < center
    if kind == "after":
        return stamp > center
    if kind == "same_session":
        return (candidate.get("session_id") or candidate.get("block_id")) == (
            event.get("session_id") or event.get("block_id")
        )
    return True


def relationship_reasons(candidate, event, kind, center, start, end):
    reasons = [f"Within the explicit context interval [{iso(start)}, {iso(end)})"]
    if candidate.get("host") == event.get("host"):
        reasons.append("Same host")
    if candidate.get("service") == event.get("service"):
        reasons.append("Same service")
    if kind == "same_session":
        reasons.append("Same supplied session/block")
    if kind == "same_window":
        reasons.append("Same supplied observation window")
    reasons.append("Before detection" if instant(candidate["timestamp"]) < center else "After detection")
    return reasons


def related_page(event, state, args, signer):
    """One keyset-paginated page of fixture events related to ``event``, each with its reasons."""
    kind = args.get("relation", "same_host")
    if kind not in RELATIONS:
        raise QueryError("Unknown related-event relationship.")
    if not next(o["available"] for o in relation_options(event) if o["value"] == kind):
        raise QueryError("This relationship is unavailable because its source fields were not supplied.")
    seconds, start, end = context_interval(event, kind, args)
    limit = integer(args.get("context_limit", 10), 1, 50, "Context page size")
    center = instant(event["timestamp"])
    fingerprint = hashlib.sha256(
        json.dumps([state["source"], event["id"], REVISION, kind, iso(start), iso(end), limit]).encode()
    ).hexdigest()
    after = cursor_position(args, signer, fingerprint)

    def key(candidate):
        value = instant(candidate["timestamp"]).timestamp()
        return (-value if kind == "before" else value, candidate["id"])

    candidates = (
        candidate
        for candidate in iter_records(state["source"])
        if candidate["id"] != event["id"]
        and start <= instant(candidate["timestamp"]) < end
        and related(candidate, event, kind, center)
        and (after is None or key(candidate) > after)
    )
    rows = heapq.nsmallest(limit + 1, candidates, key=key)
    has_more = len(rows) > limit
    items = [
        {
            field: candidate.get(field)
            for field in ["id", "timestamp", "host", "service", "message", "severity"]
        }
        | {"relationship_reasons": relationship_reasons(candidate, event, kind, center, start, end)}
        for candidate in rows[:limit]
    ]
    return dict(
        items=items,
        has_more=has_more,
        next_cursor=signer.dumps(dict(scope=fingerprint, position=list(key(rows[limit - 1]))))
        if has_more
        else None,
        limit=limit,
        relation=kind,
        context_seconds=seconds,
        interval={"start": iso(start), "end": iso(end)},
        note="Bounded related anomaly fixtures from this source, independent of global result filters. Original surrounding raw logs are unavailable.",
        available_relations=relation_options(event),
    )


def detector_evidence(event):
    """What the fixture says about the detector; anything not supplied is reported as unavailable."""
    schema, _ = bounded_fields(event.get("feature_schema"))
    features, _ = bounded_fields(event.get("feature_evidence"))
    if event["detector_id"] == "isolation-forest":
        family = "ml"
    elif event["detector_id"] in {"error-burst", "timeout-frequency"}:
        family = "rule"
    else:
        family = "unknown"
    window = event.get("observation_start") and event.get("observation_end")
    return dict(
        kind=family,
        method=event.get("detector"),
        model_name=event.get("model_name"),
        model_version=event.get("model_version"),
        model_run_id=event.get("model_run_id"),
        feature_schema=schema,
        feature_evidence=features,
        rule_id=event.get("rule_id"),
        rule_version=event.get("rule_version"),
        observed_value=event.get("actual"),
        configured_threshold=event.get("threshold"),
        reference_statistics=event.get("typical"),
        observation_window={"start": event["observation_start"], "end": event["observation_end"]}
        if window
        else None,
        score=event.get("score"),
        score_direction=event.get("score_direction"),
        score_interpretation="Synthetic 0–100 presentation ranking. Native detector score direction and calibration are unavailable. Do not compare scores across detectors or treat them as probabilities.",
        detection_unit=event.get("unit"),
        explanation=None,
        explanation_status="Explanation unavailable — no detector execution or explanation method is connected.",
    )


def evidence(event, state, args, signer):
    """The Evidence Drawer contract for one fixture anomaly; every field states its availability."""
    parsed, parsed_truncated = bounded_fields(
        event.get("parsed_attributes")
        or {"host": event.get("host"), "service": event.get("service"), "timestamp": event.get("timestamp")}
    )
    _, feature_truncated = bounded_fields(event.get("feature_evidence"))
    _, schema_truncated = bounded_fields(event.get("feature_schema"))
    detector = detector_evidence(event)
    raw = raw_page(event, args)
    related = related_page(event, state, args, signer)
    metadata = {
        field: event.get(field)
        for field in ["id", "timestamp", "host", "service", "severity", "detector", "detector_id", "unit"]
    }
    metadata.update(
        dataset_id=state["source"],
        dataset_name=SOURCES[state["source"]],
        model_run_id=event.get("model_run_id"),
    )
    return redact(
        dict(
            schema_version="1.0",
            mode="demo",
            revision=REVISION,
            anomaly=metadata,
            summary={
                "observed_signal": event.get("message"),
                "hypotheses": [],
                "root_cause": None,
                "note": "Synthetic signal statement supplied by the fixture; no generated explanation.",
            },
            raw_event={
                "page": raw,
                "provenance": {
                    "raw_timestamp": event.get("time"),
                    "parsed_timestamp": event.get("timestamp"),
                    "host": event.get("host"),
                    "source_file": event.get("source_file"),
                    "source_line": event.get("source_line"),
                    "event_reference": event["id"],
                    "original_log_available": False,
                    "parsing_status": "not_run",
                    "note": "Synthetic presentation text. No original source log or parser output is connected.",
                },
            },
            parsed_fields=parsed,
            detector_evidence=detector,
            related_events=related,
            navigation=navigation(event, state),
            availability={
                "anomaly": "synthetic",
                "raw_event": "synthetic",
                "original_raw_log": "unavailable",
                "parsed_fields": "truncated" if parsed_truncated else "fixture_only",
                "feature_evidence_truncated": feature_truncated,
                "feature_schema_truncated": schema_truncated,
                "detector_run": "unavailable",
                "explanation": "unavailable",
                "surrounding_raw_logs": "unavailable",
                "raw_page_truncated": raw["has_more"],
                "related_page_truncated": related["has_more"],
                "redaction": raw["redaction_note"],
            },
        )
    )
