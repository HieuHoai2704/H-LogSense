# Adaptive Anomaly Timeline V2 — UI/UX specification

Historical proposal: the subsequent implementation is documented in
`../INVESTIGATION_V2_IMPLEMENTATION.md`. Status and audit statements below refer
to the design-stage snapshot, not the application after that implementation.

Status: **PROPOSED — awaiting design approval**  
Audit date: 2026-11-03. Stack: Flask / Jinja2 / vanilla JavaScript.  
Scope: audit and design artifacts only. No production implementation in this task.

## 1. Evidence-based audit

### Sources inspected

- `app/templates/dashboard.html`: toolbar, form, disclosure, partial mount, evidence drawer.
- `app/templates/partials/workspace.html`: context facets, timeline, selection banner, table.
- `app/static/css/console.css`: current overrides and responsive breakpoints.
- `app/static/css/main.css`: inherited stylesheet, retained; future changes must check cascade.
- `app/static/js/dashboard.js`: filtering, requests, history, drawer, CSV.
- `app/__init__.py`: Flask factory and single workspace route.
- `app/demo.py`: six synthetic records, scope and bin construction.
- `tests/test_workspace.py`: eight unit/integration checks.
- Existing `.local/workspace-v2-laptop.png`: visual baseline, not a new browser measurement.

`git status --short` reports **not a git repository**. Uncommitted status cannot be
established. Existing application files must remain untouched during this design task.
`python -m unittest discover -s tests -q`: **8 passed, 0 failed, 0.045s** in this audit.
This does not test the proposed UI, browser accessibility, MySQL or large datasets.

### Implemented versus proposed

| Area | Verified implementation | Actual limitation / design implication |
|---|---|---|
| Workspace | One page; no multi-page navigation; visible product wordmark removed | Preserve the user's requested minimal header; do not restore a logo block |
| Global controls | Demo/empty source, three fixed ranges, local/UTC, text search, Apply | Not arbitrary sources, custom timestamps or IANA timezone support |
| Scope | Shared `build_workspace()` filters; AND between groups; single value per group | Multi-select OR is proposed, not implemented |
| Filter timing | Select changes immediately request results; search requires Apply | Mixed behavior needs explicit draft/applied feedback |
| Context | Host and service links; hide/show context | Facet counts are before host/service filtering; must label count scope |
| Timeline | Server-generated 5-minute bins over 60/35/25-minute fixture ranges | 12/7/5 bins; not width-aware or adaptive |
| Aggregation | Done in Python on backend | Repeated scope scans per detector/bin; no SQL aggregation or scale evidence |
| Cell priority | Highest ordinal priority; occupied cell shows count | No severity breakdown in tooltip, no volume mode or coverage metadata |
| Drilldown | Cell link adds detector/bin selection; table narrows; clear preserves global filters | Only occupied cells are interactive; no brush or keyboard grid navigation |
| Requests | Fetches escaped Jinja partial; AbortController and sequence guard | Good foundation; response still includes all matching synthetic anomaly records |
| History | Query-string state and back/forward fetch | No explicit zoom history or timestamp-based selection contract |
| Evidence | Drawer is implemented, not merely planned; synthetic observed/reference/raw text | Model/rule version unavailable; no actual detector output or real evidence source |
| Drawer close | Keeps timeline selection, attempts focus/scroll restoration | Mobile Tab handler currently focuses only Close; must change if controls grow |
| CSV | Browser exports the current result array, with quoting and formula guard | Works for six demo rows; no server streaming, pagination or large-export strategy |
| Loading/error | Busy state; previous content retained; retry | No explicit applied-scope label on stale content, so new form/old results can be confused |
| Empty | Empty source differs from no filter matches | No distinction between complete zero, coverage missing, unknown or partial |
| Persistence | No database model, SQLAlchemy, migrations, authentication or timeline REST API | MySQL is a target architecture, not current infrastructure |
| Text | Metadata often 10–11px; table 12px; message 13px | Readability risk on laptops; actual comprehension/contrast not fully measured |

### Prioritized problems

Priorities are implementation order and risk, not a claim of production incidents.

| Priority | Evidence / problem | Impact | Proposed change | Acceptance criterion |
|---|---|---|---|---|
| P0 | No coverage metadata; empty cells share one neutral style | Absence of evidence could look like monitored normality | Separate complete-zero, missing, partial and unknown; explicit DEMO disclosure | With missing/unknown coverage, no cell or summary states that the source is healthy |
| P0 | New controls can differ from retained results after failed fetch | Wrong investigation/export scope | Track draft, pending and applied scopes; label retained results; atomic response commit | Request failure preserves old results AND their scope label; export cannot silently use draft values |
| P0 | Fixed minute-of-day contract; no real timestamp API/DB | Adaptive UI would imply unavailable capability | Define UTC ranges and backend dependencies before enabling zoom/custom ranges | Each successful zoom returns new backend bins; no pixel-only zoom or claimed MySQL support |
| P1 | Tiny metadata, weak hierarchy for priority and result selection | Slow reading and easy loss of context | 13px minimum meaningful metadata; stronger priority labels and selected-row marker | Manual review at 1366px and 200% text zoom; no hidden required content |
| P1 | No overall row, volume mode or hover breakdown | Cannot separate how serious from how frequent | Overall strip + detector rows; exclusive Severity/Volume toggle | Mode labels and legends change together; counts match a common scope |
| P1 | No brush/zoom, arbitrary range, detector sorting or grouping | Investigation limited to fixed fixture window | Staged range selection and backend-backed zoom; bounded row viewport | Mouse and keyboard can select the same interval; filters survive zoom |
| P1 | No pagination; all result records included | Does not generalize to large sources | Aggregate timeline and paged results; separate evidence request and export | Browser never needs every raw log or every anomaly to render the timeline |
| P1 | Drawer subtracts 380px from current workspace | Timeline/table may become cramped on laptops | Wide split only when both panes remain readable; otherwise local overlay | 1024/1366/1440/1920 states preserve readable chart and recover focus |
| P2 | Context counts precede both entity filters | Counts can surprise users | Disjunctive facet counts with explanation and active checkboxes | Labels and tests agree on which filters each count excludes |
| P2 | Controls spread across header, scopebar and timeline | More scanning and unclear reset meanings | One filter owner, separate display controls, explicit Clear selection / Reset zoom / Clear filters | A reset never clears unrelated state without its label saying so |

### Keep / simplify / remove / defer

| Decision | Elements | Reason |
|---|---|---|
| Keep | Single workspace; white surface; teal primary action; DEMO notice; URL history; abort protection; linked table; evidence drawer | Working investigation foundation |
| Simplify | Counts to one scope sentence; global controls to two deliberate rows; context to a disclosure; detector controls to one searchable picker | Less scanning and no duplicated host or detector filters |
| Remove from primary table | Detection-unit sublabel and standalone numeric score column | Unit and score need detector/version context; retain them in evidence and optional columns |
| Remove | Redundant helper prose, duplicate reset controls, ambiguous generic Clear all | Give each action one owner and specific meaning |
| Do not add | Chatbot, confidence percentage, decorative AI badges, gradient cards, sidebar navigation, persistent brand block | AI credibility comes from inspectable detection output and provenance |
| Defer | Dark theme, Compare View, model tuning, upload configuration, saved views, export jobs, real-time streaming | Not needed to validate timeline investigation; later features open inline/panel |

## 2. Desktop wireframe and reading order

See `timeline-v2-desktop.svg/png` (1440px), `timeline-v2-selection.svg/png`
and `timeline-v2-evidence.svg/png`.
These are static reviewable wireframes; controls are not functional.

1. **Investigation + DEMO context**: concise title, disclosure always visible.
2. **Scope controls**: source, range, timezone; search, entity picker, priority,
   detector, Apply and Clear filters. Active chips appear immediately below.
3. **Activity**: one count sentence, then Overall, then grouped detector rows.
   No KPI card grid. Timeline display settings are local to this section.
4. **Selection strip**: exact selected interval and optional detector, result
   count, Clear selection and Zoom to selection. It is the bridge to the table.
5. **Results**: default newest-first, meaningful priority label, signal and entity.
6. **Evidence**: inspect a result without navigating away or losing timeline scope.

Identity comes from the investigation ribbon, aligned time gutters, restrained
teal actions, priority typography and a distinct blue selection bracket. No
reference product's complete arrangement, branding or color system is copied.

### Proposed layout budgets (not measured usability results)

| Viewport | Workspace | Context | Timeline | Evidence |
|---|---|---|---|---|
| 1920 | Fluid, max 1888px, 24px gutters where possible | Closed by default; 208px inline option | 8–12 rows visible, bounded internal vertical scroll | 400–440px nonmodal split if workspace stays >=1000px |
| 1440 | 24px gutters, 1392px content | One entity picker panel, no permanent left rail | 12 fixture bins in wireframe; actual count adaptive | 420px modal overlay; workspace geometry retained |
| 1366 | 24px gutters; controls wrap by semantic group | Same picker, active values as chips | Sticky detector labels; no shrinking below min cell target | Modal side overlay, no margin that crushes chart |
| 1024 | 20px gutters; two control rows | Same panel, not a second host dropdown | Default 8 visible detector rows; chart can scroll horizontally | 420px modal side overlay, keyboard focus contained |

Split evidence is allowed only if measured remaining workspace >=1000px. On
narrower viewports, overlay evidence is a dialog: background inert, focus trap,
Escape and Close restore the original row and scroll. At widths below 800px,
use a full-width dialog and controlled chart/table scroll, without requiring a
phone-sized heatmap. The four requested widths still need browser testing after implementation.

## 3. Compact viewport wireframe

See `timeline-v2-compact.svg/png` (1024px).

- Row 1: source, time range, timezone. Row 2: search, entity, priority, detector,
  Apply. Clear filters is a named text action below. No overflowed header.
- Chart navigation and view mode remain available; less-used range controls
  move into a Time range popover, never disappear without an alternative.
- Detector labels stay at least 176px. Bin hit area stays >=24px wide and 32px
  high; if the selected resolution needs more space, scroll the plot only.
- Table keeps Time, Priority, Signal and Entity. Detector and score are available
  in the evidence panel or optional columns; this does not change query scope.
- With many rows, show `Showing 8 of N detectors` and accessible row paging.
  Do not shrink rows. Overall always includes ALL matched detectors.

## 4. Component hierarchy

```text
InvestigationWorkspace
  ScopeForm (draft state)
    SourcePicker / TimeRangePicker / TimezonePicker
    Search / EntityFilterPanel / PriorityPicker / DetectorPicker
    Apply / ClearFilters / AppliedFilterChips
  DemoDisclosure
  RequestStatus (pending/applied/stale)
  AdaptiveTimeline
    ScopeSummary
    TimelineToolbar
      SeverityVolumeSwitch / RowSort / Navigation / Resolution
    TimeAxis
    OverallLane
    DetectorViewport
      CollapsibleGroup / DetectorLane / TimelineCell
    FocusTooltip / AccessibleBinInspector
    CoverageAndModeLegend
    SelectionStrip / ZoomToSelection
  InvestigationResults
    ResultSummary / ScopedExport
    ResultsTable / Pagination
  EvidencePanel (wide region or compact dialog)
    AnomalyIdentity / Priority / DetectorAndVersion
    ScoreDefinition / DetectionUnit / SourceProvenance
    ObservedVsReference / EvidenceExcerpt / DataLimitations
```

Use Jinja partials for semantic structure and a small vanilla JavaScript state
module. A chart renderer may be Canvas/SVG after evaluation, with an HTML bin
inspector and keyboard model; rendering library selection does not replace accessibility.
Do not migrate the app to React/Vue for this feature.

### Table versus evidence

Default table: time + ID, text priority, signal, host/service, detector at wide
widths, inspect action. Use a 56px minimum row with a two-line signal allowance.
Truncate long content only with full text available in an accessible inspection
route. Scores are optional, labelled `Detector score`, never percentages; sort
scores only within a comparable detector/model version. Priority is a distinct
ordinal field and is not inferred from the largest cross-detector raw score.

Evidence owns: full timestamp/offset, raw score and meaning, model/rule version,
unit and window, observed/reference, source/event references, excerpt and
coverage limitations. Unknown provenance or reference values read `Unavailable`,
not zero. Fixture text remains labelled synthetic. Never imply a root cause.

## 5. Visual tokens and encoding

Token values below are proposed. `VERIFICATION.md` records measured token-pair
contrast only; it is not an accessibility certification of the application.

| Token | Value / usage |
|---|---|
| `surface` / `surface-subtle` | `#FFFFFF` / `#F5F7F9` |
| `text-primary` / `text-secondary` | `#172F40` / `#526575` |
| `divider` | `#D6DFE6`; decorative separators only, not sole control boundary |
| `control-border` | `#718391`; meaningful field and interactive empty-cell boundaries |
| `action` | `#096C68` with white text; links underlined in prose |
| `selected` / `selected-bg` | `#164FBA` / `#EDF3FF` |
| `focus` | `#172F40`, 2px outline + 2px white gap; distinct from selection |
| Low | `#087F76`, white `L` and label `Low` |
| Medium | `#8B6700`, white `M` and label `Medium` |
| High | `#B84B16`, white `H` / triangle and label `High` |
| Critical | `#AE2442`, white `C` / diamond and label `Critical` |
| Zero | `#F0F3F6`, visible `0` in complete monitored bins |
| Missing | Neutral diagonal hatch + `!`; tooltip states known gap, no false severity |
| Unknown | Neutral `?`; completeness was not supplied or not known |
| Partial | Corner hatch + observed count + coverage label; not treated as complete-zero |
| Radius | 4px controls, 2px cells; no pill-card decoration |
| Spacing | 4 / 8 / 12 / 16 / 24 / 32px; default section gap 16px |
| Type | System sans; title 22/28 semibold; section 16/24 semibold; data 14/20; metadata 13/18 |
| Numbers/code | Tabular figures; timestamp and excerpt monospace at >=13px |
| Targets | Controls >=36px height; close/important touch action 40px; cells >=24x32px |

Selected cells retain their severity/volume fill with a blue 2px outer bracket,
white gap and visible `Selected` strip; focus uses a separate dark outline.
Selected result row uses pale blue, 3px blue leading bar and `Selected` text in
its inspect button. Hover is neutral and must not look selected.

**Severity View:** categorical fill = maximum ordinal priority among unique
anomalies anchored in the bin. Label `C/H/M/L`; count is a separate smaller
number only if space permits, always available in inspector/tooltip. Color
intensity NEVER encodes volume here. Overall uses the same rule across detectors.

**Volume View:** categorical priority colors disappear from cells. Teal sequence
`#DCEFEB`, `#9CCFC5`, `#367D72`, `#075E55` represents exact anomaly-count buckets.
Use `t = log1p(count) / log1p(scope_max_count)` for intensity quartiles; response
or renderer supplies explicit count thresholds in the legend. Zero is separate.
If scope max is 0, no scale; if max is 1, use one nonzero class. Same scale for
Overall and detector lanes, derived across the entire current scoped aggregate,
not just visible rows. The legend states `Relative to this time range`.
Density per second is deferred: do not mix counts and rates in partial bins.
Switching view changes rendering only; filters and table membership do not change.

Fixture wireframes show known counts within an explicitly bounded synthetic
fixture, not monitoring completeness. The state sheet separately demonstrates
coverage styles with constructed examples; it does not claim real missing data.

## 6. State, scope and interaction specification

### Single source of truth

```text
draftScope = source, startUTC, endUTC, displayTimezone,
             hosts[], services[], priorities[], detectors[], search
appliedScope = last successfully committed canonical scope
pendingScope = immutable snapshot submitted by current request
selection = null | { startUTC, endUTC, detectorIds[] }
zoomHistory = stack of previous applied time ranges (UTC)
initialRange = range selected outside zoom (reset-zoom target)
display = severity|volume, rowSort, collapsedGroups, rowPage
evidence = null | anomalyId
dataRevision = backend snapshot/revision, or explicitly demo-only
```

Scope applies AND between groups, OR within a supported multi-select group.
`selection` further narrows the Events table and export. The main timeline and
scope summary show global scope without selection, so users keep context.
Selection summary/result count show the additional condition explicitly.
Every count is labelled `In scope` or `In selection`; do not mix scopes in a sentence.

Host/service live in ONE entity panel. Detector has ONE searchable picker;
group toggles in the plot only hide rows and never silently filter records.
Priority has ONE picker. Sort and view mode are presentation controls, not filters.
Facet counts exclude their OWN dimension but include the other active dimensions
and global time/search; they exclude timeline selection. OR candidates are
labelled as matching counts, not additive totals. This differs from the current
pre-both-entities facet counts and requires a deliberate implementation change.

Proposed filter timing preserves the existing immediate-select behavior: picker
and chip changes submit a scope snapshot immediately; search submits on Apply
or Enter. Any dirty search value is included if another control submits, and
pending scope is visible. Multi-select panels commit once on Done. Abort and
sequence-guard every scope update. Commit summary, timeline, table, chips and
URL only when all required results belong to the same scope and revision.
On failure, keep old applied results, mark `Previous results — update failed`,
retain draft inputs, and disable export until Retry or Revert restores alignment.

Global filter changes clear timeline selection, preserving current behavior;
display timezone, view mode and row sort do not. Timezone changes labels only.
Source changes reset range to that source's valid default, zoom history,
selection and evidence; retain entity/detector values only if valid for the new
source, and announce removals. Real-source default may be Last 24 hours; fixture
default remains its dated sample period, not a live relative window with no data.

`Clear filters` resets host/service/priority/detector/search AND selection, retaining
source, current time range and timezone. `Clear selection` changes only selection.
`Reset zoom` restores initialRange and clears selection, retaining other filters.
An explicit source/range picker change establishes a new initialRange.

### Proposed API dependencies (not currently implemented)

- **T** `GET /api/v1/anomalies/timeline`: global scope, chart width/resolution,
  grouping, detector row paging/sort. Returns overall and paged rows, counts,
  coverage, canonical range and revision. No full raw logs.
- **E** `GET /api/v1/anomalies`: same global scope + optional selection + cursor;
  returns page, total counts, applied-scope echo and revision.
- **D** `GET /api/v1/anomalies/{id}`: authorized detail and evidence provenance.
- **X** `GET /api/v1/anomalies/export`: identical table scope and pinned revision;
  streams CSV across pages subject to an explicit configured export limit.
- Until API migration, equivalent fixture operations can use the existing `/`
  partial route. Do not show unimplemented zoom controls as working controls.

T/E must commit together; reject incompatible revisions and offer refresh.
Authentication and source access are backend prerequisites for real data.
Fixture mode is explicitly public/demo; it does not prove authorization support.

### Exact interaction contract

`Applied` means the last successful scope and aggregate. `Cell` includes zero,
missing and unknown cells; inspecting one never asserts source health.

| Action | Before | State change | Visual feedback | Request | Error / recovery | Keyboard equivalent |
|---|---|---|---|---|---|---|
| Hover/focus cell | Applied grid | Transient focusedCell only | Tooltip with interval+offset, detector, count, C/H/M/L breakdown and coverage; no table change | None | If metadata unknown, display Unavailable, never 0 | Tab to grid; arrows move; focus exposes identical inspector; Escape dismisses tooltip |
| Click cell | No selection, or another cell selected | Set interval and detector; overall cell has no detector restriction; reset result cursor | Blue bracket, Selection strip, table busy then selected scope count | E only, existing aggregate supplies summary | Failed update keeps old selection/table pair and Retry; do not commit the new bracket early | Enter/Space selects focused cell; activating same selected cell clears |
| Clear cell/brush selection | Selection applied | Set selection=null, preserve global filters and zoom | Remove bracket/strip only after success; return to in-scope table | E | Keep prior selection/results with retry | Clear selection button; Escape while chart focused clears a selection after dismissing tooltip |
| Drag range | Applied range; possibly cell selected | Pointer-down candidate, pointer-up creates range selection across ALL detectors allowed by global filters, snapped to bin edges | Outline preview while dragging; then exact interval strip and busy table; does NOT auto-zoom | E on release, none per pointermove | Pointer cancel leaves prior state; request failure restores old selection | Shift+Arrow extends keyboard range; Enter commits; or enter exact start/end in Select range popover |
| Zoom in / Zoom to selection | Nonempty range selection, or no selection | Selected interval becomes global range, otherwise middle half; push old range; clear selection; maintain global filters | Pending range shown, new auto-resolution and bins after success; result cursor reset | T+E | Prior range, bins, URL and zoom stack remain on failure | Named Zoom in / Zoom to selection buttons; selected-range form; no drag required |
| Zoom out | Zoom history or custom range | Pop last zoom; if none double about center within source limits; clear selection | Recomputed range, resolution and counts | T+E | Keep prior state/history; show Retry | Named Zoom out button; disabled reason when source bounds reached |
| Reset zoom | Zoom differs from initialRange | Restore initialRange; clear selection, keep global filters | Reset zoom becomes disabled; original-range label and fresh bins | T+E | Keep zoom state on failure | Named Reset zoom button |
| Previous/next window | Applied range | Shift by exact UTC span, clamped within source boundaries; clear selection; new navigation entry | Pending dates, then updated axis and table | T+E | Keep prior range; boundary control disabled with reason | Named Previous/Next window buttons |
| Change detector | Applied scope | Submit detector set; clear selection and evidence; reset page | Chip/picker count, new rows and results; counts remain scoped | T+E | Retain applied results with stale-scope notice; Retry/Revert | Searchable checkbox picker; arrows/Space; Done commits |
| Change priority | Applied scope | Submit priority set; clear selection, reset page | Priority chips, summary and timeline/table update together | T+E | As above | Labelled picker and Done |
| Change host/service | Applied scope | Submit checked sets; clear selection and evidence; reset page | Entity button count + chips, refreshed facets/timeline/results | T+E | As above; no orphan selected entity hidden silently | Entity panel with labelled checkbox lists; Done/Cancel, Escape cancels |
| Apply text search | Draft search differs | Submit snapshot of all draft controls; clear selection, reset page | Pending query, busy regions, then applied query chip | T+E | Draft retained; results labelled old; Revert restores applied form | Enter in search or Apply button |
| Change source/range | Applied scope | Source/range rules above; clear selection; update initialRange | Dated source/range summary; disclosure never removed in demo | T+E | Old source/results remain labelled; no mixed source evidence | Labelled picker; custom start/end fields with validation |
| Change timezone | Applied scope | Display timezone only; UTC range/selection stable | Axis, table and detail labels update including offset and date | None if all timestamps present; otherwise refetch same UTC scope | Keep prior timezone if validation/refetch fails | Native/accessible timezone selector |
| Toggle Severity/Volume | Applied aggregates | Change display.mode only | Toggle pressed state, mapping, legend and tooltip units change; selection fill updated | None | If volume metadata absent, disable with explanation | Two labelled buttons, aria-pressed |
| Sort/collapse/page detectors | Applied plot | Presentation row state only | Row order/group disclosure/page count; Overall and table unchanged | T row page only if needed, same scope/revision | Keep old rows; lane-local Retry, no table corruption | Sort select; group buttons aria-expanded; Previous/Next rows |
| Open anomaly | Applied result row | Set evidenceId; preserve scope, selection and table position | Row marker; panel skeleton then identity/evidence; focus heading | D; fixture may already have fields | Inline evidence error/retry; leave table and selection usable after close | Inspect button or linked signal; no clickable-tr-only interaction |
| Close drawer | Evidence open | evidenceId=null only | Remove row marker; unchanged timeline/table; restore scroll | None | If opener no longer exists, focus result heading, announce context change | Escape or Close; wide region allows return to workspace; dialog traps focus |
| Export results | Fully applied, no pending/misaligned scope | Snapshot table scope, selection and revision; independent exporting flag | Exporting label, completion or error; disclose export count/limit | X across all result pages, not only current page | No fake success/truncated file; 409 offers Refresh; limit error explains narrowing | Export scoped CSV button; status announced; focus stays on button |
| Back/forward/reload | URL contains canonical scope+selection | Restore UTC scope, selection and view; cancel obsolete requests | Restored chips, axis, result scope; do not jump to top unnecessarily | T+E, D only for intentional deep-linked detail | Retry restores URL-requested state; invalid params labelled and canonicalized | Browser navigation; no bespoke shortcut required |

In a modal drawer, Escape closes that dialog first. In the chart, Escape dismisses
tooltip, then a second Escape clears selection. Editing custom ranges does not
apply invalid dates. Local time in a DST fold requires an explicit offset/choice;
nonexistent local time is rejected. Display axis includes date and offset across
day/DST boundaries. URL stores UTC instants, never ambiguous clock-only strings.

## 7. Request and data states

See `timeline-v2-states.svg/png`; these are example states, not live measurements.

| State | Timeline / results | Actions and assistive behavior |
|---|---|---|
| Initial loading | Neutral labelled skeleton, no colored fake activity or fake counts | `aria-busy`; short loading status; retain usable source controls |
| Updating | Existing applied result geometry retained; pending scope explicitly named | Cancel/sequence guard; export disabled; avoid dimming text below contrast target |
| Success | Summary, overview, lanes and results commit for same scope/revision | Announce count once, not every cell; preserve appropriate focus |
| Complete zero | `0 anomalies` only for explicitly complete scope; neutral `0` bins | Keep time navigation; no all-clear/healthy assertion about the whole system |
| No filter matches | Valid source but narrowed scope has no anomalies | Keep active chips; Clear selection or Clear filters, not an unexplained workspace reset |
| Empty source | Source contains no imported/fixture records | Distinct source-level message; choose source; future import opens panel |
| Missing | Known unavailable interval, diagonal hatch and `!` | Label cause if supplied; never report complete zero |
| Unknown | Completeness unavailable, `?` for empty cells | Explain unknown coverage; counts are observed counts only |
| Partial | Observed count with corner hatch and `Partial coverage` | Tooltip quantifies coverage only when backend supplies valid coverage metadata |
| No detector output | Logs may exist but no completed detector run | `No detection results`, distinct from zero anomalies; configure/run later in a panel |
| Request error | Keep previous applied data with explicit scope; error adjacent to affected area | Retry same snapshot or Revert draft; don't blank working evidence arbitrarily |
| Invalid range | Inline field error + summary; no request until valid | Associate error with fields; focus first invalid control |
| Forbidden/expired | No protected content in error response; appropriately remove inaccessible cached data | Sign-in/access action when real auth exists; never bypass with demo response |
| Revision changed | Don't mix new timeline with old table/export | Explain data changed; Refresh pinned scope, then request both regions |
| Demo | Persistent `DEMO — Synthetic events, scores and evidence. No model executed.` | Never hide disclosure because of zoom, selection, export or drawer |

## 8. Accessibility and responsive acceptance

Requirements, not claims of conformance:

- Normal meaningful text contrast target >=4.5:1; larger text >=3:1 under
  applicable WCAG definitions. Meaningful control boundaries and indicators
  need independent non-text contrast review. Test final computed colors, states
  and rendered labels, not just design tokens.
- Every priority has text/symbol. Missing, partial, unknown, selected and focus
  each have non-color indicators; tooltip alone is not sufficient.
- Use one roving tabindex for the chart, arrow navigation, Home/End to row
  limits, Ctrl+Home/End to grid limits; PageUp/PageDown for detector row pages.
  Only implement ARIA grid semantics with a matching keyboard model.
- Provide an HTML Bin inspector/table alternative including detector, exact
  start/end, priority distribution, count and coverage. Row/cell labels are
  available without mouse hover. Keep it usable if Canvas is used for paint.
- Tooltip accessible from focus, dismissible, hoverable and persistent while
  focus/hover remains; it contains no required action hidden from keyboard.
- Every control has a visible or programmatic name; controls >=36px high;
  proposed chart hit areas >=24x32px. Do not assume undersized targets pass
  without examining WCAG exceptions and adjacent spacing.
- Focus restore after DOM replacement must identify the same control/cell by
  stable ID. After invalidation, focus the result summary rather than body.
- When modal: full focus loop across ALL controls, background inert, Close and
  Escape; when split region: no modal trap and a clear Return to results action.
- Test 1920, 1440, 1366 and 1024 with/without detail and entity panels; long
  detector names, 100+ detectors, empty/error/loading states and long queries.
- At 200% text zoom, controls reflow and text is not clipped. Horizontal scrolling
  is confined to chart/table containers, with keyboard access and visible cues.
- Respect reduced motion. No animation required for understanding an update.
- Manual screen-reader test (NVDA + Edge on Windows) and keyboard-only test are
  required after implementation. None has been performed for this proposed UI.

Official references used for requirements:
[WCAG contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
[use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).

## 9. Backend contract and scale guardrails for the UI

These are dependency specifications, not added endpoints or measured capacity.

- Range and bin membership are `[startUTC, endUTC)`. Use full timestamps, not
  minutes of day. Resolution uses span, drawable width and a bounded bin budget.
- Initial proposal: 24px minimum hit width, preferred up to 80 bins, hard maximum
  120; choose nice durations and coarsen to fit. Fewer than 30 bins is valid for
  short spans/meaningful minimum resolution, as in the 12-bin fixture wireframe.
  Edge partial bins count toward the cap. Validate this budget in UX/performance tests.
- Anchor each unique anomaly once: event timestamp, or detection-unit start for
  interval anomalies. Overlap activity, event count and raw log count are different
  metrics and not silently substituted for anomaly count.
- Overview and detector totals use the same global filters. Each anomaly has one
  owning detector output; unrelated detector alerts about one underlying incident
  are separate outputs unless an explicit deduplication policy is introduced.
- Each bin returns start/end, unique count, priority breakdown, max priority,
  completeness and partial-edge flag. Row metadata includes stable detector ID,
  name, group, total, max priority and most recent timestamp for sorting.
- API also returns canonical scope/range, chosen resolution, overall bins,
  detector total and paging, source mode, revision and limitations.
- Fixture completeness is explicitly fixture-only. Real coverage requires import
  and detector-run metadata, not inference from zero raw rows. Late arrivals
  increment revision; refresh recomputes counts and coverage at the chosen scope.
- Default 12 detector rows (8 compact), optional up to 20; overall remains across
  all matched detectors. Start with explicit server row pages, not thousands of
  hidden DOM nodes. Search the single detector picker across all available IDs.
- Table default 50 results, maximum 100; cursor pagination. Detail loaded on
  demand. Server CSV uses same filters and selection and an explicit export cap.
- Width/height changes request a new aggregate only if bin budget changes; don't
  spam requests on every pixel of resize. Preserve selection as UTC interval if
  it spans newly recomputed bins; bracket its actual extent, not a wrong single cell.
- Benchmark synthetic 10K/100K/1M event workloads with documented anomaly density,
  4/100/1000 detectors, sparse/dense ranges and many hosts/services. Measure API
  p50/p95, query/aggregation time, payload, browser render time and memory, and
  exact count correctness. A p95 <2s is a target, not an achieved result.
- MySQL schema/index/EXPLAIN, authentication, SQLAlchemy integration and import
  invalidation must be designed and verified before real-source claims. No cache,
  partitioning or new storage engine is justified by this UI audit alone.

## 10. Change inventory, implementation tasks and approval boundary

### Existing files to modify AFTER approval

| File | Planned scope |
|---|---|
| `app/templates/dashboard.html` | Compact scope form, applied/draft status, entity picker entry, improved evidence semantics |
| `app/templates/partials/workspace.html` | Overview, detector groups, mode/zoom controls, selection bridge, paged results |
| `app/static/css/console.css` | Tokens, typography, selection/focus, coverage patterns and target breakpoints |
| `app/static/js/dashboard.js` | Canonical state, chart keyboard/brush, zoom/history, response transaction, evidence focus |
| `app/demo.py` | Fixture adapter to timestamps/coverage/aggregate contract, without representing fixture as ML output |
| `app/__init__.py` | Integrate API blueprints and preserve existing page/fragment behavior during migration |
| `tests/test_workspace.py` | Retain/regroup existing eight checks, add new contract/regression coverage |
| `requirements.txt` | Add packages only after renderer/backend architecture choice; not part of design task |
| `README.md` | Record implemented versus planned capabilities after actual implementation |

Potential NEW modules after architecture approval: `app/api/anomalies.py`,
`app/services/timeline.py`, `app/services/anomaly_scope.py`, fixture/repository
adapters, timeline partial, chart JS module and focused tests. Names are tentative;
do not invent an existing SQLAlchemy model or overwrite a user's module.

### Proposed execution sequence

| Step | Deliverable | Verification gate |
|---|---|---|
| 1 — Recommended | Approve design: scope hierarchy, desktop/compact layout, selected/detail states and mode semantics | Review five artifact sheets; resolve any requested design changes before app edits |
| 2 | Fixture timestamp contract and shared scope service; API schema and pure aggregation correctness first | Boundary, timezone/DST, empty/missing, priority, filter and count partition tests |
| 3 | Overview + Severity/Volume + accessible cell inspector in existing Jinja workspace | Old eight checks remain passing; mode changes never alter table membership |
| 4 | Brush, range form, zoom/history, synchronized selection, pagination and export | API/UI scope parity; stale responses cannot win; export matches full selected result set |
| 5 | Evidence responsive behavior; request/error/empty states and keyboard polish | 4 target widths, focus recovery, modal loop, screen reader and text-zoom review |
| 6 | MySQL integration/authorization and large-data benchmarks in a separately approved backend increment | SQL correctness, EXPLAIN, import revisions, access tests, measured benchmark report |

The previous broader Timeline V2 request requires backend implementation before
large-data completion. This UI task only specifies that dependency; it does not
replace it or certify it as done.

### Design approval checklist

- [ ] Approve compact two-row scope controls and no persistent context rail.
- [ ] Approve one Overall lane and grouped detector lanes, not a separate dashboard.
- [ ] Approve separate Severity and Volume mappings, zero/missing/unknown styles.
- [ ] Approve explicit selection then Zoom to selection, rather than automatic drag zoom.
- [ ] Approve score in evidence/optional column and priority as table primary cue.
- [ ] Approve overlay drawer at laptop widths, split only with >=1000px workspace.

**Stop here. No production UI or backend implementation is authorized by this
design deliverable. Wait for the user's design approval before the next step.**
