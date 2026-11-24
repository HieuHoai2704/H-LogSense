# Validated BGL-compatible uploads and queued ingestion

The upload workflow stays inside the current Log Explorer workspace. HTTP
requests authenticate, validate and stage an immutable file, then queue work.
Database batch ingestion runs in a separate operator-started worker process.
Uploading a file is not the same as completing an import.

## Accepted formats and limits

| Input | Accepted content | Preservation / transformation |
|---|---|---|
| `.txt`, `.log` | UTF-8 BGL records with the existing ten-field BGL format | Original bytes, CRLF/LF and a missing final newline are preserved exactly inside the normalized container |
| `.csv` | Exactly one column named `raw_line`, containing supplied BGL record strings | Original CSV bytes are retained; each raw_line becomes one LF-terminated BGL derivative line with explicit CSV row/physical-line mapping |

Generic timestamp/message CSV schemas and unrelated log syntaxes are rejected,
not guessed. Upload validation does not fabricate timestamp, host, label, service
or other missing fields. CSV header UTF-8 BOM is accepted and recorded in the
retained original container; BGL TXT/LOG records must not contain a BOM.

Limits are 16 MiB original content, 16 MiB decoded BGL content, 200,000 rows and
262,144 bytes per BGL line. A CSV field has the same bounded character limit,
followed by the byte check after UTF-8 encoding. Multipart request size is capped
at 17 MiB to allow headers/form overhead. The larger request limit is applied
only to the upload request; other routes retain the existing 1 MiB limit.

Only one file and the supported scalar fields are accepted. Duplicate fields,
path-containing/control-character filenames, unsupported extensions, binary
control content, invalid UTF-8, embedded CSV record line breaks, empty files and
files with no valid BGL records are rejected. File extension or declared MIME
alone does not establish a valid format: content is inspected too.

A file containing at least one valid BGL record may also contain malformed text
rows. Those rows remain actual RawLogRecord bytes with parse_error; they do not
become invented LogEvent rows or labels. Status reports parsed and malformed
counts separately.

## HTTP and authorization

| Method / path | Behavior |
|---|---|
| POST `/api/v1/uploads` | Multipart fields: file, dataset_id, idempotency_key and signed csrf_token; 202 new queue item, 200 equivalent replay |
| GET `/api/v1/uploads/{upload_id}` | Authorized upload metadata, state, committed progress and provenance |
| POST `/api/v1/uploads/{upload_id}/retry` | Explicit retry/requeue of a recoverable failed or interrupted worker; 202 or 409 |

upload_id is a server-created 32-character lowercase hexadecimal UUID. It is
not a client filename, filesystem path or the integer job_id. The response
includes job_id and status_url for polling.

Submission/retry require an active analyst, manager or admin session, an
explicit dataset grant and the existing X-CSRF-Token header. Status reads require
an active viewer/analyst/manager/admin session and the same dataset grant. Admin
has no implicit access to another dataset. Read-only operator bearer tokens do
not gain upload permissions.

Submission additionally uses a real Flask-WTF UploadForm with its own signed
form CSRF token. Obtain that token through authenticated
`GET /api/v1/forms/csrf`, then include it as multipart csrf_token. The login's
session/header CSRF value and the signed Flask-WTF form token have different
purposes; do not replace one with the other. Neither form protection nor the
existing JSON mutation protection is globally disabled.

Requests must be multipart/form-data. JSON arrays/objects and text bodies are
rejected before constructing a Flask-WTF form. Errors return the existing JSON
error structure; invalid form responses include a field-to-message map without
echoing file bytes or credentials.

Common statuses: 400 invalid form/token/fields, 403 role/grant/header-CSRF denial,
404 unavailable upload ID, 409 conflicting idempotency/state or active worker,
413 size limit, and 422 unsupported or malformed content/schema. Database
failures use the existing redacted 503 handler. Unsupported extensions can be
rejected by the form before the content-validation layer.

## Immutable staging and original provenance

Server-generated storage is under ignored `.local/uploads/{upload_id}/`:

```text
original.txt / original.log / original.csv
normalized.zip
mapping.jsonl
manifest.json
```

User filenames never determine paths. Canonical containment and symlink checks
apply to directory/file access. No client-supplied server path, archive member or
upload directory is accepted. The worker reads a server-created ZIP container;
HTTP clients cannot upload arbitrary ZIP archives. No archive extraction occurs.

Before original bytes are written, each upload directory is restricted to the
current Windows account and SYSTEM with inherited ACLs removed, or mode 0700 on
POSIX. Permission setup failure rejects the upload; accepted source files are
never silently exposed through a fallback public directory. POSIX artifacts use
0600. Native Windows ACL execution and a simulated POSIX manifest-hash branch
were tested; this is not a native macOS execution claim.

Original bytes and SHA-256 remain available to the authorized local operator.
The normalized ZIP has the unique member `{upload_id}/BGL.log`, allowing multiple
immutable upload artifacts within one dataset without overwriting another
artifact. Its ZIP hash is distinct from original-file and uncompressed-content
hashes. The source artifact's archive SHA identifies this normalized container;
the original SHA is explicitly preserved as upload provenance.

CSV transformation removes at most one supplied terminal CRLF/LF/CR from a
raw_line field and appends one LF. Embedded remaining line breaks are rejected.
mapping.jsonl links each derivative BGL line/byte offset to its original CSV
logical row and physical CSV line span. **A derivative BGL byte offset is not an
original CSV byte offset.** No original CSV byte offset is invented.

Parsed event attributes carry an upload namespace with upload_id, original hash,
original filename, format, BGL line/offset and the applicable original text line
or CSV row mapping. Uploaded label provenance is `uploaded-bgl` / `supplied`:
these are user-supplied labels, not proof of an authentic verified Loghub archive.
Model evaluation must report the actual source and compatible detection unit;
the importer itself does not certify label correctness.

There is deliberately no HTTP original-file download route. Original content
may contain secrets. Existing redacted raw evidence/Log Explorer APIs remain the
HTTP investigation path; original files stay in operator-controlled storage.
Filename metadata is also passed through the existing display-redaction policy.
No claim of exhaustive secret/PII detection or filesystem encryption is made.

## Worker, progress and recovery

Run from the project root through the private runtime wrapper:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker
```

For one queued upload:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker --once
```

The existing `scripts.run.worker` continues processing detector analysis jobs;
`scripts.run.ingestion_worker` processes upload jobs. Starting the analysis worker
alone does not import queued files. The upload endpoint never starts a daemon
or imports the database inside a Flask request.

The outer upload ProcessingJob uses kind=parsing and an explicit upload type;
the existing batch importer creates its own kind=ingestion child job. This
prevents the importer's stale-ingestion recovery from marking its live parent
as interrupted. Status exposes both IDs and distinguishes per-upload rows from
the total dataset corpus.

The outer worker holds a connection-owned upload-job lease; the importer holds
its existing dataset lease. Two workers cannot process the same upload, and a
live lease prevents requeue. Process exit releases its lease. A deliberate retry
reuses the immutable member/checkpoint, so already committed batches are not
inserted again. Status can inspect the actual SourceArtifact checkpoint if a
crash occurred after the batch commit but before outer progress was updated.

Before every worker attempt and API retry, original, normalized ZIP, row-map and
queued manifest hashes are checked. Changed artifacts fail closed rather than
being silently overwritten. File-integrity failures are not retryable; other
manual retries are limited to three total worker attempts. A lease conflict is
reported separately from a generic ingestion/transaction failure.

The idempotency key is hashed into a bounded namespaced job key. The same
dataset/key/content/filename/format returns the same upload/job. A conflicting
replay returns 409, without replacing the accepted original. A new key means a
new source artifact; content deduplication across distinct keys is not claimed.
Only newly created, unaccepted staging copies are removed during rejection or
equivalent replay. Accepted originals, imported rows and audit jobs are retained.

## Verification

Pure staging/security tests:

```text
python -m unittest tests.test_upload_staging -v
```

Guarded API/worker tests:

```text
python -m scripts.qa.verify_mysql
```

Use private MYSQL_ADMIN_URL/DATABASE_URL environment values and the isolated
test-schema guards documented in [TESTING.md](TESTING.md). The upload integration
suite covers the queue boundary, byte/label/source mapping, both CSRF layers,
RBAC/isolation, a valid upload larger than 1 MiB, size limits, rollback/resume,
active leases, retry limits, idempotency and mutation detection. Fixture rows
and accepted original files are retained; only a test's own pending upload jobs
are marked failed in teardown to avoid contaminating the next queue test.

Read the actual run report for PASS/FAIL/NOT RUN. Pure validation tests are not
proof of MySQL, browser, native macOS, SMTP or detector quality. No migration,
push or merge is required by this upload module.
