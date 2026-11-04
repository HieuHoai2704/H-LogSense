# Final source and MySQL audit

Baseline: clean `feature/mysql-database-foundation`, HEAD `675c718`. MySQL persistence/parser/import/detector modules were absent; V3 documents were proposals. Original 50 tests passed. Subsequent requests explicitly authorized the completed platform work. Existing data is retained; no push or merge.

| Priority | Verified finding | Current source | Resolution | Evidence |
|---|---|---|---|---|
| P0 | No persistence existed in the baseline | [app/database.py:13](../../app/database.py#L13) | Optional shared MySQL/UTC/strict mode, no startup DDL | Clean four-revision migrations and real reflection |
| P0 | Private access needed an authentication foundation | [app/security.py:35](../../app/security.py#L35) | Hashed login, per-dataset grants, CSRF and roles before opening real data | RBAC/API and actual browser cases |
| P0 | Ownership cannot depend only on UI filters | [app/models.py:53](../../app/models.py#L53) | Composite scoped SQL foreign keys and run/version identity | Actual cross-dataset FK rejection and rollback |
| P0 | Integer-bin change initially lost arithmetic grouping | [app/services/mysql_investigation.py:268](../../app/services/mysql_investigation.py#L268) | Explicit integer DIV precedence, UTC microseconds and half-open bins | SQL grouping proof plus exact/before-boundary tests; no decimal-rounding defect claimed |
| P1 | Unique names and DOUBLE reflection needed MySQL semantics | [app/extensions.py:13](../../app/extensions.py#L13) | Correct compound unique names and native DOUBLE mapping | Alembic reports no model/schema drift |
| P1 | NodeRepeat must not replace original Node | [app/parsers/bgl.py:24](../../app/parsers/bgl.py#L24) | Keep both node fields and separate epoch UTC/printed time | Parser tests and every label/field checked on 1M actual rows |
| P1 | Row cap alone did not bound long-line memory | [app/services/bgl_ingestion.py:184](../../app/services/bgl_ingestion.py#L184) | 8 MiB raw-byte budget plus line/row caps | Large-line, rollback and resume tests |
| P1 | Interrupted jobs needed ownership and recovery | [app/services/bgl_ingestion.py:45](../../app/services/bgl_ingestion.py#L45) | Connection-owned leases, checkpoints and retry that blocks active workers | Actual os._exit(77) import proof and job-lease cases |
| P1 | Page/bin/CSV scopes could disagree after append | [app/services/log_queries.py:39](../../app/services/log_queries.py#L39) | Signed scope, event watermark and keyset cursor shared by all reads | Append-exclusion, literal search, scope and CSV tests |
| P1 | Replay/source switching could retain stale runs | [app/services/mysql_investigation.py:143](../../app/services/mysql_investigation.py#L143) | One completed run per logical detector; explicit/empty snapshots and source reset | Repeated-run and browser dataset-switch cases |
| P1 | First metric query repeated correlated EXISTS scans | [scripts/verify_detectors.py:77](../../scripts/verify_detectors.py#L77) | Use distinct prediction IDs and one join; stopped only the owned read query | Stored confusion/evidence results verified; no data erased |
| P1 | Alert retries could release a suppressed backlog | [app/services/alerts.py:16](../../app/services/alerts.py#L16) | Durable created/cooldown decision ledger plus scoped anomaly/run FKs | Idempotency, incident/audit and SMTP mock tests |
| P1 | Dev application did not need DDL permission | [scripts/mysql_runtime.py:330](../../scripts/mysql_runtime.py#L330) | Separate migrator, dev app SELECT/INSERT/UPDATE only | SHOW GRANTS and isolated backup/restore proof |

## Remaining gaps and readiness

- **FAIL for model readiness:** window IF recall is zero on the measured test split. Passing software tests does not imply useful alerting.
- **NOT RUN:** native macOS, external SMTP, manual screen-reader certification, production/TLS deployment and abrupt OS/power-loss recovery.
- **PARTIAL/NOT IMPLEMENTED:** HTTP upload/REST ingestion, full user/dataset CRUD UI, Flask-WTF, supervised baseline, Tkinter utility and full V3 publication/retention/federated identity.
- Source-time completeness remains unknown. Window raw support is a bounded recorded sample, not all logs in the unit.
- SMTP is bounded at-least-once. Distributed scheduling/global login throttling and independent tamper-proof audit storage are not claimed.

See [final report](IMPLEMENTATION_REPORT.md), [status JSON](measurements/verification-summary.json) and [traceability](TRACEABILITY.md).
