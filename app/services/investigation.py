"""UTC query contract and server-side aggregation over explicitly synthetic fixtures.

The repository boundary deliberately does not claim a MySQL connection. A real
repository must implement source authorization, revision snapshots and run coverage.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil, expm1, floor, log1p
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.demo import ANOMALIES, PRIORITIES
from app.services.redaction import redact

UTC = timezone.utc
START = datetime(2026, 11, 3, 6, 50, tzinfo=UTC)
END = START + timedelta(hours=1)
REVISION = 'synthetic-fixture-v2.1'
DETECTORS = {
    'error-burst': ('Error burst', 'Rules'),
    'timeout-frequency': ('Timeout frequency', 'Rules'),
    'isolation-forest': ('Isolation Forest', 'Statistical / pattern'),
    'event-novelty': ('Event novelty', 'Statistical / pattern'),
}
SOURCES = {
    'demo': 'Synthetic fixture',
    'empty': 'Empty synthetic source',
    'partial': 'Partial-coverage fixture',
    'unprocessed': 'Unprocessed source fixture',
}
DURATIONS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 43200, 86400, 172800, 604800]
ZONES = {'local': 'Asia/Ho_Chi_Minh', 'utc': 'UTC', 'America/New_York': 'America/New_York'}


class QueryError(ValueError):
    """A query the client must correct, rather than a backend outage."""


def iso(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('offset required')
        return parsed.astimezone(UTC)
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise QueryError('Timestamps must be ISO 8601 with an explicit UTC offset.') from exc


def integer(value, lower, upper, name):
    try:
        number = int(value)
        if not lower <= number <= upper:
            raise ValueError()
        return number
    except (ValueError, TypeError, OverflowError) as exc:
        raise QueryError(f'{name} must be between {lower} and {upper}.') from exc


def iter_records(source):
    """Adapt existing presentation records; no new detector evidence is invented."""
    if source in {'empty', 'unprocessed'}:
        return
    names = {name: key for key, (name, _) in DETECTORS.items()}
    for event in ANOMALIES:
        item = dict(event)
        item['timestamp'] = iso(datetime.fromisoformat(f"2026-11-03T{event['time']}+07:00"))
        item['detector_id'] = names[event['detector']]
        yield redact(item)


def records(source):
    return list(iter_records(source))


def query(args):
    """Validate repeated query keys; AND dimensions, OR values within a dimension."""
    source = args.get('source', 'demo')
    if source not in SOURCES:
        raise QueryError('Unknown source. Only labelled synthetic sources are connected.')
    zone = args.get('timezone', 'local')
    if zone not in ZONES:
        raise QueryError('Unsupported display timezone.')
    try:
        ZoneInfo(ZONES[zone])
    except ZoneInfoNotFoundError as exc:
        raise QueryError('Timezone database unavailable. Install requirements.txt.') from exc
    preset = args.get('range', 'full')
    spans = {'full': 3600, 'recent': 2100, 'early': 1500, '15m': 900,
             '1h': 3600, '6h': 21600, '24h': 86400, '7d': 604800, '30d': 2592000}
    if preset not in {*spans, 'custom'}:
        raise QueryError('Unknown time range.')
    if bool(args.get('start_time')) != bool(args.get('end_time')):
        raise QueryError('Both start_time and end_time are required.')
    if preset == 'custom' and not args.get('start_time'):
        raise QueryError('Custom ranges require explicit start_time and end_time.')
    start = instant(args['start_time']) if args.get('start_time') else (
        START if preset == 'early' else END - timedelta(seconds=spans.get(preset, 3600)))
    end = instant(args['end_time']) if args.get('end_time') else (START+timedelta(minutes=25) if preset == 'early' else END)
    if start >= end or end-start > timedelta(days=366):
        raise QueryError('Time range must be positive and no longer than 366 days.')
    search = args.get('q', '').strip()
    if len(search) > 200:
        raise QueryError('Search is limited to 200 characters.')
    vocabulary = {
        'host': sorted({e['host'] for e in ANOMALIES}),
        'service': sorted({e['service'] for e in ANOMALIES}),
        'severity': list(PRIORITIES), 'detector': list(DETECTORS),
    }
    state = dict(source=source, range=preset, start_time=iso(start), end_time=iso(end),
                 timezone=zone, q=search)
    base_start = instant(args.get('base_start_time') or iso(start))
    base_end = instant(args.get('base_end_time') or iso(end))
    if base_start >= base_end or base_end-base_start > timedelta(days=366):
        raise QueryError('Invalid reset-zoom range.')
    state.update(base_start_time=iso(base_start), base_end_time=iso(base_end))
    for key, choices in vocabulary.items():
        values = args.getlist(key) if hasattr(args, 'getlist') else args.get(key, [])
        if isinstance(values, str):
            values = [values]
        if key == 'detector':
            aliases = {name: did for did, (name, _) in DETECTORS.items()}
            values = [aliases.get(v, v) for v in values]
        values = sorted(set(v for v in values if v and v != 'all'))
        if len(values) > 100 or any(v not in choices for v in values):
            raise QueryError(f'Unknown {key} value.')
        state[key] = values
    s0, s1 = args.get('selection_start'), args.get('selection_end')
    if bool(s0) != bool(s1):
        raise QueryError('Both timeline selection boundaries are required.')
    if s0:
        a, b = instant(s0), instant(s1)
        if not start <= a < b <= end:
            raise QueryError('Timeline selection must be inside the query range.')
        state.update(selection_start=iso(a), selection_end=iso(b))
    else:
        state.update(selection_start='', selection_end='')
    selected_detector = args.get('selection_detector', '')
    if selected_detector and (selected_detector not in DETECTORS or not s0 or
                             (state['detector'] and selected_detector not in state['detector'])):
        raise QueryError('Invalid selected detector.')
    state['selection_detector'] = selected_detector
    state['width'] = integer(args.get('width', 1000), 240, 4000, 'Chart width')
    state['page'] = integer(args.get('page', 1), 1, 100000, 'Page')
    state['limit'] = integer(args.get('limit', 50), 1, 100, 'Page size')
    state['row_page'] = integer(args.get('row_page', 1), 1, 100000, 'Detector page')
    state['sort'] = args.get('sort', 'priority')
    if state['sort'] not in {'priority', 'count', 'recent'}:
        raise QueryError('Invalid detector sort.')
    state['mode'] = args.get('mode', 'severity')
    if state['mode'] not in {'severity', 'volume'}:
        raise QueryError('Invalid visualization mode.')
    requested = args.get('resolution', 'auto')
    if requested != 'auto':
        requested = integer(requested, 60, 604800, 'Resolution')
    state['resolution'] = requested
    return state


def matches(event, state, excluded=None):
    stamp = instant(event['timestamp'])
    if not instant(state['start_time']) <= stamp < instant(state['end_time']):
        return False
    for key, field in [('host', 'host'), ('service', 'service'), ('severity', 'severity'), ('detector', 'detector_id')]:
        if key != excluded and state[key] and event.get(field) not in state[key]:
            return False
    return not state['q'] or state['q'].casefold() in ' '.join(str(v) for v in event.values()).casefold()


def selected(event, state):
    return (not state['selection_start'] or
            (instant(state['selection_start']) <= instant(event['timestamp']) < instant(state['selection_end'])
             and (not state['selection_detector'] or state['selection_detector'] == event['detector_id'])))


def resolution(state):
    a, b = instant(state['start_time']).timestamp(), instant(state['end_time']).timestamp()
    budget = min(120, max(8, state['width']//28))
    duration = state['resolution']
    if duration == 'auto':
        # Five minutes is the fixture's meaningful minimum; no sub-minute accuracy claim.
        duration = next((d for d in DURATIONS if d >= 300 and ceil(b/d)-floor(a/d) <= budget), 604800)
    if ceil(b/duration)-floor(a/duration) > 120:
        raise QueryError('Resolution produces more than 120 bins. Choose Auto or a coarser interval.')
    return duration


def coverage(a, b, source):
    if source == 'unprocessed':
        return 'unprocessed'
    if source == 'empty':
        return 'no_data'
    covered_end = END - timedelta(minutes=15) if source == 'partial' else END
    if a >= covered_end or b <= START:
        return 'missing'
    if a < START or b > covered_end:
        return 'partial'
    return 'complete'


def display_time(stamp, zone, include_date=False):
    date = instant(stamp).astimezone(ZoneInfo(ZONES[zone]))
    return date.strftime('%d %b %Y %H:%M:%S %z' if include_date else '%H:%M')


def summary(event, state):
    """Result rows carry identity and summary only; raw evidence loads on demand."""
    return {key: event.get(key) for key in ['id', 'timestamp', 'host', 'service', 'severity', 'score', 'detector', 'detector_id', 'unit', 'message']} | {
        'display_time': display_time(event['timestamp'], state['timezone'], True), 'synthetic': True}


def build(state):
    source_rows = records(state['source'])
    scope = [e for e in source_rows if matches(e, state)]
    results = sorted((e for e in scope if selected(e, state)), key=lambda e: (e['timestamp'], e['id']), reverse=True)
    duration = resolution(state)
    start, end = instant(state['start_time']), instant(state['end_time'])
    zone = state['timezone']
    bins = []
    lower = floor(start.timestamp()/duration)*duration
    while lower < end.timestamp():
        a = max(start, datetime.fromtimestamp(lower, UTC))
        b = min(end, datetime.fromtimestamp(lower+duration, UTC))
        bins.append(dict(start=iso(a), end=iso(b), label=display_time(iso(a), zone),
                         full_label=f'{display_time(iso(a), zone, True)} – {display_time(iso(b), zone, True)}',
                         coverage=coverage(a, b, state['source']), partial_bin=(b-a).total_seconds() != duration))
        lower += duration
    by_detector = {did: [dict(meta, count=0, severity={level: 0 for level in PRIORITIES}, priority=0) for meta in bins] for did in DETECTORS}
    overall = [dict(meta, count=0, severity={level: 0 for level in PRIORITIES}, priority=0) for meta in bins]
    origin = floor(start.timestamp()/duration)*duration
    for event in scope:
        index = floor((instant(event['timestamp']).timestamp()-origin)/duration)
        for cell in [by_detector[event['detector_id']][index], overall[index]]:
            cell['count'] += 1
            cell['severity'][event['severity']] += 1
            cell['priority'] = max(cell['priority'], PRIORITIES[event['severity']])
    maximum = max((c['count'] for c in overall), default=0)
    volume_scale = []
    previous = 0
    for band in range(1, 5):
        upper = maximum if band == 4 else floor(expm1(log1p(maximum)*band/4))
        if upper > previous:
            volume_scale.append(dict(band=band, lower=previous+1, upper=upper))
        previous = upper
    for did, cells in [('', overall), *by_detector.items()]:
        for cell in cells:
            cell['volume'] = min(4, max(1, ceil(4*log1p(cell['count'])/log1p(maximum)))) if cell['count'] else 0
            cell['selected'] = bool(state['selection_start'] and did == state['selection_detector'] and
                                    instant(cell['start']) < instant(state['selection_end']) and instant(cell['end']) > instant(state['selection_start']))
    lanes = [dict(id=did, name=name, group=group, cells=by_detector[did],
                  count=sum(c['count'] for c in by_detector[did]),
                  priority=max((c['priority'] for c in by_detector[did]), default=0),
                  recent=max((e['timestamp'] for e in scope if e['detector_id'] == did), default=''))
             for did, (name, group) in DETECTORS.items() if not state['detector'] or did in state['detector']]
    order = state['sort']
    lanes.sort(key=lambda r: (-(r['priority'] if order == 'priority' else r['count']), r['name']))
    if order == 'recent':
        lanes.sort(key=lambda r: (r['recent'], r['name']), reverse=True)
    row_count = len(lanes)
    row_page = min(state['row_page'], max(1, ceil(row_count/12)))
    lanes = lanes[(row_page-1)*12:row_page*12]
    facets = {}
    fields = {'host': 'host', 'service': 'service', 'severity': 'severity', 'detector': 'detector_id'}
    for key, field in fields.items():
        counts = Counter(e[field] for e in source_rows if matches(e, state, excluded=key))
        values = list(DETECTORS) if key == 'detector' else list(PRIORITIES) if key == 'severity' else sorted({e[field] for e in ANOMALIES})
        facets[key] = [dict(value=v, label=DETECTORS[v][0] if key == 'detector' else v, count=counts[v], selected=v in state[key]) for v in values]
    page = min(state['page'], max(1, ceil(len(results)/state['limit'])))
    state = dict(state, page=page, row_page=row_page)
    first = (page-1)*state['limit']
    query_coverage = coverage(start, end, state['source'])
    if state['source'] == 'unprocessed':
        empty_reason = 'No detection results — this synthetic source has not been analysed.'
    elif state['source'] == 'empty':
        empty_reason = 'No data available — this synthetic source contains no records.'
    elif query_coverage == 'missing':
        empty_reason = 'No data coverage for this interval. Absence of anomalies is not evidence of health.'
    else:
        empty_reason = 'No anomalies match the selected scope.'
    return dict(state=state, revision=REVISION, mode='demo', scope_count=len(scope), result_count=len(results),
                high_critical_count=sum(e['severity'] in {'High', 'Critical'} for e in scope),
                events=[summary(e, state) for e in results[first:first+state['limit']]],
                page_count=max(1, ceil(len(results)/state['limit'])), row_count=row_count,
                row_page_count=max(1, ceil(row_count/12)), facets=facets,
                timeline=dict(resolution=duration, bins=len(bins), overall=overall, lanes=lanes, volume_max=maximum, volume_scale=volume_scale),
                range_label=f'{display_time(iso(start), zone, True)} – {display_time(iso(end), zone, True)}',
                coverage=dict(status=query_coverage, dataset=SOURCES[state['source']],
                              interval=f'{iso(START)} – {iso(END-timedelta(minutes=15) if state["source"] == "partial" else END)}' if state['source'] in {'demo', 'partial'} else 'Unavailable',
                              last_processed=None, last_event=max((e['timestamp'] for e in source_rows), default=None),
                              ingestion='Not connected — synthetic fixture', analysis='Not run — presentation records only',
                              freshness='Historical fixture; no live freshness measurement', raw_log_count=None, parsed_event_count=None),
                empty_reason=empty_reason, sources=SOURCES)


def detail(anomaly_id, source='demo'):
    rows = records(source)
    event = next((e for e in rows if e['id'] == anomaly_id), None)
    if not event:
        return None
    # Related records are actual fixture records sharing a host, not generated prose.
    related = [dict(id=e['id'], timestamp=e['timestamp'], message=e['message']) for e in rows if e['host'] == event['host'] and e['id'] != event['id']]
    return dict(event, synthetic=True, raw_log=f"2026-11-03T{event['time']}+07:00 [DEMO] {event['host']} {event['service']}: {event['message']}",
                parsed_fields={'host': event['host'], 'service': event['service'], 'timestamp': event['timestamp']},
                parsed_fields_note='Fixture fields; no parser executed.', model_version=None,
                score_interpretation='Illustrative detector ranking on a 0–100 scale, not a calibrated probability or evidence of root cause.',
                evidence_note='Observed/reference and raw text below belong to this synthetic presentation record, not a model run.',
                related_events=related)


def export_rows(state):
    return sorted((e for e in records(state['source']) if matches(e, state) and selected(e, state)),
                  key=lambda e: (e['timestamp'], e['id']), reverse=True)
