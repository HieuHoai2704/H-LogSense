# Reproducible local demonstration

**Release status: HOLD pending accepted scope, source review/freeze and manual
defense rehearsal.** Dataset CRUD/RBAC, safe empty SQL DELETE, bounded queued
HTTP uploads and actual Flask-WTF forms now pass their MySQL/API and current
browser software gates. See [current QA](../releases/DATASET_UPLOAD_RELEASE_QA.md)
and the [University MVP closure plan](../releases/UNIVERSITY_MVP_V1_PLAN.md).
Enterprise/research extensions belong in
the [post-MVP backlog](../releases/BACKLOG.md). Lecturer grading criteria remain
unverified until the original rubric is supplied.

## Automated real-BGL E2E and restart

Run from the project root using a native activated Python venv. Prerequisites:
the existing runtime requirements; the immutable real `data/raw/BGL.zip` with its
`BGL.log` member; a native MySQL **8.4.7** distribution for this operating system;
and the Playwright/browser QA tools described in [TESTING.md](TESTING.md).
Browser stages use the configured native browser, not an invented browser result.
Windows MySQL binaries and Windows virtual environments cannot run on macOS.

The test runtime must be a **new owned** `.local/university-e2e-mysql` on loopback
port **13307**. OS_NATIVE_BASEDIR below means the actual path of the native MySQL
distribution containing `bin/mysqld` (or `bin/mysqld.exe`); replace it before
running. This is separate from the retained application runtime on port 13306.
No OS service or global MySQL configuration is installed.

```text
python -m scripts.run.mysql_runtime --root .local/university-e2e-mysql init --basedir "OS_NATIVE_BASEDIR" --port 13307
python -m scripts.run.mysql_runtime --root .local/university-e2e-mysql start
python -m scripts.qa.verify_university_e2e --stage setup --archive data/raw/BGL.zip --lines 100000
python -m scripts.qa.verify_university_e2e --stage detect --kind rule
python -m scripts.qa.verify_university_e2e --stage detect --kind isolation_forest
python -m scripts.qa.verify_university_e2e --stage verify --phase before
python -m scripts.qa.verify_university_e2e --stage browser --phase before
python -m scripts.qa.verify_university_e2e --stage restart
python -m scripts.qa.verify_university_e2e --stage verify --phase after
python -m scripts.qa.verify_university_e2e --stage browser --phase after
python -m scripts.qa.verify_university_filters
```

Execute in order and stop at any failed stage. `setup` provisions a uniquely
named schema, applies migrations through the migration role, creates private
QA account/dataset grants, imports actual BGL source targets 1K→10K→100K, and
checks rollback/resume/idempotency/provenance. It is **single-use**: an existing
`.local/university-qa/e2e/context.json` causes refusal, not silent reuse/reset.
`init` likewise refuses an existing runtime. On this workspace, preserve the
existing context and inspect its stage reports; do not delete state merely to
make the setup command run again. A failed or interrupted stage must be
investigated against its retained state before deciding how to resume.

The detector stages submit authenticated jobs and execute the actual separate
worker. Native scores, predictions, versions and anomaly outputs are persisted
in MySQL. Verification compares SQL and API counts, dataset isolation, filter
scope, source provenance, Timeline/table/evidence/CSV behavior and error states.
The browser stages exercise the real persisted results through the current UI.
The restart stage requires successful before-checks and restarts **only** the
owned 13307 runtime; the existing 13306 runtime and datasets are untouched.

Credentials remain in ignored local state and are passed in memory/process
environment. No password is supplied in the commands above, written into Git,
or displayed in the public report. There is no manual SQL or database repair
step in the successful demonstration path, and no external email is sent.

Measured PASS/FAIL/NOT RUN and latency belong in the
[E2E summary](../releases/measurements/university-mvp-v1/e2e.json) and adjacent
`setup.json`, `detect-*.json`, `verify-before/after.json`, `browser-before/after.json`
and `restart.json`. Treat absent/pending stages as NOT RUN, never PASS. Private
credentials, raw/model artifacts and actual browser screenshots remain under
`.local/university-qa/` and `.local/university-e2e-mysql/`.

The recorded run is now [PASS for the implemented chain](../releases/E2E_REAL_BGL.md).
That historical chain uses operator CLI import; it does not itself prove the
later HTTP upload workflow. The new [dataset/upload QA](../releases/DATASET_UPLOAD_RELEASE_QA.md)
records 11/11 browser groups PASS on an actual 100,000-line, 13,259,718-byte BGL
file, yielding 100,000 parsed events and zero malformed rows. The measured
worker-start-to-verified-Explorer interval is 29.3605s including browser/status/
provenance checks; total browser run is 37.4725s. Neither is isolated import CPU
time or a repeated-throughput distribution.
The 42-case filter script retains an existing report instead of overwriting it;
use an explicit new `--report-name NAME.json` for a later authorized verification.
Default unit tests and guarded MySQL tests are separate commands in TESTING.md;
the E2E stages do not silently execute them. After their reports and the DEMO
browser reports are captured for the same source, the optional
`python -m scripts.qa.verify_university_e2e --stage summary` aggregates these local
evidence files. Read the source/date/workload in each report; aggregation is not
a replacement for executing a test.

After all stages and evidence are captured, the owned test runtime can be stopped
without deleting its data:

```text
python -m scripts.run.mysql_runtime --root .local/university-e2e-mysql stop
```

## Interactive defense walkthrough

Use a fresh authorized research dataset; never reset somebody else's database.
Windows commands use the active venv Python; macOS uses its own native venv/MySQL
distribution. Setup commands and credential handling are in MYSQL_RUNBOOK.md.
The operator commands are also listed in the
[release plan](../releases/UNIVERSITY_MVP_V1_PLAN.md#demonstration-sequence-using-current-implemented-commands).

1. Start the private loopback MySQL runtime, apply migrations through the migration
   role, register a BGL dataset and create a granted investigator account. Password
   entry is private; no default/demo password exists.
   After migration, explicitly run
   `python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev`
   for the actual intended schema. This grants DELETE on only datasets and
   user_datasets, not imported logs. It is not an automatic app-start privilege.
2. Run import with absolute limits 1000, 10000 and 100000. Show committed progress,
   raw/parsed/malformed counts and source SHA-256. Repeating the same target does
   not add source/event/label rows. Explain the difference between original bytes,
   parsed events, units and anomaly outputs.
3. Open `/?workspace=logs`, sign in, select the dataset and inspect UTC range,
   host/level/search filters. Page next/previous; show that the browser receives a
   bounded page and signed snapshot. Click a volume bin; confirm table/CSV scope.
4. Open a log's raw drawer. Show original timestamp string, authoritative Unix UTC,
   supplied Node, original label, file/line/byte provenance and redacted source
   text. Close with Escape and demonstrate preserved filters/focus.
5. Start `python -m scripts.run.worker` through the private environment wrapper. Queue
   a rule job, then IF. Explain temporal splits, template policy, features and
   thresholds before showing test metrics. Labels are not model features.
6. Open `/?source=db-DATASET_ID`. Show selected completed runs, Severity/Volume,
   faceted search, exact cell selection, brush/zoom and actual Evidence Drawer.
   Explain that a window contributes one anchored output, not one count per bin.
   Point out unknown source coverage and the absence of a confirmed root cause.
7. Expand Alerts in Log Explorer. Create a High-priority rule with manager
   permission, then run a new analysis. Show alert dedup/cooldown, acknowledgement,
   assignment to an authorized investigator, note history and the anomaly/run
   evidence link. No email is sent unless SMTP is explicitly configured/enabled.
8. Show numerical reports for real 10K/100K/1M ingestion/API measurements, source
   verification, actual integration/browser/axe results, and backup/restore proof.
   Distinguish separate cohorts: the historical default window IF had zero recall on
   the measured 100K-prefix test; the separate opt-in frozen IF V2 study had
   recall 38.60%, F1 0.4202 and average precision 0.1845 on a later test, but
   missed 404/658 positive windows. V2 is not the default and does not score
   future imports automatically. See [the historical IF study](../ml/ISOLATION_FOREST_AUDIT.md).
   The later preregistered July profile has precision 22.52%, recall 55.43%,
   F1 0.3203, AP 0.2656 and FPR 0.2037% on its independent 172,529 observed
   parsed host-windows, with 82 misses and 351 false positives. Its reusable
   opt-in inference requires the verified private model bundle and closed
   windows at/after July21 UTC; the earlier June demo is rejected. See
   [July model contract](../ml/IF_JULY_HOLDOUT.md). This is not a same-test
   June recall improvement or a probability/root-cause explanation.
   Do not promise either metric for a freshly imported demonstration sample or
   hide weak detector quality behind passing software tests.

Actual-data screenshots are intentionally private under
`.local/database-verification/platform-browser/`. The demo fixture remains at `/`
for a reproducible public/synthetic walkthrough without private data access.

Closing discussion: macOS native execution and real external SMTP were NOT RUN;
Tkinter, supervised baseline and production deployment are not
completed roadmap items. No university-grade or enterprise-readiness claim is made.

## Inline dataset, forms and upload demonstration

Use a granted admin QA account and a fresh test dataset; keep existing imported
datasets intact. No additional page/menu or frontend framework is needed.

1. Open Log Explorer and expand the dataset panel. Create metadata with a unique
   key; rename its display name and show preserved active log filters. Manager
   or admin can create/rename; a viewer cannot. Dataset lists include only grants,
   and admin role alone does not bypass another dataset's ACL.
2. Physically delete only that pristine empty test metadata as an authorized
   admin, using the inline confirmation. Explain the transaction/FK/revision
   checks. Show a protected 409 for a populated dataset rather than attempting
   force deletion; no raw/event/job/incident data is deleted.
3. Create a separate upload target and submit a known BGL TXT/LOG (or a CSV with
   exactly one raw_line column), no larger than 16 MiB. Show validation errors
   for incompatible input without fabricating timestamp/host/label fields.
   The actual browser forms use WTForms validation, signed Flask-WTF CSRF and
   session/header CSRF; JSON APIs retain their existing mutation protection.
4. Show queued state, then start the separate worker outside Flask:

   ```text
   python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker
   ```

   The analysis `scripts.run.worker` process does not consume upload jobs. Show
   committed progress, completed state and parsed/malformed counts, then open
   the imported dataset in Explorer. Do not describe 202 queued as completion.
5. Inspect raw provenance: original SHA-256 and text-line reference or explicit
   CSV row/physical-span mapping to the normalized derivative. Original bytes
   remain private; there is no HTTP original download route. Uploaded labels
   are supplied/unverified, so trusted-Loghub evaluation can have zero eligible
   ground truth and null metrics without an ingestion failure.
6. Explain exact idempotency: same dataset/key/content reuses its job; a new key
   is a new artifact. A retry checks immutable hashes and resumes committed
   checkpoints with bounded attempts. Never edit accepted staged files or reset
   a dataset merely to rerun the demonstration.

The recorded latest verification is 264 default tests (153 PASS / 111 guarded
SKIP), 123/123 explicit verifier tests (111 DB and 12 overlapping pure guards,
zero skips), current upload browser 11/11, final DEMO 21+13 groups and real-data
Investigation browser 12 groups. These groups have different scopes and must not
be added into an inflated distinct-test count. Details and limitations remain in
[the current QA report](../releases/DATASET_UPLOAD_RELEASE_QA.md).
