# Evidence Drawer — implementation and UX contract

Date: 2026-11-03. Status: **Implemented and verified with synthetic fixtures**.
This extends the Investigation V2 workspace; it does not connect a real log store,
execute detection, add SQLAlchemy models or establish production authorization.

## 1. Audit: what data actually exists

The existing drawer already opened without navigation, requested selected-record
details, supported Close/Escape and preserved timeline selection. Its payload was
a flat fixture record with a small same-host related list. It had no previous/next
scope navigation, separate raw provenance, context paging, raw controls, detector
configuration contract, evidence export, source read policy or redaction utility.

The source still contains six presentation anomalies in `app/demo.py`; all four
selectable sources are explicitly synthetic lifecycle examples. Downloaded research
archives are not imported or analysed. No MySQL connection, SQLAlchemy model,
raw-event table, parser job, model/rule execution, identity provider or user ACL
was present. Git status still reports **not a git repository**. Pre-drawer source
copies were retained in `.local/before-evidence-drawer-20261103-232414/`.

| Field | Actual availability | UI treatment |
|---|---|---|
| ID, timestamp, host/service, priority, detector label, unit | Existing fixture | Show selected record, with DEMO disclosure |
| Signal statement, illustrative score | Existing fixture | Observed signal text; no generated root cause or probability |
| Observed/reference | Existing fixture strings | Label synthetic; reference is never substituted for threshold |
| Raw text | Existing synthetic presentation text; tests may supply explicit raw fixture text | Label synthetic; no claim that it is an imported original log |
| Raw timestamp / adapted UTC timestamp | Fixture time / adapter conversion | Keep distinct; `parsing_status=not_run` |
| Parsed attributes | Fixture fields; explicit optional test attributes | Label fixture-only, not parser output |
| Source file/line, original raw log | Not supplied | Explicit null/Unavailable |
| Rule ID/version, model/version/run, thresholds, observation window | Not supplied by current fixtures | Explicit null/Unavailable; support supplied fields in contract/tests |
| Feature schema/evidence, native score direction, explanation method | Not supplied | Explanation unavailable; no feature importance or score calibration invented |
| Related records | Other anomaly fixtures from same authorized source | Explain relationship and context; surrounding original raw logs unavailable |
| Session/block, actual detection window | Not supplied | Relationship option disabled; API rejects unsupported relationship |

## 2. Final UX specification

The main Investigation hierarchy is unchanged. The drawer is 480px on the right
at desktop widths, a modal overlay below 1520px and a nonmodal split region on
wider screens. Mobile uses the full viewport. The main workspace is never routed
to another page to inspect a record.

**A — Header:** sticky Close toolbar; sticky current result/selection interval;
Previous/Next anomaly; ID, text priority, detection timestamp, host, service,
detector, unit, source and model-run availability. Previous means the next newer
anomaly, Next the next older anomaly in the complete current result scope, across
table pages. Timeline selection and all global filters are included. A related
record outside that scope has navigation disabled and an explicit explanation.

**B — Detected signal:** use the fixture's supplied signal statement. Observed
signal is separate from hypotheses; root cause remains null. No generated analysis.

**C — Raw log:** collapsible synthetic raw text, Copy visible log, Wrap lines,
keyboard-focusable scroll container, safe matching-term highlights and bounded
previous/next chunks. Provenance and parsed fields are expandable. Raw/parsed
timestamps, source file/line availability, event reference and parsing status are
explicit. Policy details live in provenance rather than dominating the main view.

**D — Detection evidence:** show observed/reference separately. Rule views expose
rule ID/version, threshold and observation-window availability. ML views expose
method, model/version, feature schema, score, score direction, threshold, unit
and available feature evidence. Event novelty's family is unknown rather than
inventing a rule or ML implementation. Missing explanation reads `Explanation
unavailable`. Reference statistics are not thresholds. Native Isolation Forest
direction and calibration are unknown; the fixture ranking is not probability.

**E — Related records:** choose same host, same service, before, after or explicit
context interval; context is configurable from ±1 to ±60 minutes. Page size is
1/5/10/20 in the UI, at most 50 via API. Every row gives ID/time/entity and why it
matches. The current source is authoritative; global result filters do not narrow
context. This is labelled so an investigator can distinguish related context from
the result scope. Session/block and detection-window relationships require actual
fields and remain unavailable for normal fixtures.

**F — Actions:** Filter by host, Filter by service, Focus context range, View raw
event, Copy anomaly reference and Export evidence JSON are functional. Filter
actions clear timeline selection but preserve other global dimensions. Focus uses
the explicitly displayed context interval, not an invented detection window.
Unavailable host/service actions are hidden. No alert/assignment/note/status
buttons are added without their persistence services.

### Interaction and state rules

- Open preserves global filters, URL and timeline interval. A panel-local sticky
  scope strip keeps the selected interval readable while scrolling evidence.
- Close restores original result focus and document scroll when possible; if the
  trigger was removed, focus falls back to the selected row or Results heading.
- Escape closes the panel. Compact modal mode makes the workspace inert and
  loops focus through enabled controls; wide split mode allows workspace access.
- Different records, raw chunks and related queries have separate request
  cancellation/sequence guards. Old responses cannot replace the newer record.
- Loading hides the old record's evidence; errors expose a local Retry. A failed
  context change clears old related rows instead of labelling them with new
  filters. Raw errors have a dedicated Retry raw log action.
- Export is disabled until the evidence, raw page and related page are ready.
  Failure never claims export/copy success. Clipboard failure is reported.
- Search terms are highlighted by creating text nodes and `mark` elements with
  `textContent`, never by interpolating log content into HTML or a regex.
- Original main-table page is retained while navigating records in the drawer.
  Header identity remains authoritative if the record is on another table page.

## 3. API and data contract

All endpoints share the source read policy and revision check:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/anomalies/{id}/evidence` | Selected metadata, provenance, parsed fields, detector evidence, initial raw/related pages, availability and result-scope navigation |
| `GET /api/v1/anomalies/{id}/evidence/raw` | One redacted text chunk; `raw_offset`, `raw_limit` |
| `GET /api/v1/anomalies/{id}/related` | One bounded relationship page |
| `GET /api/v1/anomalies/{id}/evidence/export` | JSON attachment containing the current evidence pages, explicit omissions and export-scope metadata |

Response sections: `schema_version`, `mode`, `revision`, `anomaly`, `summary`,
`raw_event.page`, `raw_event.provenance`, `parsed_fields`, `detector_evidence`,
`related_events`, `navigation`, `availability`. Missing values use JSON null,
not zero, guessed identifiers or convincing explanation text.

The existing `/anomalies/{id}` endpoint is retained for compatibility. The active
drawer uses `/evidence`. Main workspace filters and optional selection boundaries
are passed to calculate Previous/Next; they do not grant access to a source.

Related parameters: `relation`, `context_seconds` (1–3600), `context_limit`
(1–50), `context_cursor`. Time intervals are UTC `[start, end)`. Before excludes
the anchor timestamp and orders nearest-first; after excludes the anchor timestamp
and orders ascending. Other modes order chronologically. The anchor is excluded.

Related keyset cursors are signed, expire after 15 minutes and bind source, anchor,
revision, relationship, interval and page size. Tampering/reusing a cursor under
another scope returns 400. A server restart invalidates these demo cursors; the UI
can retry from the first page. No untrusted cursor SQL or filesystem path exists.

Raw chunks default to 2048 characters, maximum 8192. Redaction occurs before
slicing, including tokens spanning chunk boundaries. JSON attribute/feature
previews are capped at 8192 characters each with explicit truncation metadata.
Raw export includes the CURRENT chunk and related page, not an undisclosed partial
full-log export. `availability` records omissions, truncation and original-log
unavailability. Large full-evidence export jobs are not implemented.

## 4. Security and backend work

- `app/access.py` authorizes each source read before page/API access. Only the
  configured synthetic source allowlist is public. Disabling `DEMO_READ_ENABLED`
  denies all data views; removing a source from `PUBLIC_DEMO_SOURCES` denies its
  metadata, evidence, related, raw and export routes. Unknown/private sources are
  not connected or exposed. IDs are validated fixture references, never filenames.
- The default configuration intentionally permits public demo data. This is NOT
  user authentication or a production ACL. Real source integration remains blocked
  until an identity provider and per-user/source/anomaly permissions exist.
- JSON payloads and compatibility result/CSV surfaces use a shared redaction
  utility. It masks known credential assignments, authorization/cookie headers,
  bearer/JWT tokens, private keys, URL credentials and email patterns. Nested
  sensitive keys are masked. HTML is retained as inert text for investigation.
- This policy is heuristic, not exhaustive PII/DLP protection. Names, all identifier
  formats and arbitrary sensitive business content cannot be reliably inferred.
  Production needs source-specific classification/redaction before ingest/storage
  and an authorized raw-log repository. Do not connect private data under demo policy.
- Evidence responses use `Cache-Control: no-store`. Export serializes redacted
  payloads, including redacted query metadata. No endpoint reads a client file path.

The synthetic repository iterator scans the six fixture records. Related selection
uses a bounded heap of `limit+1`; it does not materialize every context record.
This is not evidence of SQL scalability: a real MySQL/SQLAlchemy repository must
apply source/ACL, relationship, UTC bounds, ordering and keyset cursor in SQL, with
appropriate indexes, EXPLAIN, revision snapshots and measured workloads.

## 5. Files and verification

New application files: `app/services/evidence.py`, `app/services/redaction.py`,
`app/access.py`, `app/static/js/evidence.js`.
Updated: `app/__init__.py`, `app/api/anomalies.py`,
`app/services/investigation.py`, `app/templates/dashboard.html`,
`app/static/js/dashboard.js`, `app/static/css/console.css`, `config.py`.
No new frontend framework or backend service was introduced.

Tests/QA: `tests/test_evidence.py`, `scripts/qa_evidence_drawer.py`; the existing
Investigation browser script was updated for the new evidence endpoint and complete
focus loop. Original fixture tests are retained.

Executed verification:

- **50 unit/API/integration tests passed**, including identity, source isolation,
  configured access denial, versions, unavailable evidence, malformed raw text,
  UTC selection/navigation, signed cursor paging, bounded large fields, redaction
  before chunk boundaries, HTML strings, exports and earlier timeline/filter scope.
- **13 Evidence browser scenario groups passed**, no application JavaScript errors.
- **21 Investigation browser regression groups passed**, no application JavaScript errors.
- Browser widths: 1920, 1440, 1366, 1024 and 390. Native Windows clipboard was NOT
  changed: browser QA uses a clipboard adapter to test copied payload and feedback.
- No claim of full screen-reader conformance, production pen test, MySQL query
  verification or large-data benchmarking. Current data remains synthetic.

Commands:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/qa_evidence_drawer.py
.\.venv\Scripts\python.exe scripts/qa_investigation_v2.py
```

Artifacts: [Evidence browser report](ui/evidence-drawer/browser-report.json),
[1440px](ui/evidence-drawer/evidence-1440.png),
[1366px](ui/evidence-drawer/evidence-1366.png),
[selected timeline context](ui/evidence-drawer/evidence-selected-1440.png),
[ML evidence availability](ui/evidence-drawer/evidence-ml-details.png),
[related records](ui/evidence-drawer/evidence-related.png),
[safe raw-log rendering](ui/evidence-drawer/evidence-safe-raw.png).

The implementation meets the investigation flow for ACTUALLY SUPPLIED fixture
evidence. Original logs, executed detector evidence and real-data authorization
remain explicit backend limitations, not completed enterprise capabilities.
