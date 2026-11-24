# Verification protocol

## Default suite (does not require MySQL)

```text
python -B -m unittest discover -s tests -q
python -B -m compileall -q app scripts tests migrations
```

MySQL tests are skipped unless explicitly opted in; a skip is **NOT RUN**, never
a database PASS. The original 50 demo/backend tests are retained unchanged.
Parser and database-unit tests cover byte preservation, epoch policy, malformed
UTF-8, offsets/CRLF/final line, missing host, Node versus NodeRepeat, safe text,
lazy reads, bounded line length, feature label independence, UTC conversion,
finite scores, URL validation and disabled-by-default real access.
The expanded pure suites additionally exercise WTForms fields and signed form
CSRF (not disabled for TESTING), upload byte/content/path/size validation,
minimal-grant command guards, holdout chronology, label-independent features
and frozen-model artifact contracts.

## Actual MySQL integration

Privately inject MYSQL_ADMIN_URL and DATABASE_URL for the same owned server,
then run `python -m scripts.verify_mysql`. Neither URL is a command argument.
The application username must already exist at localhost. This harness creates
two **new** `logsense_test_<12 hex>` schemas and token-hash ownership markers,
grants only schema-scoped permissions and sets TEST_DATABASE_URL for its process.
It never drops, truncates or rebuilds an existing schema.

`tests/test_mysql_integration.py` additionally requires
`LOGSENSE_RUN_MYSQL_TESTS=1`, a correctly formatted schema name and a matching
`LOGSENSE_TEST_TOKEN`. A development URL cannot pass this guard. Fixtures are
retained; each test uses a new dataset. The second fresh schema is migrated
independently to prove reproducibility. The harness reports a skip as INCOMPLETE.

Integration cases include real connectivity/UTC, migration reflection, dataset
archive, byte/JSON persistence, exact half-open boundaries and keyset ties,
cross-dataset raw/event, membership, run/output and unit/output FK violations,
version identity, negative scores, duplicate rejection, full rollback, coverage
proof checks, instant/interval checks, block labels without invented events,
malformed import, atomic checkpoint rollback, source-change rejection, persisted
rule/ML output, protected actual evidence access, second clean schema, exclusive
import lease and interrupted-job recovery.

Current additional guarded suites cover dataset metadata CRUD with roles plus
explicit grants, source isolation, concurrent creation, physical pristine-empty
DELETE, FK/revision/state protection, minimal SQL privileges and rollback;
multipart dataset/upload forms with both signed-form and header CSRF; staged
upload jobs, committed progress, content/provenance, idempotency, active leases,
bounded retry, mutation rejection and resume; and frozen July IF native scores,
actual DB event membership, cutoff/revision/dataset isolation and batch recovery.
New fixtures and accepted QA uploads are retained. Imported research data is
never made deletable just to demonstrate CRUD.

## Real BGL measurements

Use a new migrated `logsense_bench_*` schema. Run separate processes:

```text
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 1000 --output .local/bgl-1k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 10000 --output .local/bgl-10k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 100000 --output .local/bgl-100k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 1000000 --output .local/bgl-1m.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 100000 --resume --output .local/bgl-resume.json
python -m scripts.verify_import_restart --archive data/raw/BGL.zip
python -m scripts.verify_detectors --dataset DATASET_ID
```

The benchmark refuses a development schema and creates new datasets. Elapsed
ingestion time includes archive SHA-256, validation and database commits. Source
comparison and warm SELECT measurements are reported separately. RSS is sampled
every 10 ms for the importer process, not mysqld/OS cache or whole-machine RAM.
Single workload runs do not establish an ingestion latency p95. The query p50/p95
is over 20 warm, bounded event-page SELECTs, not a timeline benchmark.

Both injected exception and `os._exit(77)` worker-crash tests interrupt before
the line-50,000 commit; the committed checkpoint must remain 49,500. Resume and
retry compare all raw bytes/offsets/checksums/counts, not just final row count.
The crash fixture is genuine BGL data; the exit behavior is deliberately induced.

## Browser regression

Install Playwright separately as a QA tool. Set LOGSENSE_QA_OUTPUT to a new
private directory for each script, then run:

```text
python -B scripts/qa_investigation_v2.py
python -B scripts/qa_evidence_drawer.py
```

Windows defaults to Edge, macOS to the installed Playwright Chromium channel.
These two legacy scripts verify Demo Mode. `python -m scripts.qa_platform` adds login, real Log Explorer, MySQL Investigation/Evidence Drawer and incident E2E using private QA credentials. `python -m scripts.qa_accessibility` runs the pinned local axe-core scan; it is not screen-reader certification.

For the current inline dataset/form/upload workflow, inject private DATABASE_URL,
FLASK_SECRET_KEY, QA_USERNAME/QA_PASSWORD (admin QA actor), a fresh QA_OUTPUT and
optional QA_DATASET_ID for a retained populated dataset. Include private
QA_VIEWER_USERNAME/QA_VIEWER_PASSWORD for viewer-control coverage and
QA_UPLOAD_FILE pointing to an actual compatible local BGL TXT/LOG/CSV fixture
to exercise the real upload/worker path. Then run:

```text
python -m scripts.qa_dataset_crud
```

This script creates its own empty metadata fixture for rename/delete, and a
separate retained upload target when a file is supplied. The selected preexisting
QA_DATASET_ID is not renamed/deleted. Optional inputs omitted from a run appear
as NOT RUN; they must not be reported as browser coverage. The harness starts
and shuts down only its own loopback Flask server. The upload path invokes the
actual external ingestion worker, validates original SHA/provenance and refuses
physical deletion after data arrives.

For read-only regression against existing real BGL/results, use
`python -m scripts.qa_university_e2e_browser` with private DATABASE_URL,
FLASK_SECRET_KEY, QA_USERNAME/QA_PASSWORD, QA_DATASET_ID and
QA_OTHER_DATASET_ID (ungranted), a fresh QA_OUTPUT and QA_PHASE=before. It checks
logs, actual SQL anomaly counts, timeline/table/Evidence/CSV scope, role/dataset
denial, errors and 1366/1440/1920 layouts without importing or editing dataset
data. QA_PHASE=after is a comparison label, not a request to restart MySQL; an
operator controls an owned restart separately. Do not falsely label a run as
restart evidence without executing that stage.

## Current execution record

The expanded 2026-11-04 execution supersedes old missing-feature findings;
historical report JSON remains evidence of its original checkout/workload.
Read [current release QA](../releases/DATASET_UPLOAD_RELEASE_QA.md) for artifacts,
environment, exact measurements and limitations.

| Execution | Actual result | Measured time / scope |
|---|---|---|
| Default unittest discovery | 264 total: 153 PASS, 111 guarded SKIP | 15.772s; skips are NOT RUN database cases |
| Explicit isolated MySQL verifier | 123/123 PASS, zero skips | 31.979s including wrapper; 111 DB cases plus 12 overlapping pure guards |
| New dataset/forms/upload browser | 11/11 groups PASS, no page errors | 37.4725s; actual 100K-line BGL file, 13,259,718 bytes, 100,000 parsed, zero malformed |
| DEMO Investigation browser | 21/21 groups PASS, no page errors | 16.552s; synthetic only, no MySQL |
| DEMO Evidence Drawer browser | 13/13 groups PASS, no page errors | 10.453s; synthetic only, clipboard test adapter |
| Real-data Investigation/Evidence/CSV browser | 12/12 groups PASS, no page errors | 9.419s harness / 10.530s wrapper; retained actual 100K BGL, no restart in this run |

The upload's measured worker-start-to-verified-Explorer interval is **29.3605s**
and includes status/provenance/UI assertions; it excludes upload staging and is
not isolated import CPU time, total-machine RAM or p95 throughput. Do not sum
overlapping verifier/default cases as distinct tests. Real browser latency uses
12 warm authenticated loopback HTTP requests per endpoint, complete response
body received; it is not SQL-only timing or a general deployment SLA.

Native macOS execution, external SMTP delivery, full screen-reader certification
and the manual defense rehearsal remain NOT RUN/unverified. A passing software
suite does not establish a lecturer grade or a production release.

## Operations and security

Exercise initialize/start/stop in a new directory/unused port. Compare all-table
checksums across a graceful restart, logical backup and new-schema restore.
Check the app's base development grant is SELECT/INSERT/UPDATE and migration DDL
is separate. After migration the explicit operator command
`python -m scripts.mysql_runtime grant-dataset-crud --schema ACTUAL_SCHEMA`
adds DELETE on only datasets and user_datasets. Verify DELETE on logs remains
denied; neither app startup nor migrations silently broaden privileges.
Scan prospective Git content against actual private credential values,
ensure `.local`/datasets/artifacts are ignored, and review intended frontend
changes while retaining the Investigation layout and existing workflows.
Do not print a secret while reporting a scan match.

The final real suite includes the existing integration/platform suites and the
new dataset CRUD, forms, upload and validated-IF suites. Coverage includes
schema/FK/rollback, log snapshots, RBAC/CSRF, CSV injection, deterministic window
runs, retry leases, incidents, SMTP mocks and exact microsecond-bin boundaries.
Default discovery reports guarded DB cases as NOT RUN unless the harness opts in.
