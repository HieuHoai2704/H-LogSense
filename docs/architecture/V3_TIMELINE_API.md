# Timeline V3 API specification

Status: proposed only. Product V3 does not mean API version 3.
Keep current `/api/v1/*` behavior until an approved migration. A new compact
contract is proposed at **`GET /api/v2/anomalies/timeline`**, because replacing
the current repeated-bin/HTML-oriented shape would be a breaking v1 change.

## Query scope

Required: `dataset_id`, explicit UTC `start_time`, `end_time`,
`analysis_snapshot_id` (or resolve-and-return current snapshot on initial query).
Optional: pinned `input_revision`, display `timezone`, `resolution=auto|seconds`,
`plot_width`, repeated `host_id/service_id/detector_id/priority`, `search`,
explicit `model_run_id` selection, `detector_sort`, `detector_cursor`, `row_limit`.

Source authorization is server-derived, never granted by request tenant/dataset
strings. Validate known values and caps. AND between groups, OR within group.
Literal search and entity-unit semantics are defined in the data/query proposal.
Timeline selection is not applied to the overview; results/export explicitly add
`selection_start/end/detector_ids`. Return canonical applied scope and its hash.

## Aggregation semantics

- `metric = unique_anomaly_outputs`, `assignment = anchor_start`.
- Event output anchor = event timestamp. Window/session output anchor = actual
  detection-unit start. Store detection/emission time separately; late emission
  does not move an anomaly into another event-time bin.
- Every selected output key `(run, unit, signal)` belongs to exactly one bin in
  `[start,end)` if its anchor belongs to that query. The snapshot prevents retry/
  reanalysis duplicates. Unique output count is not incident or parsed-event count.
- An interval beginning before the query and remaining active is excluded from
  anchor-start counts. If engineers need active/overlap counts, expose a separate
  named metric/endpoint; sums across bins for that metric may exceed unique count.
- Resolve bins in integer UTC microseconds: `floor(anchor_us / resolution_us)`.
  Clip the first/last bin to the requested boundaries; every bin has exact start
  and exclusive end plus a partial-edge flag. Day means 86400 UTC seconds in v2;
  local-calendar-day/DST grouping is not silently substituted.
- Severity maximum uses the highest ordinal priority among observed matched
  outputs; coverage may make it an incomplete observation. Volume uses count.
  Native scores remain typed by detector/version and are not compared here.

## Adaptive resolution

`budget = min(configured_max_bins=120, preferred_cap=80,
max(1, floor(plot_width / minimum_cell_width=24)))`.
Choose the smallest allowed nice duration whose ACTUAL aligned/clipped bin count
fits budget and whose precision is meaningful for this source. Query-cost limits
may choose a coarser result, with a reason returned. Reject explicit resolutions
that violate caps; never silently sample raw rows. Short ranges may produce fewer
than 30 bins. Benchmarks must validate the initial 24px/80/120 design choices.

Initial nice durations: 1m, 2m, 5m, 10m, 15m, 30m, 1h, 2h, 6h, 12h, 1d, 2d,
7d, bounded by source precision and approved maximum range. Layout resize only
requeries when budget changes materially. Selected intervals remain UTC ranges,
even when new bins no longer align exactly with selection edges.

## Response shape

Example is a **constructed contract example**, not a measured result. Counts are
decimal strings in v2 to preserve exact database integer values in JavaScript.
Time bins occur once; detector cell arrays align to them rather than repeating
dates/labels/full filter URLs per cell.

```json
{
  "schema_version": "2.0",
  "data_mode": "synthetic",
  "metric": "unique_anomaly_outputs",
  "assignment": "anchor_start",
  "scope": {
    "dataset_id": "example",
    "input_revision": "rev-example",
    "analysis_snapshot_id": "snapshot-example",
    "start_time": "2026-11-03T00:00:00Z",
    "end_time": "2026-11-03T02:00:00Z",
    "detector_ids": [], "host_ids": [], "service_ids": [],
    "priorities": [], "search": "", "hash": "canonical-scope-hash"
  },
  "resolution": {"seconds": 3600, "mode": "auto", "reason": "width_budget"},
  "bins": [
    {"start": "2026-11-03T00:00:00Z", "end": "2026-11-03T01:00:00Z", "partial_edge": false},
    {"start": "2026-11-03T01:00:00Z", "end": "2026-11-03T02:00:00Z", "partial_edge": false}
  ],
  "overall": {
    "count": ["2", "0"],
    "severity": {"low": ["0","0"], "medium": ["1","0"], "high": ["1","0"], "critical": ["0","0"]},
    "max_priority": [3, 0], "coverage": ["complete", "not_analyzed"]
  },
  "detector_page": {
    "total_detectors": 1, "row_limit": 12, "next_cursor": null,
    "rows": [{
      "detector_id": "logical-detector-example", "name": "Example rule",
      "family": "rule", "run_ids": ["run-example"],
      "count": ["2","0"],
      "severity": {"low": ["0","0"], "medium": ["1","0"], "high": ["1","0"], "critical": ["0","0"]},
      "max_priority": [3,0], "coverage": ["complete","not_analyzed"]
    }]
  },
  "counts": {"raw_lines": null, "parsed_events": null, "detection_units": null, "anomaly_outputs": "2"},
  "coverage": {"query_execution": "complete", "input": "complete", "analysis": "partial", "missing_intervals": [], "as_of": "2026-11-03T02:01:00Z"},
  "analysis_runs": [{"run_id": "run-example", "detector_id": "logical-detector-example", "version_id": "version-example"}],
  "semantics": {"range": "[start,end)", "deduplication": "snapshot-owned run/unit/signal", "timezone_affects_membership": false},
  "warnings": ["Analysis coverage is incomplete; observed zero does not establish absence of anomalies."]
}
```

Counts for other layers are null unless measured under a named applicable scope.
Never fill raw/parsed/unit totals from anomaly counts. Severity-array sums equal
bin observed anomaly count. Overall sum equals global-scope anomaly count for the
anchor metric; detector-page sums alone need not equal Overall. If multiple runs
are explicitly included, outputs are counted as distinct selected run outputs and
the UI discloses that choice; default snapshot avoids implicit version comparison.

## Response and query bounds

- B <=120; default 12 detector rows, max20; Overall across all selected detectors.
- Names/IDs/metadata bounded; do not duplicate full model/configuration or evidence.
- Initial target <=512 KiB uncompressed timeline JSON for the documented row/bin
  cap. Measure actual fixtures with long names and maximum filter arrays.
- Results default50/max100 with signed timestamp+ID cursors; no deep OFFSET scans.
- Evidence/raw/related endpoints stay on demand and authorized. No raw-event array
  or entire source file is included in the timeline.
- The composite workspace may orchestrate bounded queries in one snapshot; it
  should not return duplicate complete timeline data plus full per-cell HTML URLs.
- Query budget, rows examined, DB/serialization timings and payload size are
  observable internally; do not disclose SQL/plans/secrets to arbitrary clients.

## Consistency, errors and client behavior

400: invalid scope/range/resolution/cursor. 403: source access denied.
404: inaccessible/missing resource under a non-disclosing policy.
409: stale input/analysis/access-policy revision. 429: explicit query concurrency
budget. 503/504: query unavailable/timed out. A failed query never returns a partial
result labelled complete. Existing UI keeps labelled old data and disables scope-
mismatched export until Retry/Revert/Refresh resolves it.

Preserve existing AbortController and sequence guards, including drawer subqueries.
Use canonical UTC URL state; do not place secrets or raw log bodies in share URLs.
Group collapse/mode changes do not change membership. Closing evidence preserves
selection, result position and focus. Large-data support must not require a new
page/menu or another frontend framework.
