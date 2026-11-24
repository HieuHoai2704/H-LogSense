# University MVP v1.0: release audit and closure plan

**Cập nhật 05/11/2026.** Onboarding và cài sạch Windows đã qua QA. Dùng [báo cáo nghiệm thu mới](UNIVERSITY_MVP_READINESS_VI.md) cho trạng thái phát hành hiện tại. Phần dưới lưu checklist và phạm vi theo kế hoạch ban đầu.

Date: 2026-11-04. Target: a reproducible Advanced Python university demonstration
of the existing Flask/MySQL investigation workspace. This is a release plan, not
an issued release, a lecturer grade or a production-readiness certificate.

## Release decision

**HOLD pending final accepted scope, source review/freeze and defense rehearsal.** Dataset
metadata CRUD/RBAC, protected empty SQL DELETE, bounded queued HTTP upload and
actual Flask-WTF forms are now implemented. The expanded MySQL/API verifier
passed 123/123 tests; this supersedes their initial absent-feature findings.
The new dataset/upload browser E2E passed 11/11 groups, recorded separately in the
[current QA report](DATASET_UPLOAD_RELEASE_QA.md), not inferred from older runs.
No push, merge, release tag or publication is authorized by this audit.

The authoritative project planning sources are the supplied Master Prompt,
section 21 (eight-week deliverables, lines 1066-1165) and section 22 (MVP
acceptance, lines 1167-1186). The plan explicitly calls itself a planning baseline.
The original lecturer rubric and scoring weights remain unavailable; see the
[course audit](../../academic/course/COURSE_ACCEPTANCE_AUDIT.md). Requirements of the project
and unknown requirements of the course must remain separate.

This plan uses P0 for a release-blocking functional/safety/evidence issue in the
defined University MVP scope; P1 is a useful follow-up that can be deferred only
with a documented scope decision. These priorities are engineering judgments,
not invented lecturer grading weights.

## Eight-week source audit

| Week | Master deliverables | Current source/evidence | Status and gap |
|---|---|---|---|
| 1: foundation | Git, factory, Blueprint, config, MySQL/schema, layout, labeled prototype | Factory/extensions/database wiring, modular Blueprints including datasets/forms/uploads, migration chain 0001-0004, existing white Investigation UI and explicit Demo Mode | IMPLEMENTED locally; retain the current branch and uncommitted work until reviewed |
| 2: auth and CRUD | Login/logout, hashes, user management, dataset metadata CRUD, Flask-WTF, migrations/tests | Password-hashed auth, roles plus explicit dataset ACL, create/read/name-only update/empty DELETE; real dataset/upload Flask-WTF forms with signed form and header CSRF | CRUD/forms MySQL/API and browser PASS. Physical deletion is admin-only and refuses populated datasets; full user-administration UI is not implemented |
| 3: ingestion | File upload/validation, BGL parser, timestamps, errors, dataset/jobs | Operator BGL ZIP import plus bounded TXT/LOG/raw_line CSV HTTP staging, checksum/provenance, external upload worker, committed progress, rollback/resume/idempotency | Backend and actual 100K-upload browser E2E PASS in current QA. 16 MiB file cap; no arbitrary CSV schema or HTTP ZIP/path import |
| 4: Explorer/REST | Explorer, filters/sorting/pages, REST ingestion, dataset API, validation/tests | Authenticated Explorer, signed scope/keyset paging, CSV, dataset CRUD API and multipart upload/status/retry API | IMPLEMENTED for the documented BGL import scope; queued submission is not completed ingestion |
| 5: ML | Rule, features, IF, native score, model-run storage, tests | Event/host-window detectors and a separate opt-in frozen July IF inference profile, versioned schema/threshold/evidence, external worker | Functionality and guarded MySQL tests PASS; model quality remains experimental, private artifact required and pre-July21 windows rejected for the July profile |
| 6: investigation/evaluation | Timeline/table/detail, supervised baseline, applicable P/R/F1/AP, experiment comparison | Actual MySQL timeline and Evidence Drawer; aligned scope; valid unit-specific metrics; written rule/IF and IF V2 comparison with frozen test evidence | PARTIAL: supervised classifier baseline and general experiment-comparison UI are absent. Validation-label threshold calibration is not a supervised classifier |
| 7: alerts/integration | Severity rules, email, management, E2E/error/security | Scoped rules/incidents/notes/audit, dedup/cooldown, SMTP outbox and mock tests; integration/API tests | IMPLEMENTED locally with mocked SMTP. External email delivery is NOT RUN; the current real-data E2E/restart report is the fresh gate below |
| 8: finalization | Responsive UI, themes, performance, docs/README/repo/demo/presentation/final tests | Existing 1366/1440/1920 browser checks, benchmark reports, ERD/API/runbooks/tests | PARTIAL: presentation deck, native macOS run and external deployment are not verified. White-only UI follows the later user instruction and is not a dark-theme blocker |

Source locations include `app/security.py`, `app/api/`, `app/parsers/bgl.py`,
`app/services/`, `migrations/versions/`, `scripts/run/database.py`, `scripts/run/worker.py`
and the existing `tests/`. Detailed course concepts and limitations are in
[traceability](../database/TRACEABILITY.md).

## University MVP boundary

Keep the modular Flask monolith, MySQL, Jinja2, REST/JSON and current single
Investigation workspace. The release demonstration should show a bounded real
BGL sample through parsing, persistence, feature extraction, rule and IF scoring,
stored outputs, Timeline, actual evidence and scoped CSV. Synthetic Demo Mode
remains a separate labeled source. Account/permission checks and restart
consistency are part of the demonstration, not optional decorations.

Master section 22's upload/CRUD criteria are now implemented rather than replaced
with CLI-only import. The accepted lifecycle is metadata create/read/rename and
physical deletion of pristine empty datasets only; no force deletion of logs.
HTTP formats are BGL-compatible TXT/LOG and one-column raw_line CSV, with a
16 MiB original-content cap. Original bytes are retained privately and uploaded
labels remain supplied/unverified. Final acceptance must demonstrate these
exact bounds and cannot claim generic log ingestion or trusted upload labels.

Tkinter remains conditional on the lecturer's actual requirement. No desktop
companion is added merely because the course summary names Tkinter labs. A
presentation/report may be a university submission deliverable, but its exact
format, marks and mandatory content remain unverified without lecturer material.

## P0 closure backlog

| ID | Gap / verified risk | Required concrete change or decision | Acceptance evidence |
|---|---|---|---|
| P0-01 PASS | Dataset metadata CRUD with explicit RBAC/grants and safe physical deletion | Software acceptance complete; retain source review/freeze as P0-06 | 23 CRUD MySQL tests and current browser checks PASS, including roles, protected populated datasets, concurrency, rollback and narrow DELETE privileges; see [dataset contract](../database/DATASET_CRUD.md) and [current QA](DATASET_UPLOAD_RELEASE_QA.md) |
| P0-02 PASS | Validated upload and queued ingestion | Actual 100K upload reached verified Explorer without duplicate rows or lost provenance | Upload MySQL/API/worker and pure staging/security tests PASS; current dataset/upload browser 11/11 PASS, 100,000 parsed and zero malformed. [Current QA](DATASET_UPLOAD_RELEASE_QA.md) records the exact workload and bounds |
| P0-03 PASS | Actual Flask-WTF dataset/upload forms with dual CSRF | Valid/invalid forms and existing JSON mutations verified without disabling CSRF | Declared dependencies, pure form validation, guarded form/API tests and current browser checks PASS; [course evidence](../../academic/course/COURSE_ACCEPTANCE_AUDIT.md) |
| P0-04 DONE | Whole-chain evidence must be reproducible after restart | Measured real-BGL 100K E2E, 42 filter cases and real browser before/after restart passed; all 24 table checksums and CSV bytes match | [Readable E2E report](E2E_REAL_BGL.md), [structured evidence](measurements/university-mvp-v1/e2e.json), retained private raw/model artifacts |
| P0-05 DOCS UPDATED | README/demo must describe the exact current behavior | README/plan now distinguish CLI and uploaded BGL, supplied labels, legacy IF, V2 replay and reusable July inference; manual defense rehearsal remains open | [Current QA](DATASET_UPLOAD_RELEASE_QA.md), [upload contract](../database/UPLOADS.md), [July IF](../ml/IF_JULY_HOLDOUT.md), [demo](../database/DEMO_SCRIPT.md); historical reports remain unchanged |
| P0-06 | Release source snapshot is not reviewed/frozen | Review existing uncommitted changes, inspect diff/secret/data exclusions, freeze the accepted implementation and scope | Reproducible source hash/commit recorded after review. No push/merge/tag before approval |

If the fresh audit finds a reproducible cross-dataset leak, SQL inconsistency,
lost provenance, unsafe output or restart loss, that issue takes precedence over
feature completion. Fix only the verified defect, add a relevant regression and
rerun the affected E2E stage. Do not redesign the UI to close a backend defect.

## P1 closure backlog

| ID | Follow-up | Release treatment |
|---|---|---|
| P1-01 | Presentation deck and short defense narrative: OOP, Blueprint/Jinja, transactions, API/JSON, evidence, AI limitations | Prepare before submission; obtain the actual university format rather than guessing a rubric |
| P1-02 | Supervised baseline from week 6 | Use a future unused temporal test and appropriate unit/labels; never relabel IF calibration as a trained supervised classifier. Promote to P0 only if retained as required scope |
| P1-03 | Experiment comparison interface | Existing written baseline/IF comparison is demonstrable; defer a new comparison UI unless explicitly required |
| P1-04 | Native macOS setup/demo verification | Run on native macOS before claiming both operating systems verified. Windows success plus macOS instructions is not Mac execution evidence |
| P1-05 | Actual external SMTP delivery | Mock tests are adequate only for a declared mocked-email demo. Use user-authorized credentials/recipient if inbox delivery is required; never invent success |
| P1-06 | Basic account lifecycle documentation | Document operator account creation/grants, roles and login/logout. A full user-administration UI is a separate scope decision |
| P1-07 | Package reproducibility and clean-install smoke | Record dependency versions and `pip check`; pin a tested environment or lockfile if needed without changing framework or application layout |
| P1-08 FIXED | Real source used a misleading demo 60-minute label and raw None for missing service | Two Jinja expressions now use Full imported range for MySQL and Unavailable for missing metadata. Final real/DEMO regression passed; layout unchanged |

Enterprise scaling and research experiments are in the separate
[backlog](BACKLOG.md); they must not displace P0 closure.

## Release acceptance checklist

Check an item only when its linked execution report proves the stated scope.
Historical evidence remains useful but does not replace a failed fresh run.

- [ ] Record the accepted University MVP scope and unresolved lecturer criteria.
- [x] Implement and verify P0-01 dataset lifecycle through isolated MySQL/API
  tests, including real empty DELETE, RBAC, rollback and populated protection.
- [x] Implement and verify P0-02 upload API/external-worker validation,
  committed progress, integrity, retry/resume and idempotency in MySQL tests.
- [x] Implement and verify P0-03 Flask-WTF forms and both CSRF layers while
  retaining the JSON API mutation contract.
- [x] Attach the new dataset/form/upload browser and real-upload E2E acceptance
  record from [current QA](DATASET_UPLOAD_RELEASE_QA.md).
- [x] Fresh database upgrades through 0001-0004 with no model/schema drift;
  preserve existing databases and never stamp a broken schema as current.
- [x] Authentication, password hashing, roles, dataset ACL, CSRF and error
  contracts pass real API tests, including unauthorized other-dataset requests.
- [x] Real BGL import preserves original bytes, Unix UTC, original timestamp,
  labels and source/line/byte provenance; retries do not duplicate records.
- [x] Rule and IF feature extraction/detection run outside Flask requests;
  unit, version, threshold and score direction are persisted and inspectable.
- [x] Prediction/output/unit counts agree with SQL and API results. Count raw
  logs, parsed events, evaluated units and anomaly facts separately.
- [x] Timeline/table/drawer/CSV preserve the same global filters and selected
  time range; CSV formula prefixes and raw content are rendered safely.
- [x] Timeline zero/missing/unknown coverage and source DEMO/MYSQL remain distinct.
- [x] Real-data browser checks open/close evidence without losing scope or focus;
  existing Severity/Volume/brush/zoom and filter behavior remain intact.
- [x] Restart of an isolated owned database/app leaves counts, provenance,
  output identities and scoped responses unchanged; record real latency.
- [x] Expanded unit/integration/API tests pass; record guarded default skips
  separately and do not combine overlapping groups into an inflated total.
- [x] Finish browser regression of the newly added controls and the existing
  DEMO/real Investigation, Evidence Drawer and CSV workflows.
- [ ] README, environment example, migration/runbook, ERD/API docs, limitations
  and the demonstration script agree with the accepted implemented scope.
- [ ] Complete one uninterrupted timed defense rehearsal; record the exact
  dataset/run IDs and any manual steps honestly.
- [ ] Review the release diff, private-data exclusions and source snapshot.
- [ ] Obtain approval before push/merge/release publication. None occurred here.

Historical operator-chain entries are supported by the
[real-BGL report](E2E_REAL_BGL.md):
166 default tests (110 pass / 56 explicitly skipped), 63 guarded tests (56 actual
MySQL plus seven overlapping pure guards), 42 independent filter cases,
12 real browser groups before and after restart, and 21+13 DEMO browser groups.
Real browser checks cover scope/selection/evidence/Severity/Volume; brush/zoom
regression was exercised by the separate labeled DEMO suite. Remaining unchecked
scope/verification/rehearsal/publication gates prevent a v1.0 release declaration.
The superseding expanded execution is 264 default tests (153 PASS / 111 guarded
SKIP, 15.772s) and 123/123 explicit MySQL verifier tests (zero skips, 31.979s
including wrapper overhead). The latter includes 111 database cases and 12
overlapping pure guards; do not sum these as distinct tests. Current dataset/
upload browser checks passed 11/11 groups in 37.4725s on actual 100K BGL input
(13,259,718 bytes), yielding 100,000 parsed and zero malformed. Worker start to
verified Explorer was 29.3605s including UI checks. Final DEMO regressions passed
21+13 groups and real-data Investigation regression passed 12 groups; these
independent scopes are detailed in [current QA](DATASET_UPLOAD_RELEASE_QA.md).

## Demonstration sequence using current implemented commands

Use a newly registered research dataset. Commands assume the active native venv
and the existing private runtime wrapper; replace DATASET_ID with registration
output. No password belongs in CLI arguments, `.env.example` or screenshots.
The new E2E harness may use its own dedicated runtime/schema; its report records
the exact test environment separately from these operator commands.

```text
python -m scripts.run.mysql_runtime start
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db current
python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database register-bgl --key university-demo-UNIQUE
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database create-user --username investigator --role admin --dataset DATASET_ID
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 10000
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 100000
python -m scripts.run.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
```

The demonstration reaches the first 100,000 BGL source lines so that its window
detector has the previously observed train/validation/test periods; a 1K/10K
prefix alone is not an adequate promise of model sample sufficiency. Confirm
the current run's actual split counts before the defense. Do not fabricate
synthetic windows as real BGL evidence just to make IF produce results.
`--limit` is an absolute source-line target, so repeated targets demonstrate
idempotency rather than an additional N rows. These commands demonstrate the
operator CLI path. For HTTP import, create an empty dataset in the inline panel,
submit a compatible TXT/LOG or raw_line CSV with an authorized account, and run
`python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker`
in a separate terminal. Show queued/running/completed state and committed row
counts; do not describe a successful upload request as a completed import.

1. Open `/?workspace=logs`, sign in, choose the granted dataset and inspect UTC
   bounds, original log levels, host/search, keyset pages and scoped log CSV.
2. Open raw evidence; compare source line/byte, original timestamp, Unix UTC,
   supplied Node and ground-truth label with the actual source.
3. Expand **Alerts and analysis jobs**, select **Queue window rule**, then run
   `python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.worker --once`
   in another terminal. Check completion. Repeat **Queue Isolation Forest** with
   the same separate-worker command; neither training runs in Flask requests.
4. Open `/?source=db-DATASET_ID`. Show actual completed run IDs, native score
   direction, feature/threshold metadata, Timeline, selected cell, Evidence Drawer
   and matching anomaly CSV. Keep DEMO source visibly separate.
5. Distinguish the legacy policy, fixed-snapshot IF V2 replay and reusable July
   frozen inference. July test precision is 22.52%, recall 55.43%, F1 0.3203,
   AP 0.2656 and FPR 0.2037% on its own 172,529 observed parsed host-windows;
   82 positives are missed and 351 false positives remain. This is not a
   same-test improvement from June recall zero. Its opt-in profile needs a
   verified private model bundle and closed windows at/after July21 UTC; the
   earlier June demo is rejected. Uploaded supplied labels do not automatically
   qualify as trusted ground truth. Never transfer model-card metrics to a new
   dataset or silently train against its labels.
6. Show the real E2E/restart report, tests and limitations. A model flag is not a
   confirmed root cause; raw evidence is inspectable and priority is not model
   probability. Demonstrate external email only if actually authorized/tested.

## Verification record and publication status

Historical complete operator-chain results are recorded in
[`measurements/university-mvp-v1/e2e.json`](measurements/university-mvp-v1/e2e.json)
and [the readable report](E2E_REAL_BGL.md). The implemented operator-import chain
and isolated restart gate are **PASS**. Full University MVP release remains
**HOLD** pending final accepted scope, rehearsal and source-review/freeze/
publication gates. Current browser/real-upload software gates PASS.
CRUD/upload/Flask-WTF are no
longer absent. Their actual current execution is recorded in
[DATASET_UPLOAD_RELEASE_QA.md](DATASET_UPLOAD_RELEASE_QA.md). Historical reports
remain evidence of their own checkout/workflow, not proof that later features
were tested then. The [July IF study](../ml/IF_JULY_HOLDOUT.md) is separately
measured research evidence with a bounded reusable inference contract.

This document records explicitly authorized application changes without changing
the existing Investigation layout or introducing a new schema migration.
Existing uncommitted work and retained data are preserved. No push, merge or
release tag occurred. A final version label and public release require accepted
scope, all P0 closures and approval; local functional success alone is insufficient.
