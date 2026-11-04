# LogSense AI

A Python/Flask investigation workspace for imported system logs and experimental
anomaly detection. The application keeps a clearly labeled synthetic Demo Mode
separate from authenticated MySQL data. It is an Advanced Python portfolio
project, not a production monitoring or root-cause diagnosis service.

## Implemented

- Flask application factory, Blueprints, Jinja2 and modular Python services.
- MySQL 8.4, SQLAlchemy 2 and Alembic/Flask-Migrate; dataset-scoped foreign keys.
- Streaming Loghub BGL parser, exact source bytes and provenance, atomic batch
  ingestion, validation, malformed-row reporting, checkpoints and safe resume.
- Authenticated Log Explorer with UTC filters, signed keyset snapshots, bounded
  server-side pagination, aggregated volume and scoped streamed CSV.
- The existing Investigation V2 layout connected to persisted anomaly outputs:
  Severity/Volume, brush/zoom, facets, real Evidence Drawer and frozen run scope.
- Event baselines plus observed host-window rule/Isolation Forest jobs, versioned
  features/configuration, predictions and test-only evaluation.
- User/dataset permissions, password hashing, CSRF-protected changes, incident
  acknowledgement/assignment/notes/audit, cooldown decisions and an opt-in SMTP
  outbox with bounded retry.

The latest measured real-BGL prefix import reached **1,000,000 parsed events**.
That is not one million anomalies. Model quality remains experimental: the
current host-window Isolation Forest has **zero recall** on its defined test
split. See the exact measurements and limitations before interpreting results.

## Quick start: synthetic demo

Create/activate a native Python 3.10+ environment:

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app app run --host 127.0.0.1
```

```bash
# macOS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app app run --host 127.0.0.1
```

Open the loopback URL printed by Flask. No database URL/server is needed for
Demo Mode. Install all runtime dependencies even when using the demo. Never
copy a Windows venv or MySQL executable to macOS.

## MySQL and real BGL

Follow the [Windows/macOS runbook](docs/database/MYSQL_RUNBOOK.md). A local native
MySQL ZIP runtime uses only `.local`, port 13306 and 127.0.0.1; no service or global
configuration is installed. The lifecycle tool generates private credentials and
passes DATABASE_URL/FLASK_SECRET_KEY into child processes without printing them.
It refuses reinitialization over an existing runtime. No default login exists.

```text
python -m scripts.mysql_runtime start
python -m scripts.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.mysql_runtime exec --role app -- -m scripts.database register-bgl --key bgl-research-v1
python -m scripts.mysql_runtime exec --role app -- -m scripts.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.mysql_runtime exec --role app -- -m scripts.database create-user --username investigator --role admin --dataset DATASET_ID
python -m scripts.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
```

Replace DATASET_ID with the actual registration result. Account creation prompts
for a password; do not put passwords in command arguments. The import limit is an
absolute physical-line target: increase to 10000/100000 to resume the same source.
The archive must be the immutable locally downloaded Loghub BGL ZIP. HTTP upload
is not implemented. Do not pass untrusted server paths through an HTTP endpoint.

Open `/?workspace=logs`, sign in and select an authorized dataset. To investigate
completed detections, open `/?source=db-DATASET_ID`. The Demo workspace remains
available at `/`. Run the analysis worker separately:

```text
python -m scripts.mysql_runtime exec --role app -- -m scripts.worker
```

Jobs are submitted from the inline analysis controls or authenticated REST API.
A queued job is not a completed detection. Use the inline Alerts panel to create
rules (manager permission), acknowledge/assign incidents and inspect actual
anomaly evidence. SMTP is disabled by default; configure it privately and invoke
`python -m scripts.database notify` outside HTTP requests. Tests use mocks;
external SMTP delivery was not exercised.

## Verification and measurements

```text
python -B -m unittest discover -s tests -q
python -B -m compileall -q app scripts tests migrations
python -m pip check
```

The default suite explicitly skips real-MySQL tests. For actual integration,
privately configure MYSQL_ADMIN_URL and DATABASE_URL and run
`python -m scripts.verify_mysql`; it creates new token-marked test schemas, never
drops existing databases, and runs migrations plus integration/API/security tests.
See [testing](docs/database/TESTING.md) for browser tools and reproducible data
benchmarks. The final report distinguishes PASS, FAIL and NOT RUN.

- [Final QA / implementation report](docs/database/IMPLEMENTATION_REPORT.md)
- [Eight-week and course traceability](docs/database/TRACEABILITY.md)
- [API reference](docs/database/API.md)
- [Schema and ERD](docs/database/SCHEMA.md), [ERD diagram](docs/database/ERD.md)
- [BGL parsing/ingestion](docs/database/BGL_PIPELINE.md)
- [Detector/evaluation semantics](docs/database/DETECTORS.md)
- [Demo script](docs/database/DEMO_SCRIPT.md)
- [Architecture proposal V3](docs/architecture/README.md)
- [Research and dataset sources](docs/research/README.md)

## Limits and privacy

Native macOS execution, real external SMTP, screen-reader certification,
production deployment/TLS, full BGL archive detection, supervised baseline,
Tkinter companion, HTTP upload and production user administration are not
verified/implemented. The white UI follows the user's design constraint; no dark
mode was added. The supplied roadmap is not proof of an official lecturer rubric.

Raw datasets, MySQL files, dumps, model artifacts, private credentials and actual
research-data QA screenshots stay in ignored local directories. Git contains
source, migrations, tests and sanitized numerical reports. No background server
or schema creation occurs by importing the application. No push/merge is part of
this implementation.
