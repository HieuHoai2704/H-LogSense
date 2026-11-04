# Enterprise Investigation V2 — implementation report

Date: 2026-11-03. **Implemented and verified for synthetic fixtures only.**
This is not a production-readiness, real-ML, MySQL or large-data certification.

Subsequent Evidence Drawer increment: see `EVIDENCE_DRAWER.md` for current drawer
contracts, source read policy, redaction and verification. The earlier drawer
description below records the initial V2 increment; real login/ACL and database
limitations still apply.

## Initial audit and boundary

Before this increment, the application had one Flask `/` route, six synthetic
anomaly records, fixed five-minute bins, linked cell/table filtering, a drawer,
browser CSV export, fetch cancellation and URL history. Eight existing tests
passed. The adaptive overview, modes, brush, zoom and detector grouping in
`docs/ui/` were static wireframes, not working application components.

No SQLAlchemy extension/model, MySQL connection, ingestion service, REST data
blueprint, authenticated source access or model-run results were present.
`git status --short` reported that the folder is **not a Git repository**.
A local pre-change copy of affected original files and SHA256 manifest was
saved in `.local/before-investigation-v2-20261103-230603/`.

The authorized UI/API increment uses an explicitly synthetic repository adapter.
Real-source integration stops at that boundary because its required persistence,
ingestion, run coverage and access-control backend do not exist. No fake database
connection or invented detector evidence has been introduced.

## Final component specification

| Component | Implemented responsibility |
|---|---|
| Source/global scope | Four labelled synthetic lifecycle sources; fixed/relative-to-fixture/custom UTC ranges; display timezone; search; multi-value entity/priority/detector panels |
| Applied-filter chips | Remove individual values; retain unrelated dimensions and current time range |
| Coverage/query status | Source identity, fixture interval and last fixture record; explicit unavailable processing/ingestion/model/freshness fields; pending, success, failure and retained scope |
| Adaptive timeline | Backend-built UTC half-open bins; width-aware Auto resolution; Overall and grouped detector rows |
| Severity | Maximum ordinal priority, with L/M/H/C and count; score is not used to choose maximum priority |
| Volume | Separate teal count scale with labelled buckets; zero separate; same scope-wide scale for Overall and lanes |
| Cell inspector | Pointer hover and keyboard focus expose exact time/offset, count, severity distribution and coverage in persistent readable text |
| Timeline selection | Cell selects detector+interval; Overall/brush/exact-range form selects all globally allowed detectors within an interval |
| Navigation | Previous/next UTC window, zoom in/out, zoom to selection and reset to base range; fresh aggregation from backend |
| Detector controls | Searchable picker, maximum-priority/count/recent sort, group collapse, bounded 12-row server page contract |
| Results | Newest-first paginated anomaly summaries, scope-labelled counts, explicit empty state, inspect action |
| Evidence drawer | On-demand selected-record API; timestamp, entity, detector, version availability, score meaning, observed/reference, synthetic raw text, fixture fields and actual related fixture records |
| CSV | Server endpoint exports all matching results rather than only the table page, includes synthetic flag, quotes CSV and guards formula prefixes |

The main order remains scope → timeline → detector groups → results → contextual
evidence. No multi-page menu, framework migration, chatbot or decorative KPI grid.
The visible product wordmark remains removed as previously requested.

The context rail is consolidated into multi-select entity controls. Meaningful
metadata is 13px or larger, controls are generally 36px or larger, cells are
32px high with a minimum width of 24px. Local chart/table scrolling prevents
document overflow. This is a design implementation, not a WCAG certification.

## Shared filter and aggregation semantics

- Canonical scope: `source`, UTC `start_time/end_time`, `timezone`, repeated
  `host/service/severity/detector`, `q`, optional selection boundaries/detector,
  display mode, row sort/page, table page/limit and chart width.
- AND between categories; OR between repeated values in the same category.
- Facet counts exclude ONLY their own dimension, include every other global
  dimension and search/time, and exclude timeline selection. Counts are matching
  candidate counts, not additive category totals.
- Timeline and scope KPI counts use the global scope. Table and CSV add the
  explicit selection condition. Result counts name their scope.
- Every range is `[startUTC, endUTC)`, including partial edge bins. UTC epoch
  alignment; selected local timezone changes labels only. UTC day bins are elapsed
  24-hour intervals, not local calendar days. DST labels include explicit offsets.
- The default demo range ends at the dated sample timestamp, not the live clock.
  Custom inputs are explicitly UTC, avoiding ambiguous local-time entry.
- Auto uses nice durations, drawable width and a hard 120-bin limit. The demo's
  meaningful minimum is five minutes; short ranges can have fewer bins. Explicit
  API resolution finer than a minute or producing >120 bins is rejected.
- Each fixture anomaly is anchored at its supplied timestamp and counted once.
  `Time window` is a fixture unit label, not a supplied real interval. A future
  interval repository must provide an explicit unit start and deduplication key;
  this increment does not implement overlap-interval activity or raw-event counts.
- Fixture completeness is only completeness of an enumerated synthetic record
  set. Missing/partial lifecycle examples are explicitly constructed sources.
  No healthy or all-clear conclusion follows from zero anomalies.
- Raw log count, parsed event count, model/run, last processed event and ingestion
  freshness are unavailable. `last_event` means last fixture timestamp, not last
  successfully analysed log.

## REST and architecture

| Endpoint | Response / scope |
|---|---|
| `GET /` | Server-rendered Jinja workspace; fragment header retained for compatibility |
| `GET /api/v1/investigation` | Atomic canonical state, aggregate, facets, paged result summaries, coverage, revision and Jinja fragment |
| `GET /api/v1/anomalies/timeline` | Aggregated overview/detector bins and metadata; no result/evidence array |
| `GET /api/v1/anomalies` | Paged result summaries and total counts under the same scope |
| `GET /api/v1/anomalies/<id>?source=...` | Selected record and related same-host fixture records; no generated explanation |
| `GET /api/v1/anomalies/export` | CSV for table scope including selection, independent of page |

The service in `app/services/investigation.py` owns validation, fixture access,
filters, disjunctive facets, aggregation, paging and evidence adaptation. HTTP
handlers live in a Blueprint; `app/presentation.py` owns Jinja/link helpers.
The original fixture-only `app.demo.build_workspace()` remains for legacy tests;
active V2 routes use the new shared service.

API values are validated; malformed ranges, unknown filter values and unsupported
sources return structured 400 errors. Unknown selected records return 404.
Revision conflicts return 409, including export. APIs use `Cache-Control: no-store`.
The fixture revision is static because the fixture adapter is immutable.

The composite API atomically commits scope, overview, facets, table and count
updates. Detail is loaded separately; raw text is not preloaded in every result.
No entire raw log dataset is sent to the browser. Timeline payload is bounded by
bins and detector row pages; result pages are at most 100 rows. Export has an
explicit 50,000-anomaly limit; it never silently truncates.

## Reliability and interaction state

- Filter selects submit immediately; multi-select checkboxes commit on Done;
  search submits on Apply/Enter. Dirty fields are explicitly marked unapplied.
- AbortController plus request sequence guard prevents old scope responses from
  overwriting newer results. Identical pending requests are deduplicated.
- Newer unsubmitted field edits survive an older in-flight query commit.
- Query timeout is 15 seconds. Loading keeps old data legible and labels the
  previous scope. Failure/timeout retains old applied data with Retry/Revert.
- CSV is disabled while scope is pending or dirty. Export failures are reported;
  no successful download is claimed for an error response.
- Global scope changes clear timeline selection; timezone/mode/sort retain it.
  Clear selection preserves global filters. Clear filters preserves source/time.
- Brush creates a selection first. Zoom is explicit and requests new bins.
  Reset-zoom base boundaries are URL state, so they survive reload.
- Browser history restores canonical scope and selection. Invalid direct page
  queries display a dedicated error page with a safe return link.
- Detail has independent request cancellation and error/retry. Switching related
  records does not change global scope. Related records are labelled as possibly
  outside active filters. Unknown evidence remains unavailable.
- At laptop widths detail overlays the workspace without squeezing it; background
  is inert, the complete control list is trapped, Close/Escape restores focus.
  At >=1488px it becomes a nonmodal split region. Closing does not refetch data or
  clear selection; layout retains the main result context.
- Chart uses roving focus, arrows/Home/End, Enter/Space, Shift+Arrow range extension
  and Escape. A labelled exact UTC range form provides a non-drag alternative.

## Files changed

Existing application files modified:

- `app/__init__.py`
- `app/templates/dashboard.html`
- `app/templates/partials/workspace.html`
- `app/static/css/console.css`
- `app/static/js/dashboard.js`
- `requirements.txt` (adds `tzdata` for Windows IANA timezone support)

New application files:

- `app/api/__init__.py`, `app/api/anomalies.py`
- `app/services/__init__.py`, `app/services/investigation.py`
- `app/presentation.py`, `app/templates/query_error.html`

Tests/QA: `tests/test_investigation_v2.py`, `scripts/qa_investigation_v2.py`.
Documentation: this report, README/progress tracker, historical-design index notice
and actual screenshots/reports under `docs/ui/implementation-v2/`.
`app/demo.py`, `tests/test_workspace.py`, `config.py` and the old inherited
`main.css` were retained; `main.css` is no longer loaded by the new page.

## Verification

- Unit/API/integration command: `.venv/Scripts/python.exe -m unittest discover -s tests -q`.
- Browser command: `.venv/Scripts/python.exe scripts/qa_investigation_v2.py`.
  Playwright and locally installed Microsoft Edge are QA tools, not Flask runtime dependencies.
- See [generated browser report](ui/implementation-v2/browser-report.json) for the
  executed scenarios and their count. The script owns and shuts down its local server.
- Screenshots: [1440px](ui/implementation-v2/workspace-1440.png),
  [1366px](ui/implementation-v2/workspace-1366.png),
  [1024px](ui/implementation-v2/workspace-1024.png),
  [selection](ui/implementation-v2/workspace-selection.png),
  [evidence](ui/implementation-v2/workspace-evidence.png),
  [partial coverage](ui/implementation-v2/workspace-partial.png).
- Tested layout widths: 1920, 1440, 1366, 1024 and 390. Horizontal scrolling is
  local to chart/table; no document-level overflow in those tested normal states.
- Token contrast from the design review does not prove every implemented
  composite state meets accessibility criteria. No screen-reader certification,
  full 200% text-zoom audit, MySQL EXPLAIN or large-data benchmark is claimed.

## Remaining backend blockers and limitations

1. **MySQL/SQLAlchemy schema, migrations, connection and query repository are not
   implemented.** Real sources are deliberately unavailable. No SQLite substitute
   or mock SQL result is presented as MySQL. Need a backend increment and a test DB.
2. **Import/parsing and detection jobs are absent.** Downloaded BGL/HDFS archives
   remain research files, not selectable analysed datasets. Fixture scores and
   supporting text remain synthetic.
3. **Authentication/source authorization are absent.** APIs are demo-only; no
   protected production dataset should be connected before access controls exist.
4. **Large-data performance is unverified.** The in-memory fixture adapter does
   not replace SQL-side filtering/aggregation. Need measured 10K/100K/1M workloads,
   query plans, snapshot revisions and import invalidation before scale claims.
5. The renderer/contract bounds row pages, but the current catalog contains only
   four detectors. Very-many-detector behavior has not been browser-benchmarked.
6. CSV currently adapts a bounded in-memory fixture list then streams text; a
   real repository must stream an authorized, pinned SQL snapshot. Large async
   export jobs and ingestion revision recomputation are deferred.

All requested investigation flows are operational in DEMO mode. The real-data
enterprise acceptance gate remains open at the backend dependencies above.
