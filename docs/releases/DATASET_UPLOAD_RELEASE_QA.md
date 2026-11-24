# Dataset CRUD, upload, forms and frozen IF release QA

Date: 2026-11-04. Status: **implemented and locally verified; release HOLD pending source/scope review**. No commit, push or merge was made. Existing uncommitted work and retained BGL data were preserved. No migration/schema change was needed for these features.

## Outcome and boundaries

| Workstream | Result | Verified behavior |
|---|---|---|
| Dataset metadata CRUD/RBAC | DONE / PASS | Explicit dataset grants for every role, manager/admin create and name-only update, admin-only physical DELETE of pristine empty metadata, protected populated/busy datasets, FK checks, concurrent creation and transactional rollback |
| Secure BGL upload and queued ingestion | DONE / PASS | Bounded UTF-8 TXT/LOG or exactly one raw_line CSV column, immutable original SHA/provenance, external worker, committed progress, idempotent replay, retry/resume, malformed rows, dataset isolation and integrity failures |
| Flask-WTF/WTForms | DONE / PASS | Real inline dataset/upload forms; signed form CSRF plus existing session/header CSRF, invalid/expired/cross-session rejection, no-store responses; existing JSON API remains protected |
| Frozen reusable IF | DONE / PASS software; measured experimental quality | Validation-only selection, independent chronological July test, native lower-is-more-anomalous scores, actual DB evidence/IDs, inference cutoff, deterministic retry and revision isolation |
| Existing Investigation/DEMO | PASS | Current layout, Severity/Volume, brush/backend zoom, facets, scoped CSV, drawer focus/selection and synthetic labeling preserved |
| Native macOS, external SMTP, official grading approval | NOT RUN / UNVERIFIED | No Mac host, authorized external email execution or lecturer rubric in this session |

These are local development results, not an enterprise-readiness or university-grade certification. Viewer/analyst/manager/admin access is tested at the API; browser mutation controls are additionally checked for admin/viewer. Admin has no implicit bypass of per-dataset grants.

## Actual executions

| Execution | Result | Measured time / qualification |
|---|---:|---|
| Default discovery | 264 tests: 153 PASS, 111 guarded MySQL SKIP | unittest internal 15.772s; wrapper 17.688s |
| Explicit MySQL 8.4.7 verifier | 123/123 PASS, zero failures/errors/skips | 31.979s wrapper; two fresh guarded schemas retained |
| Dataset/forms/upload browser | 11/11 groups PASS, zero JS errors | 37.473s; actual Edge/Playwright, fresh isolated QA datasets |
| DEMO Investigation browser | 21/21 PASS, zero JS errors | 16.552s wrapper; synthetic fixture |
| DEMO Evidence Drawer browser | 13/13 PASS, zero JS errors | 10.453s wrapper; synthetic fixture |
| Existing actual-BGL browser regression | 12/12 PASS, zero JS errors | 9.419s script; 10.530s wrapper, read-only retained 100K dataset |
| Dependency integrity | PASS | python -m pip check: no broken requirements |
| Known private-value scan | PASS | Zero matches in prospective repository files; ignored credentials, venv, uploads and datasets remain excluded |

The 123 explicit cases comprise 111 real-DB guarded cases and 12 overlapping pure artifact guards. **Do not add 264 + 123 as unique tests.** Default SKIP means NOT RUN in that invocation; the explicit verifier supplies their execution. SMTP assertions in these suites use mocks.

The new MySQL coverage includes 23 CRUD, 14 signed-form, 12 upload/worker and 11 frozen-IF cases. Remaining cases preserve prior migrations/FK/rollback/log/query/detector/incident coverage.

A prior browser attempt caught a harness race: it captured URL state before the initial Explorer load finished. The harness now waits for the actual ready/nonbusy state. The failed attempt remains private; the final fresh patched-source run above passed. Other earlier failed/fixed runs are retained rather than relabeled as final PASS.

## Actual HTTP upload proof

The browser uploaded the actual Loghub BGL first 100,000 records as TXT/LOG, **13,259,718 bytes**, SHA-256:

```text
d6b55a02a67d9ab027abae4b60c365edbf9a892fcb6810ff780528512ca01c83
```

The UI queued the job without ingesting inside Flask. The separate ingestion worker committed **100,000 parsed events, zero malformed rows** into a new owned QA dataset. The browser verified original SHA, real raw provenance, final row count and deletion refusal. The measured worker-to-verified-Explorer interval was **29.361s**; it includes post-worker UI/API checks and is not isolated worker CPU or SQL time. Whole browser workflow was 37.473s. No new upload-process peak-RAM measurement or ingestion latency p95 is claimed.

The resulting populated QA dataset was retained. Only the browser's own newly created pristine CRUD metadata was physically deleted. Existing retained research logs were never deleted, renamed or reset. All generated test schemas, accepted source files and failed-attempt evidence remain available.

TXT/LOG retains exact original bytes including CRLF or missing final newline. CSV has a truthful row/physical-line map into the immutable original CSV; it does not claim CSV byte offsets or invent generic timestamp/host columns. Actual CSV parsing/ingestion is covered by unit/MySQL fixtures, not a new 100K CSV browser benchmark. Uploaded ground-truth labels are `uploaded-bgl/supplied`; they are not silently promoted to authenticated Loghub research labels. Missing eligible evaluation truth yields null metrics.

## Verified defects fixed during integration

1. Concurrent dataset creation could attach a missing DataSource relationship under a stale repeatable-read snapshot. Current locking read plus explicit parent relationship fixed the reproduced two-thread failure.
2. The POSIX upload permission loop reused the manifest path variable, producing the wrong manifest SHA. A regression reproduced FAIL, then passed after the variable fix. This exercises the POSIX code branch on Windows; native macOS is still NOT RUN.
3. Windows upload directories inherited broad local read/modify grants. New directories now establish a private current-account/SYSTEM ACL before any bytes are written, fail closed on ACL errors, and use no public raw-download endpoint. Existing owned upload storage was restricted without changing source content.
4. Default Investigation used only minimum raw timestamp, excluding a window anchor preceding the first raw record. Implicit ranges now include completed anomaly anchors, joined within the same dataset. Explicit [start,end) remains unchanged; regression checks both cases and an empty dataset.
5. Multipart private metadata responses now use Cache-Control:no-store even on the `/forms` routes outside the API URL prefix.

No main Investigation redesign, new frontend framework or invented score explanation was introduced.

## Actual-BGL filter/evidence consistency and latency

On the retained 100K dataset, SQL, timeline and table agreed on **158 detector-output facts** (not 158 distinct incidents); selected bin and CSV both contained **4** outputs. Evidence returned actual source line/rule threshold/version. Cross-dataset access was rejected. Close/Escape restored focus and selection. Browser layouts at 1366/1440/1920 had no document-level horizontal overflow.

Twelve warm loopback HTTP GET samples per endpoint, full body received:

| Endpoint workload | p50 ms | p95 ms | Payload bytes |
|---|---:|---:|---:|
| Bounded log page | 43.241 | 59.741 | 11,653 |
| Aggregated timeline | 63.552 | 83.958 | 21,980 |
| Investigation response | 77.807 | 89.325 | 183,673 |
| Evidence | 36.541 | 38.591 | 3,416 |
| Selected CSV | 20.362 | 21.526 | 562 |

These are current warm development measurements with 12 samples, not production capacity or isolated SQL latency. No new 1M end-to-end/UI benchmark or fresh upload restart test was run here; prior 1M import and isolated restart reports remain historical evidence.

## Independent IF result and reuse

The newly reserved July experiment trains on July 1-14, calibrates on July 14-21 and tests July 21-28, all UTC [start,end). It uses observed parsed 300-second host-windows. Neither labels nor future/test statistics enter features/model selection. Threshold tuning uses validation labels and must not be called fully unsupervised calibration.

The frozen July test had 172,529 units (184 positive): precision **0.225166**, recall **0.554348**, F1 **0.320251**, average precision **0.265610**, FPR **0.00203661**. It missed 82 positive windows and produced 351 false positives. Before/after model comparisons use this same new cohort in [IF_JULY_HOLDOUT.md](../ml/IF_JULY_HOLDOUT.md); the historical June zero-recall sample is a different cohort.

The reusable profile rejects pre-calibration June data and accepts only closed windows at/after July 21 UTC. It requires an operator-installed trusted private bundle, verifies hashes/specification and never loads uploaded pickle/model files. It does not retrain on uploaded data or convert scores to probabilities/causes. Its model card's independent metrics are not performance guarantees for newly uploaded logs.

[Actual DB reuse proof](../ml/measurements/if-july-holdout-2026-11-04/actual-db-profile-proof.json) uses a deliberately curated 20-window real-source functional slice. It verifies native scores, actual DB membership and evidence/CSV; this selected fixture is not another accuracy estimate. The July model/test selection remained unchanged.

## Reproduction and evidence

```text
python -m unittest discover -s tests -q
python -m scripts.verify_mysql
python -m scripts.qa_dataset_crud
python -m scripts.qa_investigation_v2
python -m scripts.qa_evidence_drawer
python -m scripts.qa_university_e2e_browser
python -m pip check
```

Inject MySQL/admin/QA credentials privately as described in [TESTING.md](../database/TESTING.md), choose a fresh QA_OUTPUT, and provide QA_UPLOAD_FILE for the optional actual upload browser path. The MySQL verifier creates fresh token-marked schemas; it never resets a development database. Do not rerun the single-use research holdout to tune an exposed test.

Structured evidence: [environment](measurements/dataset-upload-v1/environment.json), [unit](measurements/dataset-upload-v1/unit-tests.json), [MySQL](measurements/dataset-upload-v1/mysql-tests.json), [upload/CRUD browser](measurements/dataset-upload-v1/dataset-upload-browser.json), [DEMO timeline](measurements/dataset-upload-v1/demo-timeline.json), [DEMO drawer](measurements/dataset-upload-v1/demo-evidence.json), [real browser/latencies](measurements/dataset-upload-v1/real-browser.json), [security](measurements/dataset-upload-v1/security.json).

Actual screenshots, credentials, model/cache binaries, original logs and full failed/passed execution logs stay under ignored `.local`; they are not added to Git. Feature contracts: [CRUD](../database/DATASET_CRUD.md), [uploads](../database/UPLOADS.md), [course audit](../course/COURSE_ACCEPTANCE_AUDIT.md).

Remaining gates: review/freeze current uncommitted source; actual lecturer requirements; native macOS smoke; user-authorized external SMTP if required; manual screen-reader/defense rehearsal. Enterprise scaling, automated retention and new research comparisons stay in the backlog. No push/merge is authorized by this report.
