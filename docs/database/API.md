# API reference

All timestamps are ISO 8601 with an explicit UTC offset; output is UTC. Intervals
are `[start,end)`. JSON errors use `{ "error": { "code": "...", "message": "..." } }`.
Some validation/authorization responses omit optional message text. HTTP status:
400 invalid query, 401 invalid login, 403 role/dataset/CSRF denial, 404 unavailable
resource, 409 conflicting scope/job/state, 413 oversized request, 422 export cap,
429 login throttle, 503 database/auth configuration unavailable. API responses
are `Cache-Control: no-store`.

## Authentication and permissions

| Method/path | Contract |
|---|---|
| POST `/api/v1/auth/login` | JSON username/password, existing active account only. Returns HttpOnly SameSite=Strict session cookie and csrf_token. |
| GET `/api/v1/auth/me` | Current ID, role, granted dataset IDs and CSRF token. |
| POST `/api/v1/auth/logout` | Requires X-CSRF-Token; clears session. |

Every private read additionally requires a `user_datasets` grant. A global role
does not grant automatic access to every dataset. `viewer` reads; `analyst` can
queue/retry analyses, acknowledge/change investigation status and add notes;
`manager`/`admin` also create rules, assign other authorized investigators and
reopen a resolved incident. State changes require a session and CSRF token.
Password hashes use Werkzeug scrypt. Login is throttled in-process per source IP;
multi-worker/global throttling and account administration UI are not implemented.

An optional local bearer token plus explicit app dataset allow-list supports
read-only operator tools. It cannot mutate incidents or submit jobs. It is not a
substitute for user RBAC. No token/password is accepted in a URL or persisted by
frontend JavaScript. Configure `COOKIE_SECURE=1` only with HTTPS.

## Log Explorer

| Method/path | Contract |
|---|---|
| GET `/api/v1/logs/datasets` | At most 100 authorized datasets, data mode/revision and observed time bounds; these bounds are not coverage proof. |
| GET `/api/v1/logs` | dataset_id, start_time, end_time; optional repeated host/severity, literal q (<=200), sort=asc/desc, limit=1..100, scope_token, cursor. |
| GET `/api/v1/logs/timeline` | Same scope, optional bins=20..120. Returns server-aggregated parsed-event counts and explicit unknown time coverage. |
| GET `/api/v1/logs/{event_id}` | Same scope, raw_offset; redacted raw chunk, original timestamp, ground-truth category and source/line/byte provenance. |
| GET `/api/v1/logs/export` | Same scope, at most 100,000 events. Streamed CSV, redacted full message, formula prefixes escaped. |

Filters use AND across groups, OR within repeated hosts/levels. Severity here is
the **supplied log level**, not anomaly priority. Search is literal message
substring matching with LIKE wildcard escaping; it is case-sensitive under the
schema collation and does not claim a full-text index.

Page one pins the maximum event ID and input revision in a signed 30-minute
scope_token. Subsequent page/timeline/CSV requests must reuse it with the same
filters, order and page size. Append-only imports cannot enter that snapshot.
Cursors sign `(timestamp,id)` and the snapshot; altered/expired/cross-scope
cursors are rejected. Ordering ties use ID. The UI commits table and timeline
atomically after matching their counts and cancels superseded requests.

## Anomaly Center and evidence

Existing paths retain Demo Mode for `source=demo/empty/partial/unprocessed`.
Use `source=db-DATASET_ID` with authentication for persisted results:

- GET `/api/v1/investigation`: bounded table rows, facets, aggregated timeline and
  server-rendered existing Jinja fragment.
- GET `/api/v1/anomalies/timeline`, `/api/v1/anomalies`, `/api/v1/anomalies/export`:
  same canonical filter/selection/run scope. Export cap: 50,000 flagged outputs. Anomaly CSV contains compact signal summaries (event message preview up to 1,024 characters); use raw evidence paging or Log Explorer CSV for the full source text.
- GET `/api/v1/anomalies/DB-ID/evidence`, `/evidence/raw`, `/related`,
  `/evidence/export`: actual source evidence, model/rule/version, bounded signed
  related cursors and explicit missing fields, using the existing Drawer contract.
- GET `/api/v1/database/anomalies?dataset_id=...&run_id=...`: lower-level completed
  run page; native score and direction, no private message projection.
- GET `/api/v1/database/anomalies/ID/evidence?dataset_id=...`: lower-level bounded
  evidence API; the Investigation adapter provides richer navigation/context.

Common Investigation parameters: dataset source, UTC range, display timezone,
host/service, anomaly severity (Low/Medium/High/Critical/Unknown), detector IDs,
literal q, run_id repeated, optional version_id, selection_start/end/detector,
resolution, page/limit and detector-row page/sort. Dataset time presets end at the last observed imported timestamp, not the current wall clock; explicit UTC ranges override presets. One completed run per logical
detector is selected; default is its latest completed run. The returned state
pins run IDs, including an explicitly empty run snapshot. Mixed replay runs for
the same detector are rejected.

Count means **distinct persisted anomaly-output facts** in the selected run set.
It does not mean raw lines, evaluated units, active overlapping intervals or
unique incidents. A window is counted once at its start anchor, even if it spans
several display bins. Joins do not fan out through event membership. A single unit
flagged by two different detectors represents two detector signals. Timeline
uses global filters; table/CSV add the timeline selection. Facet counts omit their
own dimension and timeline selection. Native detector scores are never normalized
into a shared probability.

Integer microseconds and explicitly grouped MySQL `DIV` implement exact bins;
no floating Unix epoch arithmetic is used. Bin cells distinguish observed zero
from unknown/missing/unprocessed coverage. Only explicit coverage proofs can
establish complete processing; min/max timestamps do not establish completeness.
Related results are anomaly references; surrounding parsed logs are available in
Log Explorer. A window's raw sample is labeled as a sample, not all evidence.

## Jobs, incidents and email

| Method/path | Role/contract |
|---|---|
| POST `/api/v1/detection/jobs` | analyst+: dataset_id, idempotency_key, configuration (detector=rule/isolation_forest, window_seconds=60/300/900/3600, seed, optional aligned UTC range). 202 new; same key/config returns existing job; changed config 409. |
| GET `/api/v1/detection/jobs/{id}` | Dataset-scoped state, processed count, result and safe error code. |
| POST `/api/v1/detection/jobs/{id}/retry` | analyst+: failed/interrupted job only; active worker lease blocks recovery. |
| POST `/api/v1/alert-rules` | manager+: dataset_id, name, min_priority, optional detector_id/host, cooldown_seconds=0..86400. |
| GET `/api/v1/alerts` | dataset_id; optional before_id and limit<=100. |
| GET `/api/v1/alerts/{id}` | State, assignment, acknowledgement actor, last 100 audit entries, actual anomaly/run evidence link. |
| PATCH `/api/v1/alerts/{id}` | analyst+: status/assigned_to/note (<=2000); role, transition and assignee dataset grant checked. |

Run `python -m scripts.worker` outside Flask. No training or batch import is
executed inside an HTTP request. Jobs use connection-owned MySQL leases, atomic
prediction batches and unique run/unit identity for retry. The minimal worker
does not implement a distributed scheduler or automatic heartbeat recovery.

Alert matching is priority+optional detector+optional host. A decision ledger
records both created and cooldown-suppressed signals, so retry cannot release old
suppressed backlog. Cooldown is **per rule**, not per host when host is omitted.
Alert/anomaly/run references are database-scoped FKs. Audit history is append-only
through the application; it is not an independently tamper-proof audit service.

Email is queued in an outbox. Run `python -m scripts.database notify` explicitly.
SMTP_ENABLED must be 1; STARTTLS with certificate validation is mandatory. Raw
logs and credentials are not mailed. Attempts are bounded to three with backoff;
stable Message-ID helps receivers deduplicate. Delivery is at-least-once, not an
exactly-once SMTP guarantee. Actual external delivery was NOT RUN; mocks verify
TLS invocation, successful send and bounded failures.

HTTP file upload and arbitrary server-path ingestion are intentionally absent.
The operator-only CLI imports an immutable local BGL ZIP with bounded validation.
