# H-logsen

A local Python/Flask workbench for training runs, code, data profiling and log
investigation. The desktop launcher supports Windows, macOS and Linux, with an
optional local browser mode. The authenticated MySQL investigation
and the synthetic demo are separate data sources.

## Project map

| Path | What it is | Start here |
| --- | --- | --- |
| `app/` | The product: Flask application, workbench, templates, static assets, locales. OS-specific workbench code is isolated in `app/workbench/platforms/` | `app/__init__.py` |
| `migrations/` | MySQL schema history (Alembic) | |
| `tests/` | Product test suite: `python -B -m unittest discover -s tests` | |
| `scripts/` | Operator and developer commands, `python -m scripts.<group>.<command>` | [scripts/README.md](scripts/README.md) |
| `packaging/` | Installers and guides shipped in the Windows / macOS / Linux ZIPs | [packaging/README.md](packaging/README.md) |
| `docs/` | Product documentation | [docs/README.md](docs/README.md) |
| `academic/` | Papers, research notes, experiments and coursework (not shipped) | [academic/README.md](academic/README.md) |
| `sandbox/`, `data/`, `dist/`, `.local/` | Scratch space, datasets, builds and local runtime state (ignored by Git) | |

Dependencies are declared once, in `pyproject.toml`. `pip install -r requirements.txt` installs this checkout
(`-e .`) with everything the web app and workbench need; extras: `.[desktop]` (Linux window), `.[qa]`, `.[course]`.
Local runtime state (uploads, model studies, caches) lives in `.local/` of the checkout, or `LOGSENSE_LOCAL_DIR`.

The University MVP documents record the earlier academic baseline.
Dataset metadata CRUD/RBAC, safe empty-dataset deletion, bounded queued uploads
and real Flask-WTF forms are implemented and passed the expanded MySQL/API and
new browser/upload E2E gates. Actual execution is recorded in the
[current University QA report](docs/releases/UNIVERSITY_MVP_READINESS_VI.md).
The [release closure plan](docs/releases/UNIVERSITY_MVP_V1_PLAN.md) separates
remaining P0/P1 work from the [enterprise/research backlog](docs/releases/BACKLOG.md).
The earlier operator-import chain passed a
[real 100K BGL E2E and isolated restart](docs/releases/E2E_REAL_BGL.md), including
actual Timeline/Evidence/CSV and dataset-scope checks. That historical run does
not itself prove the subsequently added upload UI.
The original lecturer rubric is not available, so no course grade or full
eight-week completion is claimed. No push/merge is part of the current audit.

## Implemented

- Flask application factory, Blueprints, Jinja2 and modular Python services.
- MySQL 8.4, SQLAlchemy 2 and Alembic/Flask-Migrate; dataset-scoped foreign keys.
- Streaming Loghub BGL parser, exact source bytes and provenance, atomic batch
  ingestion, validation, malformed-row reporting, checkpoints and safe resume.
- Dataset metadata create/read/rename/delete with explicit dataset grants:
  manager/admin may create and rename; only an authorized admin may physically
  delete pristine empty metadata. Populated datasets are protected.
- Inline dataset/upload Flask-WTF forms with signed form CSRF plus existing
  session/header CSRF; JSON mutations retain their existing CSRF contract.
- Validated TXT/LOG BGL uploads and single-column `raw_line` CSV, at most 16 MiB;
  immutable staging, queued external ingestion, committed progress and bounded
  retry/resume. Original files have no HTTP download route.
- Authenticated Log Explorer with UTC filters, signed keyset snapshots, bounded
  server-side pagination, aggregated volume and scoped streamed CSV.
- Tkinter companion via the same HTTP API, a server-rendered dataset page with
  Jinja inheritance and WTForms, and a 15-language selector.
- The existing Investigation V2 layout connected to persisted anomaly outputs:
  Severity/Volume, brush/zoom, facets, real Evidence Drawer and frozen run scope.
- Event baselines plus observed host-window rule/Isolation Forest jobs, versioned
  features/configuration, predictions and test-only evaluation.
- User/dataset permissions, password hashing, CSRF-protected changes, incident
  acknowledgement/assignment/notes/audit, cooldown decisions and an opt-in SMTP
  outbox with bounded retry.

The latest measured real-BGL prefix import reached **1,000,000 parsed events**.
That is not one million anomalies. The historical default host-window IF policy
had **zero recall on its measured 100K-prefix test**. A separate opt-in frozen IF
V2 study achieved recall **38.60%**, F1 **0.4202** and average precision **0.1845**
on its own later 89,119-window test, while missing 404 of 658 positive windows.
V2 is not the default and replays a fixed snapshot; it does not automatically
score future imports. See [the historical IF audit](docs/ml/ISOLATION_FOREST_AUDIT.md).
A separately preregistered July model achieved precision **22.52%**, recall
**55.43%**, F1 **0.3203**, average precision **0.2656** and FPR **0.2037%** on its
independent 172,529 observed parsed host-window test. It misses 82 positives and
produces 351 false positives. These are different cohorts, not a same-test
recall 0-to-55% improvement. Its opt-in frozen inference profile accepts only
closed windows at/after 2005-07-21 UTC and requires the verified private model
bundle; it does not retrain on uploaded data. See
[the July experiment and reusable model contract](docs/ml/IF_JULY_HOLDOUT.md).

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

Open the loopback URL printed by Flask. The root opens H-logsen's project
workspace with local file viewing, a read-only editor and appearance settings.
The **Phân tích** tab opens MySQL Log Explorer if configured, or the demo
investigation otherwise. No database URL/server is needed for Demo Mode. Install all runtime dependencies even when using the demo. Never
copy a Windows venv or MySQL executable to macOS.

## Local workbench

### Install H-logsen from a download

Choose the ZIP for your system in [GitHub Releases](https://github.com/HieuHoai2704/H-LogSense/releases)
when a release is available. Extract it on the machine where H-logsen will run.
Use 64-bit Python 3.10–3.13 on Windows and macOS. Linux uses the system Python
(3.12 on Ubuntu 24.04, 3.14 on Ubuntu 26.04). The first install needs an internet connection.

| System | Install and open | Desktop requirements |
| --- | --- | --- |
| Windows x64 | `Install-H-logsen.cmd`, then the H-logsen shortcut or `Open-H-logsen.cmd` | Microsoft Edge WebView2 Runtime |
| macOS 14+ | `sh Install-H-logsen.sh`, then `sh Open-H-logsen.sh` | Python from python.org and system WKWebView. The macOS ZIP also contains Finder `.command` launchers. |
| Ubuntu 24.04 / 26.04 x64 | `sh Install-H-logsen.sh`, then **H-logsen** in the application menu or `sh Open-H-logsen.sh` | A Wayland or X11 session, system Python and WebKitGTK. See [installation instructions](packaging/posix/CAI_DAT_MAC_LINUX.txt) for apt packages. |

Extract the Windows release ZIP into a writable folder. Double-click
**Install-H-logsen.cmd** once, then double-click **Open-H-logsen.cmd**.
The installer uses Python 3.10–3.13 x64 and downloads the dependencies into
the extracted folder's own environment. The launcher opens a native Windows
window using Microsoft Edge WebView2 Runtime, with a local Flask server tied
to that window. Use `Open-H-logsen.cmd --browser` for browser mode.

To install manually, use CMD in the extracted folder.

~~~cmd
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install .\h_logsen-0.4.13-py3-none-any.whl
Open-H-logsen.cmd
~~~

The platform installers also accept a source checkout. Use `--browser` with
either launch script for local browser mode. Run `python -m scripts.release.package_workbench`
to build three platform ZIPs, a source ZIP and their SHA-256 file into an empty directory.
The [portfolio verification guide](docs/releases/PORTFOLIO_VERIFICATION.md)
covers clean installation, platform support and the publication checklist.

### Run directly from source

Use the installer above for desktop mode. To run the source checkout in a local
browser with filesystem access, editing, training runs and a real terminal:

```text
python -m pip install -r requirements.txt
python -m scripts.run.workbench --browser
```

The launcher creates a temporary capability. **Dự án → Mở thư mục** opens
the operating system folder picker in desktop mode and accepts an absolute project
path in browser mode. In the tree,
open a log or a source file. **Code** supports saving, native undo and
running a Python file with the interpreter selected in **Thiết lập**.
The terminal starts with CMD on Windows and an available local shell on
macOS/Linux. It uses the restored workspace folder or your home directory.
Use **Xem log** in the terminal toolbar to open the read-only log pane.
Project history and run outputs are stored under `~/.h-logsen` by default.
The regular Flask entry point has no local filesystem or terminal API.

- On desktop-sized windows, Project keeps the controls at the top and shares
  the remaining height between the charts and terminal.
- The Explorer search finds filenames and folders in unopened branches.
  Its results show relative paths and indicate when the scan is limited.
  It scans at most 12,000 entries and returns up to 80 matches.
- The workspace follows a root-level `train.log` when no other log or run
  has been selected. Text files open in the editor. Select **Theo dõi như log**
  in **Quản lý tệp** to explicitly follow a text or JSONL file. The activity
  badge distinguishes waiting for a source, waiting for lines and observed
  warning or error records.

- In Project, select a .log to follow it in place. Open source files explicitly
  with **Open in editor**. The timeline groups observed WARN, ERROR and CRITICAL
  lines, and selecting a cell pins the related log lines in the terminal.
  **Return to latest log** resumes the moving view. Analysis lets you select
  a local file for profiling. Project,
  Analysis, and Code remember their folders, expanded branches and open files independently.
  For an existing installation, the last project folder supplies the initial
  folder for each tab.
- Two windows sharing a profile merge settings and view changes. For the same
  project, tab and setting, the most recent save is used. After another window
  changes that tab's folder, refresh or reselect your folder before working.
- In **Code**, split into two panes and click a pane header to choose where
  the next file opens. Save the active pane using Ctrl+S on Windows/Linux or
  Command+S on macOS. PDFs are rendered one
  page at a time, up to 32 MiB per file. The dock contains Terminal,
  log-derived Problems, Output, local TCP Ports and an interactive Python
  Debug console using pdb. Choose the interpreter in the Code toolbar. New
  local shells put that Python first on their PATH. The default prefers the
  project's `.venv` or `venv`, then H-logsen's Python. On Windows run
  `python code.py` or `python -m pip` in the new session. Syntax highlighting
  runs in a worker for eligible text files and refreshes after a short pause.
- **Kiểm tra Python** checks the saved active Python file with Ruff from the
  selected interpreter and Pyright from the Code folder's `node_modules`.
  Results appear in **Vấn đề** with links to the line and column. A tool that
  is missing or fails is reported separately. **Định dạng** uses Ruff for
  Python and project-local Prettier for JS, TS, JSON, CSS, HTML, Markdown and
  YAML. Review the changes in the editor, then save. **Chạy tệp** opens a
  terminal pane for the saved `.py` or `.js` file with the Code folder as its
  working directory. **Theo dõi lượt chạy** retains the Python training
  history and metrics workflow.
- To enable the editor tools, open a fresh terminal in **Code** with the
  desired Python interpreter selected. In the project folder, run
  `python -m pip install ruff` and, with Node.js/npm available,
  `npm install -D pyright prettier`. H-logsen runs the installed tools on
  demand and uses project configuration. Use these commands in folders you
  trust and where you want to add these dependencies.
- In **Machine load**, hover to inspect a sample or pin it by clicking the
  plot or using the arrow keys. Pinning aligns the terminal log context
  and training chart with the selected timestamp, when their time ranges
  overlap. GPU and VRAM share a device selector backed by NVIDIA telemetry.
- Project logs update from the last 64 KiB. Run output and history come from
  the background supervisor. To plot loss, write UTF-8 CSV with
  `epoch,train_loss,val_loss` into `metrics.csv` at the project root or
  into the path given to a training script by `H_LOGSEN_METRICS_CSV`.
  Select a run from **Lịch sử lượt chạy** to inspect its UTC timeline, machine
  samples, checkpoint log messages and raw log context. Add an optional
  ISO 8601 `timestamp` column with an offset to synchronize loss with time.
  Legacy CSV can align to an unambiguous timestamped `epoch=N` log message.
  **Hồ sơ lượt chạy** records the Git branch, commit and whether the selected
  project had uncommitted changes, the Python executable and version, and
  the script and configuration fingerprints before launch. In
  **Thiết lập → Python và thư viện**, enter up to eight project-relative
  configuration paths, one per line. This registers their fingerprints in
  the profile. Pass any configuration path the script needs via its normal
  arguments. Common dependency manifests at the root are included
  automatically. The profile stores SHA-256 for files up to 1 MiB
  and a short allowlist of numeric flags such as `--epochs` and `--batch-size`.
  It omits file contents, environment values and other argument values.
  A fingerprint identifies a file at capture time. Keep the actual code and
  configuration separately if the run must be reproduced.
- To observe a process that is already running, open its project and choose
  **Gắn lượt chạy**. Enter its PID and the project-relative log and metrics
  paths that it writes. The process must run under your OS account with its
  working directory inside the project. H-logsen reads the supplied files and
  samples CPU and resident RAM for that PID while the run is being viewed.
  GPU and VRAM for attached PIDs are unavailable. To select by an external
  `run_id`, register a manifest first from the project directory:

  ```text
  python -m app.workbench.attached experiment-01 --pid 12345 --log train.log --metrics metrics.csv
  ```

  Replace the example PID with the real process ID. The registration records
  the process start time to reject PID reuse. Attached runs are read-only.
- To associate checkpoints, reports or other output files with this run, write
  them under `Path(os.environ["H_LOGSEN_ARTIFACTS_DIR"])` in the training script.
  The profile lists metadata for at most 100 results, plus the log, machine
  samples and loss CSV. It opens none of the result files. Existing runs retain
  their logs and metrics, with historical environment metadata shown as unavailable.
- Optional project `machine.jsonl` records take an ISO 8601 timestamp with
  an offset and numeric fields such as `cpu_percent`, `ram_percent`,
  `gpu_percent`, `vram_used_mib` and `vram_total_mib`. Live measurements
  use psutil, plus NVIDIA GPU/VRAM if `nvidia-smi` is available.
- Windows uses ConPTY for CMD and PowerShell. macOS/Linux use the native
  POSIX PTY and shells found under `/bin`. **Thiết lập → Máy từ xa** opens
  an outbound SSH terminal using OpenSSH and a pre-verified known host key.
  **+ Phiên** focuses the live shell when it is ready. Local shells can start
  in the user's home directory before a project is selected. New shells
  start in the active project when one is selected. The desktop window
  supports split panes. Detached terminal popups are available in browser mode.
  Keep the workbench on loopback. The session executes as the OS user.
  If the browser briefly loses connectivity, the open terminal resumes from
  its last output cursor while the same shell is still running. Output older
  than the server buffer is marked as skipped. Input is never replayed.
- **Thiết lập → Ngôn ngữ** controls Analysis and the primary workbench
  labels. Some advanced workbench labels are still Vietnamese. The color
  palette applies across all workbench tabs. **Tiện ích** manages
  built-in capabilities. **Python và thư viện** selects the interpreter and
  lists installed packages. Use the terminal for package installation.
- **Phân tích → Phân tích tệp dữ liệu** profiles CSV, JSONL and Parquet files
  within the open project. It displays a schema, up to 20 valid sample rows,
  missing values, duplicate rows after the first occurrence and distributions.
  Text inputs are limited to 1 MiB. The profiler scans at most 5,000 records.
  Parquet reports the total from file metadata and inspects at most 24 MiB of
  decoded row groups from files up to 256 MiB. Sample counts describe only
  inspected records. HDFS, OpenStack, Log CSV and Log JSONL remain available
  as separate log parsers. The separate evaluation CSV expects
  `unit_id,label,prediction` and binary 0/1 values. Use HDFS block IDs,
  OpenStack VM IDs or event IDs as applicable. The preview does not train a
  detector or import into the MySQL BGL pipeline. The separate full HDFS_v1
  CLI evaluates two baselines on complete block sessions. See
  [HDFS block baseline](academic/notes/HDFS_BLOCK_BASELINE_VI.md).
- For local tracebacks and test failures, select a source reference in a
  run's log or in the monitored log pane to open the file in **Soạn thảo**.
  A pytest summary without a line number opens the file only. Live local
  shell links require an absolute path within the currently open project.
- **Dự án → So sánh hai lượt chạy** compares runs within one project.
  It overlays train and validation loss by epoch and reports paired values at
  the latest shared epoch, along with code/configuration fingerprints and
  peak machine measurements from the recorded samples. Missing values are
  shown explicitly. Direct loss comparisons require matching datasets and
  definitions.
- Terminal assets are vendored from `@xterm/xterm@6.0.0`,
  `@xterm/addon-fit@0.11.0` and `@highlightjs/cdn-assets@11.11.1`.
  Their licenses are in `app/static/vendor/`.

If using MySQL through the operator runtime, start the launcher under the
same database configuration:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.workbench
```

## MySQL and real BGL

Follow the [Windows/macOS runbook](docs/database/MYSQL_RUNBOOK.md). A local native
MySQL ZIP runtime uses only `.local`, port 13306 and 127.0.0.1; no service or global
configuration is installed. The lifecycle tool generates private credentials and
passes DATABASE_URL/FLASK_SECRET_KEY into child processes without printing them.
It refuses reinitialization over an existing runtime. No default login exists.

```text
python -m scripts.run.mysql_runtime start
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database register-bgl --key bgl-research-v1
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database create-user --username investigator --role admin --dataset DATASET_ID
python -m scripts.run.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
```

Replace DATASET_ID with the actual registration result. Account creation prompts
for a password; do not put passwords in command arguments. The import limit is an
absolute physical-line target: increase to 10000/100000 to resume the same source.
The CLI archive must be the immutable locally downloaded Loghub BGL ZIP.
The extra grant is DELETE on only `datasets` and `user_datasets`, not log tables;
use the actual schema name if different. See [dataset CRUD](docs/database/DATASET_CRUD.md).

Open `/?workspace=logs` and sign in. A manager with no initial grants can register
a first dataset. Use `create-user --username investigator --role manager --no-dataset`
with the operator command above when starting from an empty database. To investigate
completed detections, open `/?source=db-DATASET_ID`. The Investigation link uses
the selected MySQL dataset. Open `/?source=demo` for synthetic fixtures. Run the
analysis worker separately:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.worker
```

For HTTP import, use the inline dataset/upload panels in Log Explorer. A
manager/admin can first create an empty dataset; an analyst/manager/admin with
its grant can stage a compatible TXT/LOG or `raw_line` CSV. A viewer cannot
submit imports. Run the separate ingestion worker to consume queued uploads:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker
```

The analysis worker does not consume upload jobs. A 202 response means queued,
not imported. The same dataset/idempotency key/content reuses its job; a new key
creates a separate artifact. Uploaded labels are explicitly user-supplied,
not independently authenticated Loghub ground truth. See
[formats, validation, provenance and recovery](docs/database/UPLOADS.md).

Jobs are submitted from the inline analysis controls or authenticated REST API.
A queued job is not a completed detection. Use the inline Alerts panel to create
rules (manager permission), acknowledge/assign incidents and inspect actual
anomaly evidence. SMTP is disabled by default; configure it privately and invoke
`python -m scripts.run.database notify` outside HTTP requests. Tests use mocks;
external SMTP delivery was not exercised.

## Verification and measurements

```text
python -B -m unittest discover -s tests -q
python -B -m compileall -q app scripts tests migrations
python -m pip check
```

Code style is enforced by ruff (lint and format) and types by mypy, both configured in `pyproject.toml`,
in CI and, optionally, as a git hook. Shared shapes (the investigation scope, job configuration, source and
anomaly identities) live in `app/contracts.py`; modules listed as typed in `[tool.mypy]` must annotate
every function.

```text
python -m pip install -e ".[dev]"
pre-commit install            # ruff check --fix, ruff format and mypy on every commit
ruff check . && ruff format --check . && mypy
```

The default suite explicitly skips real-MySQL tests. For actual integration,
privately configure MYSQL_ADMIN_URL and DATABASE_URL and run
`python -m scripts.qa.verify_mysql`; it creates new token-marked test schemas, never
drops existing databases, and runs migrations plus integration/API/security tests.
See [testing](docs/database/TESTING.md) for browser tools and reproducible data
benchmarks. The final report distinguishes PASS, FAIL and NOT RUN.

See the [latest University QA](docs/releases/UNIVERSITY_MVP_READINESS_VI.md)
for current discovery, isolated MySQL, browser results and clean installation.
The [clean setup checklist](docs/releases/UNIVERSITY_REPRODUCTION_VI.md)
covers fresh dependencies, migrations, an account without dataset grants
and the real-BGL browser workflow.

The [real-BGL E2E demo instructions](docs/database/DEMO_SCRIPT.md) use
`scripts.qa.verify_university_e2e` with a new owned MySQL runtime on **13307**, kept
separate from existing **13306** data. Its stages cover fresh migrations,
1K→10K→100K source import, parsing/provenance, actual worker detection, stored
anomalies, Timeline, Evidence Drawer, scoped CSV and a controlled restart with
before/after checks. This is operator CLI ingestion, not a file-upload UI.
Read the [measured E2E status](docs/releases/measurements/university-mvp-v1/e2e.json)
and individual stage reports; missing or pending reports must not be read as PASS.
The single-use setup refuses an existing private context instead of resetting it.

- [University MVP v1.0 closure/release checklist](docs/releases/UNIVERSITY_MVP_V1_PLAN.md)
- [Post-MVP enterprise and research backlog](docs/releases/BACKLOG.md)
- [Current course requirements matrix](academic/course/COURSE_REQUIREMENTS_MATRIX_VI.md)
- [Historical course source audit](academic/course/COURSE_ACCEPTANCE_AUDIT.md)
- [Vietnamese technical report](academic/course/BAO_CAO_LOGSENSE_AI_VI.md) and [submission verification checklist](docs/releases/UNIVERSITY_HANDOFF_CHECKLIST_VI.md)
- [Dataset CRUD/RBAC and minimal SQL privileges](docs/database/DATASET_CRUD.md)
- [HTTP uploads and queued ingestion](docs/database/UPLOADS.md)
- [Current dataset/upload/form/model QA](docs/releases/DATASET_UPLOAD_RELEASE_QA.md)
- [Final QA / implementation report](docs/database/IMPLEMENTATION_REPORT.md)
- [Eight-week and course traceability](docs/database/TRACEABILITY.md)
- [API reference](docs/database/API.md)
- [Schema and ERD](docs/database/SCHEMA.md), [ERD diagram](docs/database/ERD.md)
- [BGL parsing/ingestion](docs/database/BGL_PIPELINE.md)
- [Detector/evaluation semantics](docs/database/DETECTORS.md)
- [Demo script](docs/database/DEMO_SCRIPT.md)
- [Architecture proposal V3](docs/architecture/README.md)
- [Research and dataset sources](academic/notes/README.md)

## Limits and privacy

Native macOS execution, real external SMTP, screen-reader certification,
production deployment/TLS, full BGL archive detection, supervised baseline
and production user administration are outside the verified MVP scope.
The Tkinter companion runs with `python -m scripts.run.desktop`. The white UI follows the user's design constraint; no dark
mode was added. The supplied roadmap is not proof of an official lecturer rubric.

Raw datasets, MySQL files, dumps, model artifacts, private credentials and actual
research-data QA screenshots stay in ignored local directories. Git contains
source, migrations, tests and sanitized numerical reports. No background server
or schema creation occurs by importing the application. No push/merge is part of
this implementation.

Upload support is deliberately BGL-compatible, not a generic CSV parser or an
arbitrary server-file importer. Uploaded labels do not automatically qualify for
the trusted-Loghub evaluator; null metrics are retained when eligible ground
truth is unavailable. A cloned source checkout does not include the private July
model artifact, and must report that profile unavailable until provisioned.
