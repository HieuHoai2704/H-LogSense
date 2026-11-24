# Eight-week and Advanced Python traceability

For the current evidence/requirement distinction and acceptance checklist, read
[the course source audit](../../academic/course/COURSE_ACCEPTANCE_AUDIT.md). It identifies the
explicit Flask-WTF project-plan requirement separately from the unverified
lecturer criteria. No official course rubric has been found in the searched
workspace/conversation attachments.

This current-source matrix supersedes earlier missing-CRUD/upload/Flask-WTF
findings. Actual expanded tests and new upload/browser acceptance are in
[DATASET_UPLOAD_RELEASE_QA.md](../releases/DATASET_UPLOAD_RELEASE_QA.md).
Historical measurement JSON and the operator-import E2E report retain their
original scope; they are not rewritten as tests of subsequent features.

The planning source is the user's supplied LogSense AI master prompt, sections
4 and 21. It explicitly distinguishes Tkinter labs from Flask and says the roadmap
is a planning baseline. Separate lecturer materials/official grading weights were
not available in this workspace. This matrix does not certify a university grade.

| Roadmap | Delivered evidence | Status / remaining requirement |
|---|---|---|
| Week 1: factory, modules, config, MySQL, demo, Git | app/__init__.py, extensions.py, database.py, migrations, original UI tests | PASS locally; branch retained, no new push/merge |
| Week 2: auth, CRUD, validation, migration | security.py, domain.py, UserDataset, dataset_management.py/datasets.py, actual forms.py/form adapters, four migrations, CRUD/form API and browser tests | Dataset create/read/rename/empty SQL DELETE and dual-CSRF forms PASS. Admin plus explicit grant is required for pristine deletion; populated data is protected. Full production user administration is not implemented |
| Week 3: BGL ingestion, files, jobs | parsers/bgl.py, services/bgl_ingestion.py, uploads.py and ingestion_worker.py, original/derivative provenance, checkpoints, actual upload/import tests | PASS for documented BGL scope: CLI ZIP or validated TXT/LOG/raw_line CSV upload (16 MiB), queued external worker, rollback/resume/idempotency; supplied upload labels are not certified Loghub labels |
| Week 4: Explorer/REST | logs.py, log_queries.py, logs.html/logs.js, dataset CRUD/upload/status/retry endpoints, snapshot/filter/CSV tests | PASS for bounded Explorer and documented REST ingestion submission; 202 queued is distinct from completed import |
| Week 5: rules/features/IF/runs | detection.py, window_detection.py, worker.py, validated_if.py, predictions/model version tests, independent July study | PASS functionally, quality experimental. Frozen opt-in July profile rejects pre-July21 windows and needs its verified private artifact; no production-readiness claim |
| Week 6: Investigation/evaluation | mysql_investigation.py, mysql_evidence.py, original layout plus real adapter, unit-specific evaluation | PARTIAL: real timeline/Drawer/metrics work; supervised baseline and experiment comparison UI remain deferred |
| Week 7: alerts/email/integration | alerts services/API, incidents.js, audit/cooldown/outbox, SMTP mocks and browser workflow | PASS locally with mocks; external SMTP delivery NOT RUN |
| Week 8: responsive/QA/docs/demo | 1366/1440/1920 browser evidence, axe, API benchmarks, this documentation/demo script | PARTIAL: local QA/docs done; macOS native QA, external deployment and presentation deck NOT RUN. Dark mode intentionally omitted to honor the requested white design |

| Course concept | Actual implementation and demonstration | Qualification |
|---|---|---|
| Forms, labels, inputs, selectors, checkboxes, callbacks | Real Flask-WTF/WTForms dataset/upload validation, Jinja forms, login, facets, timeline/evidence callbacks | Used by actual inline workflows with signed form and session/header CSRF; web UI is not a Tkinter implementation |
| Layout/grid, reusable components, tooltips, status/error feedback | Existing white Investigation V2 CSS/macros, adaptive cells, errors/loading, drawer | Browser layout and keyboard checks; no claim of native Tkinter lab completion |
| Classes/state/data management | SQLAlchemy typed models, UTC TypeDecorator, LogScope dataclass, filter/snapshot state | Demonstrated in source and tests |
| Generators/context managers/exceptions/decorators | Streaming parser/export, Session.begin/import leases, QueryError, RBAC decorators | Meaningful bounded workflows and injected-failure tests |
| MySQL INSERT/SELECT/UPDATE/DELETE and persistence | Ingestion, dataset metadata CRUD, acknowledgement/assignment, FK/unique/CHECK, JSON/byte roundtrip | Real MySQL 8.4.7 tests; physical DELETE only on pristine empty fixtures, rollback and protected populated datasets verified. App DELETE is granted on only two metadata tables |
| HTTP/JSON/REST/status codes | Flask Blueprints, dataset GET/POST/PATCH/DELETE, multipart upload/status/retry, login/CSRF, API/browser tests | Actual network workflow; no arbitrary server-path import or unbounded raw-log browser load |
| Network data acquisition | Existing research download scripts and source register | Public sources retained locally; no invented download/benchmark |
| Flask chapters 1–7 | venv, factory/routes, Jinja, actual Flask-WTF forms/server validation, ORM/migrations, SMTP outbox, modules/tests | Exact lecturer coverage is UNVERIFIED; external SMTP and full deployment are not claimed |
| ML experimentation | Deterministic features/seed, temporal fit/validation/test, hashes, separate post-inference labels, historical V2 replay and opt-in July frozen inference | [Historical June audit](../ml/ISOLATION_FOREST_AUDIT.md) remains unchanged. [July independent holdout](../ml/IF_JULY_HOLDOUT.md) reports P/R/F1/AP/FPR and misses on its own observed parsed host-window target, not same-test June recall improvement |
| Concurrency/reliability | Separate worker process, connection-owned leases, request cancellation, atomic batch progress | No Redis/Celery/distributed scheduler claim |

Flask-WTF/WTForms is explicitly required by the supplied project Master Prompt
section 3 and is now implemented in real workflows, with pure, MySQL/API and
browser verification. This is not evidence of an official lecturer rubric.
The new CRUD module demonstrates actual SQL DELETE, distinct from archive
UPDATE, without authorizing deletion of retained logs. If course acceptance
specifically requires Tkinter, a supervised classifier or another exact workflow,
obtain the primary criterion first. A web UI cannot automatically satisfy Tkinter.

Current execution: 264 default tests (153 PASS / 111 guarded SKIP, 15.772s),
123/123 explicit MySQL verifier tests (111 DB plus 12 overlapping pure guards,
zero skips, 31.979s wrapper). New dataset/upload browser checks passed 11/11
groups on actual 100K BGL input; final DEMO regression passed 21+13 groups and
actual-data Investigation regression passed 12 groups. Do not sum overlapping
suites as distinct tests or infer native macOS/SMTP execution from these results.
