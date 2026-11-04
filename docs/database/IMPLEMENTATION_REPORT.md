# LogSense AI: implementation and final QA report

Date: 2026-11-04. Scope includes the authorized database foundation, real BGL pipeline, Log Explorer, observed-window jobs/evaluation, MySQL Investigation V2, minimum authentication and incident workflow. No push/merge.

## 1. Executive status

**DONE:** local implementation and measured QA described below. **FAIL for production/model readiness:** both baselines remain insufficient, especially window IF recall=0. **NOT RUN:** native macOS, external SMTP and manual screen reader. The full eight-week roadmap is **PARTIAL**, not declared finished.

| Area | Status | Evidence |
|---|---|---|
| database models migrations fk | PASS | Numerical reports/source tests in this directory |
| bgl parser streaming ingestion resume | PASS | Numerical reports/source tests in this directory |
| real source bytes labels fields 1M | PASS | Numerical reports/source tests in this directory |
| log API snapshot pagination csv | PASS | Numerical reports/source tests in this directory |
| real investigation and evidence | PASS | Numerical reports/source tests in this directory |
| authentication dataset permissions csrf | PASS | Numerical reports/source tests in this directory |
| window models reproducibility and evaluation | PASS | Numerical reports/source tests in this directory |
| alerts audit cooldown smtp mocks | PASS | Numerical reports/source tests in this directory |
| operational detector quality | FAIL: experimental rule/IF are insufficient; window IF recall is zero | Numerical reports/source tests in this directory |
| mysql restart backup restore windows | PASS | Numerical reports/source tests in this directory |
| macOS native execution | NOT RUN | Numerical reports/source tests in this directory |
| external SMTP delivery | NOT RUN | Numerical reports/source tests in this directory |
| manual screen reader | NOT RUN | Numerical reports/source tests in this directory |
| HTTP upload | NOT IMPLEMENTED; endpoint absent and request-size rejection tested | Numerical reports/source tests in this directory |
| full eight week roadmap | PARTIAL; see TRACEABILITY.md | Numerical reports/source tests in this directory |

## 2. Initial audit and verified fixes

The starting clean branch was `feature/mysql-database-foundation` at `675c718`; the original 50 backend tests passed. No persistence/parser/import/model-result modules existed. V3 documents were proposals. Docker engine was unavailable; official native MySQL 8.4.7 ZIP was checked and provisioned privately without an OS service or global configuration. See [file/line audit](DATABASE_AUDIT.md). All original datasets and backups remain.

## 3. Architecture and count semantics

The existing Flask factory/Blueprint/Jinja architecture is retained. [Architecture](ARCHITECTURE.md), [23-table ERD](ERD.md) and [schema inventory](SCHEMA.md) describe actual modules and constraints. Dataset identity is enforced in SQL and RBAC. Raw source records, parsed events, evaluated units, stored predictions, anomaly-output facts and incidents are different counts. A million parsed events do not imply a million anomalies.

Raw epoch is authoritative UTC; printed timestamp, original bytes, Node/NodeRepeat and labels remain intact. Log pages/timeline/CSV share signed scope and event watermark. Anomaly views pin one completed run per logical detector; intervals use exact UTC microseconds and grouped integer DIV, counting outputs once at their anchors. Missing/unknown time coverage is never converted into a health claim.

## 4. Files and modules

- `app/extensions.py`, `database.py`, `models.py`, `domain.py`: MySQL/ORM/domain foundation.
- `app/parsers/bgl.py`, `services/bgl_ingestion.py`: bounded actual BGL parsing and checkpoints.
- `security.py`, `api/logs.py`, `services/log_queries.py`: roles/dataset ACL, snapshots and log reads.
- `services/window_detection.py`, `api/jobs.py`, `scripts/worker.py`: independent temporal training/scoring/evaluation jobs.
- `services/mysql_investigation.py`, `mysql_evidence.py`, existing API/template adapters: actual Investigation/Evidence with the same stylesheet/layout.
- `api/alerts.py`, `services/alerts.py`, inline `incidents.js`: scoped incidents/audit/cooldown/outbox.
- Four frozen migrations; unit/integration/browser/benchmark/lifecycle scripts and documentation.

## 5. Configuration and operating checks

Use [.env.example](../../.env.example) placeholders or the private runtime wrapper. No real credentials or .env are committed. Dev application has SELECT/INSERT/UPDATE only; a separate migrator has schema-scoped DDL. MySQL listens at 127.0.0.1:13306; UTC, InnoDB, utf8mb4. Default Demo Mode works without a MySQL server. Testing never falls back to the dev URL. Native Windows init/start/stop, pool reconnect, restart and new-schema logical restore were exercised. Mac setup/runbook is supplied but not executed.

## 6. Migrations and recovery

Head **0004**, 23 domain tables plus Alembic. Clean schema migrations and model reflection pass on fresh token-marked isolated schemas. No destructive downgrade, database/table drop, truncation or existing-volume reset was performed. Older temporary schemas remain at their original versions; they are not silently upgraded.

Final recovery check: real 1K BGL source; all 24 table row checksums match after restart and after isolated restore. Backup bytes: 871849; SHA-256: `86ac02b5c34289cc8e83987f938f17a19d5ca286c565c0957838a27daabbfed4`. The dump stays private under .local. This is local recovery evidence, not off-device/PITR coverage.

## 7. Tests and measured workloads

| Test group | Actual result |
|---|---|
| Default discovery | 125 discovered; 73 pass, 52 MySQL cases explicitly skipped/NOT RUN in this command |
| Guarded real MySQL suite | 52/52 PASS, zero skipped, migrations 0001..0004 and actual SQL/API/workflows |
| Original demo workspace browser | 21 groups PASS |
| Original demo Evidence Drawer browser | 13 groups PASS |
| Actual MySQL browser/E2E | 9 groups PASS, zero page errors |
| Automated axe-core | Three pages, zero reported violations; incomplete/manual checks remain |
| Compile, undefined-name/critical syntax lint, dependency check | PASS |

Thus 125 distinct Python cases were executed across the separate default and real-DB commands; the skip count is not misreported as a MySQL pass. Browser groups are separate from Python test counts. Actual tests include source/FK isolation, duplicate rejection, transaction rollback, JSON/bytes, exact time boundaries, signed cursor scope, CSV injection, auth/CSRF, deterministic scores, job leases, alert decisions/audit and SMTP mocks.

### Real BGL import measurements

Windows build 26300, Intel i5-14600K (20 logical CPUs), 34,039,918,592 bytes physical RAM, Python 3.10.11, MySQL 8.4.7, batch rows=500, raw-byte batch budget=8 MiB. Each workload uses a new isolated dataset. Source is the original archive prefix, not generated rows. The local server also hosted QA workloads; this is not a dedicated performance lab.

| Physical/parsed rows | Wall seconds | Rows/sec | Importer peak RSS MiB | Malformed | Duplicate provenance |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.381 | 2624.4 | 66.94 | 0 | 0 |
| 10,000 | 1.932 | 5175.2 | 68.64 | 0 | 0 |
| 100,000 | 25.078 | 3987.5 | 69.42 | 0 | 0 |
| 1,000,000 | 294.710 | 3393.2 | 70.88 | 0 | 0 |

Time includes archive hashing, validation and commits. Source/checksum verification is excluded from import timing. RSS is the Python importer only, sampled at 10 ms; it excludes mysqld and OS cache. Single import runs do not establish a latency p95. Separate 20-request API samples follow.

Every imported raw byte, physical position, label category, epoch UTC, printed time, host/component/level and parsed content was compared against the source for the 10K/100K/1M datasets. The one-million prefix has SHA-256 `51cdd00c485ba0f1af049e3dbce93027e4814432e97bb2e05ddfe69bb3c4bd65`. Raw/event/label counts all equal 1,000,000, malformed=0 and duplicates=0. Malformed-row behavior is exercised separately with explicit controlled fixtures, not invented errors in the real prefix.

Actual interruption: an owned worker used os._exit(77) before the 50,000th-line batch committed. Checkpoint remained 49,500; resume finished 100,000 lines with no duplicate, equal source hash and recovered stale job. Caught-exception rollback/retry is also recorded.

### Loopback HTTP API and SQL measurements

Twenty sequential warm requests per endpoint/dataset, login excluded. p95 uses nearest rank. These are loopback HTTP measurements; SQL duration and payload/memory are recorded separately in [raw profile](measurements/api-performance.json).

| Endpoint/workload | p50 ms | p95 ms | Maximum payload bytes |
|---|---:|---:|---:|
| /api/v1/logs / 10,000 parsed events | 9.13 | 27.89 | 11,495 |
| /api/v1/logs/timeline / 10,000 parsed events | 10.51 | 32.03 | 7,130 |
| /api/v1/logs / 100,000 parsed events | 25.94 | 42.31 | 11,655 |
| /api/v1/logs/timeline / 100,000 parsed events | 50.74 | 51.36 | 7,161 |
| /api/v1/logs / 1,000,000 parsed events | 189.79 | 846.59 | 11,764 |
| /api/v1/logs/timeline / 1,000,000 parsed events | 453.33 | 471.12 | 7,269 |
| /api/v1/investigation / 158 anomaly outputs | 34.74 | 55.20 | 181,102 |

API process peak RSS: 83.96 MiB, including the local client/server in one Python process, excluding mysqld. Page size was 50; browser/API caps remain 100. The log-volume API aggregates in MySQL. The anomaly profile covers 158 facts on a 100K-log dataset; **one-million anomaly outputs were NOT tested**. Actual EXPLAIN/ANALYZE/index plans are retained. A matching pre-implementation real endpoint did not exist, so a same-workload before comparison is NOT RUN; fixture latency is not a valid speedup claim.

### Model/evaluation measurements

Both new runs use observed host windows, chronological 50/25/25 time boundaries, actual split counts train=11,165 / validation=60 / test=79,109, label-blind fitting/calibration and a test-only original-label window target. The sparse prefix is not representative or complete source coverage.

| Model | TP | FP | FN | TN | Precision | Recall | F1 | Average precision | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| rule | 92 | 61 | 437 | 78519 | 0.601307 | 0.173913 | 0.269795 | 0.177245 | 0.000776 |
| isolation_forest | 0 | 5 | 529 | 78575 | 0.000000 | 0.000000 | 0.000000 | 0.254564 | 0.000064 |

These are observed-window metrics. Earlier event-level baseline results remain in detectors.json and are **not mixed** with this table. AUPRC is sklearn average precision from all eligible scores, not only flagged outputs. Window IF has zero recall at its calibrated threshold; both models fail readiness for operational alerting. No test-label tuning or fabricated feature importance/root cause is claimed.

## 8. Security and privacy

Private reads require dataset permission; mutations require current role and CSRF. Credentials are injected privately, passwords hashed, cookies HttpOnly/SameSite, HTTPS Secure flag documented. Logs use text rendering and redaction before raw pagination. CSV formula prefixes are escaped. SQL binds values; IDs, time, page/cursor and archive paths are validated. Upload endpoint is absent and oversized requests rejected. SMTP is disabled unless explicitly configured; tests send mocks only. Actual-data screenshots, archives, model files, MySQL files/dumps and credentials stay ignored. Security scan compares prospective Git bytes with actual local secret values without echoing secrets. These checks are not a penetration-test certificate.

## 9. Limits and roadmap gaps

Native macOS and external SMTP remain NOT RUN; screen-reader certification, production/TLS deployment and off-device recovery are not claimed. HTTP upload/REST ingestion, full user/dataset CRUD UI, Flask-WTF, supervised baseline, Tkinter utility, presentation deck, dark theme and full V3 publication/retention are incomplete/deferred. White UI is an explicit user constraint. Login throttling is process-local, email at-least-once, audit application-level, and worker recovery is explicit rather than distributed scheduling. [Traceability](TRACEABILITY.md) distinguishes these from official course grading.

## 10. Git and preservation

Branch: `feature/mysql-database-foundation`. Starting head: `675c718`. Implementation commit: `d29a781ff34e457c3ae18522269491f4c4a798b2`. The code/test implementation above is committed locally. This verification report is finalized in a separate documentation commit; its HEAD is available with git log. Working tree is checked clean afterward. No remote configuration change, push, merge, reset or cleanup of original data is authorized/performed. Existing main stylesheet bytes are unchanged; the original V2 layout is preserved with the specifically requested real adapters and inline controls.

## 11. Prioritized next work

1. Improve sampling/validation representativeness and threshold/model research; preserve a genuinely unseen test split. Do not optimize against this reported test set.
2. Execute the native macOS runbook/tests and a separately authorized real SMTP check.
3. Confirm lecturer criteria, then close the required upload/CRUD/Flask-WTF/supervised/Tkinter gaps; do not claim Flask satisfies Tkinter.
4. Review/publish only after explicit permission; production identity, TLS, retention and deployment require separate validation.

Private screenshots: `.local/database-verification/platform-browser/` (logs and Investigation at 1366/1440/1920). [Demo script](DEMO_SCRIPT.md), [API](API.md) and numerical JSON receipts are included; no real credentials are embedded.

Tracked files after implementation: 179. Private runtime/datasets/model artifacts remain ignored. No GitHub publication occurred.
