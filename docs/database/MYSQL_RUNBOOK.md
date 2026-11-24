# Local MySQL 8.4 ZIP runbook: Windows and macOS

Scope: an owned development server, loopback only, no OS service, no global
configuration and no deletion/reset of any database. Windows 8.4.7 was exercised
here. macOS commands and portable Python paths are provided; **native macOS
execution is NOT RUN** because this session has no macOS machine. Do not interpret
cross-platform source compatibility as an executed macOS certification.

## Prerequisites and first provisioning

Use Python 3.10+ and a virtual environment. Windows uses
`.venv\Scripts\python.exe`; macOS uses `.venv/bin/python` after creating it with
`python3 -m venv .venv`. In examples below `python` means that venv interpreter.
Install `python -m pip install -r requirements.txt`.

Obtain the official **native** MySQL 8.4 distribution for the OS and CPU from
[MySQL archives](https://downloads.mysql.com/archives/community/). Windows ZIP
cannot execute on macOS; use the macOS archive matching Intel/Apple Silicon and
the supported macOS release. Do not install a service or change system-wide
MySQL settings. Extract into an owned directory; verify the published checksum
and retain the local SHA-256. This session used:

```text
https://cdn.mysql.com/archives/mysql-8.4/mysql-8.4.7-winx64.zip
bytes: 260872794
SHA256: fd9bdbd4b5a878d31c8e4067078bd60665b1b3c4677fa1f099416d194b458aff
published .md5: matched before extraction
```

Run from the repository root. For a **new** runtime directory only:

```text
python -m scripts.run.mysql_runtime --root .local/mysql-foundation init --basedir NATIVE_MYSQL_BASE_DIRECTORY --port 13306
python -m scripts.run.mysql_runtime status
```

`status` is expected to fail until `start` below. `init` refuses an existing
runtime or a listening port. It writes a repo-local config with absolute owned
paths, InnoDB 128 MiB buffer pool, utf8mb4, UTC, bind-address 127.0.0.1, port 13306
and mysqlx disabled. It initializes offline, then uses a private init-file on
first start to set random passwords **before** network service is available.

Private settings and MySQL data live under `.local`, ignored by Git. Windows
initialization removes inherited ACLs and grants the current user and SYSTEM;
POSIX uses directory mode 0700 and private file mode 0600. Keep the directory
private. The initial bootstrap SQL is replaced with a comment after successful
first startup. Passwords never appear in command arguments or printed output.

## Start, inspect and stop

```text
python -m scripts.run.mysql_runtime start
python -m scripts.run.mysql_runtime status
python -m scripts.run.mysql_runtime stop
python -m scripts.run.mysql_runtime start
```

`start` passes one correctly quoted defaults-file argument to the native binary,
launches a hidden background process on Windows, and waits for authenticated
readiness. No Windows service, launchd job or shell daemon setup is installed.
`status` verifies server version, loopback binding, timezone and that @@datadir
matches the protected owned directory. It does not print credentials.
`stop` verifies the same ownership and performs SQL `SHUTDOWN`; it does not kill
unrelated processes or delete files. The data directory remains for restart.

If another process owns the port, stop and inspect; do not kill it or replace its
configuration. If startup fails, inspect private `server-error.log` and
`launcher.log`. Never rerun initialization over an existing data directory. A
partial initialization requires investigation and a new dedicated directory.

## Roles, application and migrations

- `root@localhost`: local provisioning, grants, backup, safe restore, shutdown.
- `logsense_migrator@localhost`: SELECT/INSERT/UPDATE/CREATE/ALTER/INDEX/REFERENCES
  on `logsense_dev` only; no global privilege or DROP/DELETE grant.
- `logsense_app@localhost`: initially SELECT/INSERT/UPDATE on `logsense_dev`
  only. Dataset CRUD additionally needs an explicit post-migration DELETE grant
  on only `datasets` and `user_datasets`; no DELETE on logs/jobs/anomalies.
  Production read-only access should use a separate SELECT-only account and
  real identity/tenant enforcement.

Test harness grants DDL only on newly generated isolated test/benchmark schemas.
Those grants are not runtime requirements. No remote-host account is created.

The wrapper constructs DATABASE_URL inside a child process so no real URL is
copied into source, terminal history or `.env`:

```text
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db current
python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database register-bgl --key bgl-v1
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database create-user --username investigator --role admin --dataset DATASET_ID
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.run.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
```

The default UI continues to show synthetic fixtures. Health is
`/api/v1/health/database`. Create an account/dataset grant using the private CLI,
then open `/?workspace=logs`; real Investigation is `/?source=db-DATASET_ID`.
A URL parameter alone never authorizes a dataset. Optional operator read tokens
must be privately injected, not hard-coded into a frontend.

The `grant-dataset-crud` command is an explicit operator action after migrations,
not an automatic startup grant. It validates the owned runtime, target schema
identifier and both existing base tables before granting DELETE on exactly the
two metadata tables. It grants no schema-wide DELETE, DDL, DROP, GRANT OPTION or
remote access and executes no data deletion. Repeat the fixed operation safely
after checking an interrupted result; MySQL GRANT auto-commits. For another owned
runtime/schema pass its actual `--root` and `--schema`; do not grant against a
guessed or unrelated schema. See [the exact contract](DATASET_CRUD.md).

Application deletion is separately guarded by active admin role, explicit
dataset grant, CSRF, a dataset row lock and no dependent data/revision. Only
pristine empty registered/archived metadata and its ACL links may be removed
atomically. Populated datasets return 409; table-level grants never authorize
HTTP access to another dataset.

## Queued uploads and analysis workers

After signing in to Log Explorer, a manager/admin can create/rename granted
dataset metadata in the inline panel. An analyst/manager/admin with a grant can
stage BGL-compatible TXT/LOG or one-column `raw_line` CSV (16 MiB file cap).
Both signed Flask-WTF form CSRF and session/header CSRF apply. Uploads are stored
under private ignored `.local/uploads`; original bytes are not served by HTTP.

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.worker
```

Run the processes separately. The first consumes upload jobs; the second runs
detectors. Flask requests only validate/stage/queue imports; a queued response
is not completion. Poll committed progress in the existing UI. A retry reuses
an immutable artifact/checkpoint and has bounded attempts; do not edit staged
files to force recovery. Same dataset/key/content replay reuses its job, while a
new key represents a new artifact. See [upload recovery and provenance](UPLOADS.md).
Uploaded labels remain supplied/unverified, so trusted-Loghub evaluation can
correctly return no eligible ground truth and null metrics.

## Backup and isolated restore

Choose a **new output filename** per backup (existing files are never overwritten):

```text
python -m scripts.run.mysql_runtime backup --schema logsense_dev --output .local/mysql-foundation/backup-RUN_ID.sql
python -m scripts.run.mysql_runtime restore --input .local/mysql-foundation/backup-RUN_ID.sql
```

Backup uses an InnoDB single-transaction logical dump, hex BLOBs, no DROP TABLE,
no CREATE/DROP DATABASE, no locks added to the output and no GTID changes.
A SHA-256 manifest accompanies the private dump. Error output is not echoed with
credentials or raw data. A failed/incomplete output remains for inspection and
is not automatically restored. Keep dumps private; they contain actual logs.

Restore checks the manifest checksum, creates a **new unique**
`logsense_restore_<12 hex>` schema and a fresh user scoped only to that schema.
It executes the dump through that limited user, not root. An existing schema
is never cleared or selected as a restoration target. It retains a private
credential receipt; no restore user/database is automatically deleted.

After restore compare every table's row counts and canonical row checksums,
raw/source provenance, migration version and FK consistency before intentionally
reconfiguring a reader to the new schema. A successful CLI exit alone is not a
data validation. This task compared all 24 tables (23 domain + Alembic) after
restart and after restoring a real 1K BGL import; checksums matched.

Live filesystem copying of the InnoDB data directory is not this backup method.
This local backup is not an off-device backup/PITR solution. Transport encryption
and production secrets/retention policies require separate deployment work.

## Moving development between Windows and macOS

Clone code; create a fresh native venv and native MySQL runtime. Do not copy the
Windows executable, venv, absolute-path config or live data directory to macOS.
Use a verified logical dump and a new isolated restore schema. Recreate local
roles and inject new private credentials. UTC, utf8mb4 and microsecond database
types are platform-independent. Retrain or explicitly verify ML artifacts with
matching Python/sklearn versions instead of assuming joblib portability.

For browser regression on macOS, install the Playwright QA tool/browser in the
venv and set `LOGSENSE_BROWSER_CHANNEL=chromium`; Windows defaults to installed
Edge. Existing QA scripts accept a private `LOGSENSE_QA_OUTPUT` directory.

Remaining NOT RUN: macOS native startup/migration/import/browser/restore, remote
database/TLS deployment, abrupt OS/power-loss recovery and off-device restoration.
