# Eight-week and Advanced Python traceability

The planning source is the user's supplied LogSense AI master prompt, sections
4 and 21. It explicitly distinguishes Tkinter labs from Flask and says the roadmap
is a planning baseline. Separate lecturer materials/official grading weights were
not available in this workspace. This matrix does not certify a university grade.

| Roadmap | Delivered evidence | Status / remaining requirement |
|---|---|---|
| Week 1: factory, modules, config, MySQL, demo, Git | app/__init__.py, extensions.py, database.py, migrations, original UI tests | PASS locally; branch retained, no new push/merge |
| Week 2: auth, CRUD, validation, migration | security.py, domain.py, UserDataset, CLI registration/archive/account creation, four migrations, API tests | PARTIAL: login/hash/RBAC/CSRF work; full user/dataset CRUD UI and Flask-WTF specifically are not implemented |
| Week 3: BGL ingestion, files, jobs | parsers/bgl.py, services/bgl_ingestion.py, byte provenance/checkpoints, 1K..1M measurements | PARTIAL: operator CLI import works; HTTP upload UI/security pipeline is intentionally absent |
| Week 4: Explorer/REST | logs.py, log_queries.py, logs.html/logs.js, snapshot/filter/CSV tests | PASS for reads/Explorer; HTTP REST upload/ingestion submission is not implemented |
| Week 5: rules/features/IF/runs | detection.py, window_detection.py, worker.py, predictions/model version tests | PASS functionally; actual detector quality is insufficient, not production-ready |
| Week 6: Investigation/evaluation | mysql_investigation.py, mysql_evidence.py, original layout plus real adapter, unit-specific evaluation | PARTIAL: real timeline/Drawer/metrics work; supervised baseline and experiment comparison UI remain deferred |
| Week 7: alerts/email/integration | alerts services/API, incidents.js, audit/cooldown/outbox, SMTP mocks and browser workflow | PASS locally with mocks; external SMTP delivery NOT RUN |
| Week 8: responsive/QA/docs/demo | 1366/1440/1920 browser evidence, axe, API benchmarks, this documentation/demo script | PARTIAL: local QA/docs done; macOS native QA, external deployment and presentation deck NOT RUN. Dark mode intentionally omitted to honor the requested white design |

| Course concept | Actual implementation and demonstration | Qualification |
|---|---|---|
| Forms, labels, inputs, selectors, checkboxes, callbacks | Jinja forms, login, facet controls, timeline callbacks, evidence actions | Web UI concepts; not a Tkinter implementation |
| Layout/grid, reusable components, tooltips, status/error feedback | Existing white Investigation V2 CSS/macros, adaptive cells, errors/loading, drawer | Browser layout and keyboard checks; no claim of native Tkinter lab completion |
| Classes/state/data management | SQLAlchemy typed models, UTC TypeDecorator, LogScope dataclass, filter/snapshot state | Demonstrated in source and tests |
| Generators/context managers/exceptions/decorators | Streaming parser/export, Session.begin/import leases, QueryError, RBAC decorators | Meaningful bounded workflows and injected-failure tests |
| MySQL INSERT/SELECT/UPDATE and persistence | Ingestion, queries, acknowledgement/assignment, FK/unique/CHECK, JSON/byte roundtrip | Real MySQL 8.4.7 tests; destructive DELETE is intentionally not demonstrated on retained data |
| HTTP/JSON/REST/status codes | Flask Blueprints, GET/POST/PATCH, login/CSRF, API tests, urllib loopback benchmark | Actual network/browser workflow |
| Network data acquisition | Existing research download scripts and source register | Public sources retained locally; no invented download/benchmark |
| Flask chapters 1–7 | venv, factory/routes, Jinja, custom validation, ORM/migrations, SMTP outbox, modules/tests | Flask-WTF itself and a full deployment are not claimed |
| ML experimentation | Deterministic features/seed, temporal train/validation/test, version/artifact hashes, post-inference labels | Metrics are measured; zero-recall IF remains a documented failure for alert readiness |
| Concurrency/reliability | Separate worker process, connection-owned leases, request cancellation, atomic batch progress | No Redis/Celery/distributed scheduler claim |

If a lecturer explicitly requires Tkinter, supervised learning, DELETE CRUD or
Flask-WTF, obtain those exact criteria and implement focused additions. The
existing web UI cannot be described as automatic satisfaction of Tkinter labs.
