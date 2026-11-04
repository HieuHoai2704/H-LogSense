# Investigation workspace v2

Implemented: 2026-11-03. This is a working UI prototype using synthetic fixtures,
not ingestion, real anomaly detection or an enterprise-readiness claim.

## Wireframe and component responsibilities

```text
Investigation | Source | Demo period | Timezone | Search | Apply | Hide filters | Export
One DEMO disclosure
Signals in scope                       Priority | Detector | Clear all
Active filter chips
Context facets | Anomaly timeline: count per detector / five-minute interval
               | Events: scope or selected detector/time slice
               | Selected event -> evidence panel docked on the right
```

The hierarchy adapts Elastic-style anomaly lanes, field/facet exploration, and
in-place evidence inspection without reproducing a vendor layout. Visible project
branding remains removed at the user's request.

## Scope and selection contract

`app/demo.py:build_workspace()` builds one synthetic source/time/query scope,
host/service facets, a timeline and the table's optional drilldown. Flask renders
the same view for a full GET and an internal HTML-fragment response. JavaScript
updates presentation, browser history, evidence inspection and export only.

- Sources: a six-record synthetic fixture and an intentionally empty demo fixture.
  The downloaded BGL/HDFS/etc. archives are not selectable imported datasets.
- Fixture date: 2026-11-03, timestamps interpreted as UTC+07:00.
- Full period: 13:50–14:50; earlier segment: 13:50–14:15; later: 14:15–14:50.
  These are fixed demo intervals, not live relative-time controls.
- Display timezone: UTC+07:00 or UTC; changing it does not change membership.
- Global filters: source, period, host, service, priority, detector and search.
  Combined groups use AND; one host and one service can be selected at a time.
- Bins are half-open five-minute intervals. Cells show counts and the highest
  priority, not maximum raw model score or calibrated probability.
- Timeline retains the global scope when an occupied cell is selected. The table
  narrows to that detector/bin and labels the selection explicitly.
- Selecting the same cell again, or clearing the selection banner, restores the
  scoped table. Global filter changes clear drilldown; timezone changes preserve it.
- Facet counts respect time/query/priority/detector before host/service selection;
  that denominator is disclosed in the facet panel.
- Internal partial responses use the same `/` GET with `X-Workspace-Fragment: 1`.
  This is browser rendering support, not the planned versioned public REST API.

## Detail choice

Use a **docked right panel** on desktop. It keeps the chart and table usable,
highlights the inspected row and exposes detector/unit, timestamp, ranking score,
observed/reference values and a synthetic raw message. Model/rule version is
explicitly unavailable because no detector has run.

On mobile, the panel becomes a full-width modal dialog; background is inert.
Escape and close restore the triggering control when available. Closing does not
clear filters or the timeline selection. No module navigation or separate detail
page is introduced.

## States

- Loading: retained results are marked busy; competing requests are aborted and
  stale responses cannot overwrite the latest request.
- Failure: keep previous results, show an error, allow retry.
- Empty source: explain that the source itself contains no records.
- No matches: explain that the current filters/selection have no results.
- Selected: outline the timeline cell, label the slice and highlight inspected row.
- CSV: export exactly the current table records, including display timezone.

The UI uses a few example detector names, priorities and scores; none proves a
real incident. All values and raw messages remain synthetic.

## Verification evidence

- `python -m unittest discover -s tests -v`: **8 tests passed**. Covers shared scope,
  disjoint bins, time boundaries, priority aggregation, timezone consistency,
  empty-source distinction, escaped search and full/fragment parity.
- Real Edge checks passed: scope selection, table narrowing, selected CSV, host /
  priority / source / time / search, UTC display, drawer/Escape, error/retry,
  mobile context and modal focus. No JavaScript exceptions were observed.
- At 1366x768, the beginning of the Events panel is visible with the timeline.
- The four text-on-active-cell color combinations were calculated above 4.5:1.
  This is not a full accessibility audit or conformance claim.

Screenshots are retained locally in `.local/workspace-v2-*.png`; no deployment or
GitHub push was performed. MySQL, upload, persisted analysis and ML remain pending.
