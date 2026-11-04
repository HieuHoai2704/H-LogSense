"""Synthetic presentation fixtures, never detector output."""

ANOMALIES = [
    dict(id='LS-1042', time='14:32:08', host='compute-07', service='kernel', severity='Critical', score=96, detector='Error burst', unit='Time window', message='Kernel error volume exceeded the configured baseline.', actual='42 errors / min', typical='3 errors / min'),
    dict(id='LS-1041', time='14:28:41', host='storage-02', service='storage', severity='High', score=84, detector='Isolation Forest', unit='Time window', message='Unusual storage event-rate pattern.', actual='318 events / min', typical='92 events / min'),
    dict(id='LS-1040', time='14:21:16', host='gateway-01', service='api', severity='High', score=81, detector='Timeout frequency', unit='Time window', message='Repeated timeout messages in the API service.', actual='17 timeouts / min', typical='2 timeouts / min'),
    dict(id='LS-1039', time='14:16:02', host='compute-03', service='kernel', severity='Medium', score=62, detector='Event novelty', unit='Event', message='Previously unseen event pattern.', actual='New event template', typical='Known templates'),
    dict(id='LS-1038', time='14:09:55', host='storage-02', service='storage', severity='Medium', score=57, detector='Isolation Forest', unit='Time window', message='Warning count differs from the reference window.', actual='28 warnings / min', typical='8 warnings / min'),
    dict(id='LS-1037', time='13:58:30', host='gateway-01', service='api', severity='Low', score=34, detector='Event novelty', unit='Event', message='Low-priority event pattern to review.', actual='New event template', typical='Known templates'),
]


DETECTORS = ['Error burst', 'Isolation Forest', 'Timeout frequency', 'Event novelty']
PRIORITIES = {'Low': 1, 'Medium': 2, 'High': 3, 'Critical': 4}
RANGES = {'full': (830, 890), 'recent': (855, 890), 'early': (830, 855)}


def minute_of(event):
    """Fixture timestamps are on 2026-11-03 in UTC+07:00."""
    hours, minutes, _ = map(int, event['time'].split(':'))
    return hours * 60 + minutes


def clock(minute, timezone):
    display = minute - (420 if timezone == 'utc' else 0)
    return f'{display // 60:02d}:{display % 60:02d}'


def build_workspace(args):
    """Build one shared demo scope, timeline and optional table drilldown.

    This is presentation aggregation of synthetic fixtures, not anomaly detection.
    All time intervals are half-open. Display timezone never changes membership.
    """
    state = {key: args.get(key, default) for key, default in {
        'source': 'demo', 'range': 'full', 'timezone': 'local', 'host': 'all',
        'service': 'all', 'severity': 'all', 'detector': 'all', 'q': '',
        'selection': '',
    }.items()}
    for key, allowed, default in [
        ('source', {'demo', 'empty'}, 'demo'),
        ('range', set(RANGES), 'full'),
        ('timezone', {'local', 'utc'}, 'local'),
    ]:
        if state[key] not in allowed:
            state[key] = default
    state['q'] = state['q'].strip()[:200]
    start, end = RANGES[state['range']]
    source_events = ANOMALIES if state['source'] == 'demo' else []
    candidates = [e for e in source_events
                  if start <= minute_of(e) < end
                  and (state['severity'] == 'all' or e['severity'] == state['severity'])
                  and (state['detector'] == 'all' or e['detector'] == state['detector'])
                  and (not state['q'] or state['q'].lower() in
                       ' '.join(str(v) for v in e.values()).lower())]
    scope = [e for e in candidates
             if (state['host'] == 'all' or e['host'] == state['host'])
             and (state['service'] == 'all' or e['service'] == state['service'])]
    lanes, selected, focus_label = [], [], ''
    valid_selection = False
    for detector in DETECTORS:
        cells = []
        for lower in range(start, end, 5):
            upper = min(lower + 5, end)
            matches = [e for e in scope if e['detector'] == detector
                       and lower <= minute_of(e) < upper]
            key = f'{detector}@{lower}'
            is_selected = key == state['selection']
            if is_selected:
                valid_selection = True
                selected = matches
                focus_label = f"{detector} · {clock(lower, state['timezone'])}–{clock(upper, state['timezone'])}"
            priority = max((PRIORITIES[e['severity']] for e in matches), default=0)
            cells.append(dict(key=key, count=len(matches), priority=priority,
                              selected=is_selected,
                              label=f"{detector} · {clock(lower, state['timezone'])}–{clock(upper, state['timezone'])} · {len(matches)} signals"))
        lanes.append(dict(name=detector, cells=cells))
    if not valid_selection:
        state['selection'] = ''
    rows = selected if state['selection'] else scope
    events = []
    for event in rows:
        item = dict(event)
        item['display_time'] = clock(minute_of(event), state['timezone']) + ':' + event['time'][-2:]
        item['date'] = '03 Nov 2026'
        item['timezone'] = 'UTC' if state['timezone'] == 'utc' else 'UTC+07:00'
        item['raw_message'] = f"2026-11-03T{event['time']}+07:00 [DEMO] {event['host']} {event['service']}: {event['message']}"
        events.append(item)
    return dict(
        state=state, events=events, lanes=lanes, detectors=DETECTORS,
        scope_count=len(scope), result_count=len(events),
        priority_count=sum(e['severity'] in {'Critical', 'High'} for e in events),
        focus_label=focus_label, source_empty=not source_events,
        range_label=f"{clock(start, state['timezone'])}–{clock(end, state['timezone'])}",
        timezone_label='UTC' if state['timezone'] == 'utc' else 'UTC+07:00',
        ticks=[clock(value, state['timezone']) for value in range(start, end + 1, 5)],
        bin_count=(end - start) // 5,
        host_counts={name: sum(e['host'] == name for e in candidates)
                     for name in sorted({e['host'] for e in source_events})},
        service_counts={name: sum(e['service'] == name for e in candidates)
                        for name in sorted({e['service'] for e in source_events})},
    )
