# LogSense AI

A Flask-based log anomaly detection project for an Advanced Python course.

## V3 architecture proposal

See the [Investigation V3 architecture review](docs/architecture/README.md) for
the proposed count/data model, compact timeline contract, SQL/index/coverage
strategy, staged benchmark matrix and scaling roadmap. A measured six-anomaly
fixture baseline is included; the 10K/100K/1M parsed-event MySQL benchmark is NOT
executed because an approved isolated database is unavailable. V3 does not change
the current application or provision infrastructure.

## Research resources

See the [research library](docs/research/README.md) for the initial paper register,
public dataset catalog, measured archive inventory and acquisition manifest.
Downloaded archives and paper PDFs are local-only and excluded from Git.
The [baseline review](docs/research/BASELINE_REVIEW.md) separates published scores
from unmeasured local methods.

## Current scope

Investigation V2 is a working single Flask/Jinja2 workspace with versioned REST
APIs, server-aggregated adaptive UTC bins, Overall and grouped detector rows,
Severity/Volume modes, brush/keyboard interval selection, backend zoom,
multi-select faceted filters, URL history, paged results, contextual evidence and
server CSV export matching the selected scope. All displayed records and evidence
are **synthetic**. Four labelled fixture sources exercise complete, empty,
unprocessed and partial-coverage states; they are not imported datasets.

See the [implementation report](docs/INVESTIGATION_V2_IMPLEMENTATION.md) for the
final component/API contract, audit, files changed, verification screenshots and
remaining blockers. Database access (MySQL/SQLAlchemy), authentication, ingestion,
real detector jobs and large-data performance are **not implemented or verified**.

The [Evidence Drawer report](docs/EVIDENCE_DRAWER.md) documents scope-wide
Previous/Next, safe redacted raw chunks, rule/ML availability, paginated related
records, source read policy and evidence export. Public access is restricted to
the explicitly configured synthetic source allowlist; this is not real user login
or authorization for private datasets.

## Local setup

Use Python 3.10 or newer. Run these commands from the project directory.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app:create_app run
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app:create_app run
```

Open http://127.0.0.1:5000 on the machine running Flask. This address is local
to that machine; a browser on another computer cannot reach it using localhost.
Stop the development server with Ctrl+C. The development server is for local
use, not public deployment.

## How it works

1. Flask calls `create_app()` in `app/__init__.py`.
2. The application loads settings from `config.py`.
3. A GET request to `/` calls the `dashboard()` view.
4. Jinja2 renders `app/templates/dashboard.html`; the API Blueprint shares the
   same validated query and aggregation service in `app/services/investigation.py`.
5. Browser updates use one composite API response; evidence and CSV are separate
   read endpoints. Downloaded research archives are not automatically imported.

Runtime dependencies are Flask and `tzdata` (IANA timezone support on Windows).

## UI scope checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests check synthetic scope aggregation and rendering. They do not verify
MySQL, real ingestion or ML, which have not been implemented.

Optional browser QA with the locally installed Microsoft Edge and Playwright:

```powershell
.\.venv\Scripts\python.exe scripts/qa_investigation_v2.py
```

The QA script starts and stops its own loopback server, exercises interaction and
failure states, and writes reports/screenshots to `docs/ui/implementation-v2/`.
Playwright is a local QA utility, not a runtime requirement for the Flask app.

## Research acquisition

```powershell
.\.venv\Scripts\python.exe scripts\download_research.py
.\.venv\Scripts\python.exe scripts\inspect_research_archives.py
```

The download script requires `curl` (`curl.exe` on this Windows workstation),
verifies dataset MD5 against the catalog and computes local SHA-256. It does not
extract archives. A failed paper source is recorded rather than treated as a PDF.
See `docs/research/download_status.json` and `paper_download_status.json` for
artifact status. PDF analysis/browser tools installed locally are research/QA
utilities, not application runtime dependencies.
