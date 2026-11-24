# Real BGL University MVP E2E verification

Date: 2026-11-04. **Functional chain: PASS. University MVP v1.0 release: HOLD.**
The unchanged Master Plan still requires full dataset CRUD, validated HTTP upload/REST ingestion and Flask-WTF. This test demonstrates the existing operator-import workflow; it does not declare absent features complete. No push/merge/tag occurred.

## Workload and environment

Actual immutable Loghub BGL first 100,000 lines in a newly migrated schema on a dedicated native MySQL 8.4.7 runtime, loopback port 13307. A second real 1K dataset is deliberately unauthorized; a third authorized dataset is empty. The retained application MySQL on 13306 was not restarted or changed and remained ready. Python 3.10.11 / Windows build 26300, Edge headless, local storage. No external SMTP was enabled.

Fresh migration 0001→0004 passed with no ORM/schema diff. The same rule and IF jobs ran outside HTTP requests; native parameters and thresholds were not tuned. This is a functional replay of the known 100K workload, not a new independent ML quality experiment.

## Measured chain and consistency

| Stage | Result | Evidence |
|---|---|---|
| Import/parse/MySQL | PASS | 100,000 raw records, parsed events and original labels; zero malformed/duplicates in this prefix |
| Rollback/resume | PASS | Failure before 1500 commit preserved 1000 checkpoint; resume reached 10K and 100K |
| Full source verification | PASS | Every raw byte, timestamp, Node, message, label, line and byte offset matched the archive prefix |
| Feature extraction | PASS | 90,334 observed host-window vectors per detector: 11,165 train / 60 validation / 79,109 test |
| Rule worker | PASS | 79,109 persisted predictions, 153 flagged outputs; stored unit/version/threshold/evidence |
| IF worker | PASS functionally | 79,109 persisted predictions, 5 flagged outputs; lower native score is anomalous |
| Counts | PASS | 79,109 persisted test units, 158,218 predictions, 158 detector-output facts, 153 unique flagged units |
| Timeline/results/CSV | PASS | All table-page IDs and full/selected CSV IDs equal independent SQL facts; selection adds to global scope |
| Filter matrix | PASS | 42 cases: host OR, priority, detector/run/version, time boundaries, literal search, AND, selection clear, timezone, empty/unknown coverage, cursors and isolation |
| Real Evidence Drawer | PASS | Actual source provenance, redacted raw text, model/rule version/threshold; root_cause remains null; close retains context/focus |
| Errors/recovery | PASS | Invalid input 400, unauthenticated/otherdataset/missing CSRF 403, missing evidence 404; network retry retains labeled scope |
| Restart | PASS | All 24 table count/SHA-256 records match; full and selected CSV bytes unchanged; identities persist |
| DB outage | PASS | Health/private query 503, DEMO 200; same app/pool reconnects and returns 158 facts |
| Model usefulness | FAIL for alert readiness | DefaultIF recall 0 on this test; passing software checks do not establish useful detection |

The 158 count is detector-output facts, not 158 unique incidents. A unit flagged by both detectors legitimately yields two facts; there are 153 unique flagged units. Window anchor is start; full-window features become available only after window end. Coverage remains unknown: absence of an observed anomaly is not a proof of healthy/missing-free source data.

Raw/source prefix SHA-256: `d6b55a02a67d9ab027abae4b60c365edbf9a892fcb6810ff780528512ca01c83`.
Full anomaly CSV SHA-256 before/after: `46854cc05da8ac27314ad36c1bcf8b005afcf588f051c269a5e5a0b3010b5e92`.
Selected CSV SHA-256 before/after: `17e04dd28573c1f88a1df4e36cae32def2d1aa4480788464744fb488b0a23deb`.

## Latency and memory

| Operation | Actual time |
|---|---:|
| Import target 1K |0.367s |
| Resume 1K→10K (9K additional) |1.508s |
| Resume 10K→100K (90K additional) |13.262s |
| Full 100K byte/field/label verification |9.115s |
| Repeat unchanged 100K import |0.058s |
| Rule worker total |165.387s |
| IF worker total |117.463s |
| QA graceful stop / start |2.318s /3.087s |
| Same-app recovered query (in process) |0.098s |

Import timings are separate resume calls, not a fresh single-call 100K benchmark. Each includes its validation/checksum/commit work. There is no invented uninterrupted total pipeline/defense time.

| Worker | Feature stream | Model fit | Scoring | Persistence | Evaluation | Sampled peak RSS |
|---|---:|---:|---:|---:|---:|---:|
|Rule|1.439s|0.000s|0.000s|158.744s|4.515s|669.8MiB|
|IF|1.363s|0.071s|0.908s|110.508s|4.601s|673.1MiB|

Feature streaming includes DB reads. Persistence contains scoring and SQL, so timings overlap and must not be summed. RSS samples every 20 ms describe only the worker process, not total MySQL/browser/system memory. Existing per-unit ORM persistence dominates: rule 478,389 SQL statements / IF 318,057. Bulk persistence and bounded evaluation memory are measured backlog work, not changes made here.

| Warm loopback HTTP endpoint | Before p50/p95 ms | After p50/p95 ms | Samples per phase |
|---|---:|---:|---:|
|Logs (50 rows / 100K scope)|28.51/37.24|28.36/35.02|12|
|Anomaly timeline (158 facts)|30.23/30.61|29.79/30.50|12|
|Investigation JSON+HTML|38.20/50.72|38.81/52.17|12|
|Actual selected evidence|18.00/19.04|18.65/19.31|12|
|Selected anomaly CSV (4 facts)|11.39/12.80|11.35/12.32|12|

HTTP timing includes receiving the complete body through authenticated Playwright requests. Samples are single-user/warm on this local machine; p95 uses linear interpolation of 12 observations. These are not a concurrency benchmark, SQL-only timing, universal latency guarantee or 1M-anomaly workload.

Login-to-log ready: before216.3ms/after324.3ms. Investigation navigation-to-observed-ready: before692.5ms/after706.7ms. These include server/assets/JS and QA observation, not isolated paint CPU.

## Fresh tests, UI fix and unverified items

- Default discovery: 166 total, 110 PASS, 56 explicit MySQL skips; final runner 8.796 s.
- Guarded suite: 63/63 PASS, including 56 unique MySQL tests plus 7 pure guards; 10.319 s wrapper wall. Do not add duplicate tests into an inflated total.
- Real browser: 12 groups before and 12 after the final restart; zero page errors, 1366/1440/1920 checks. DEMO regressions: 21 workspace + 13 drawer groups PASS, separately labeled synthetic.
- Post-final-restart filter matrix: 42/42 PASS. Duplicate output-name protection refused a repeated filter run; a new explicit report filename was used, retaining earlier evidence.
- A real-data visual review caught the full-range selector incorrectly labeled 60 min. It now says Full imported range for MySQL, while DEMO retains its sample label. Missing host/service now says Unavailable rather than None. Only two Jinja expressions changed; layout/JS/API/schema are retained. Final real / DEMO regression checked the changes.
- NOT RUN: native macOS, external SMTP delivery, manual screen reader, full BGL archive / 1M chain in this task, manual timed defense rehearsal, production deployment, official lecturer rubric. Prior 1M measurements remain historical evidence.

## Reproduce and inspect

Use the exact commands in [DEMO_SCRIPT.md](../database/DEMO_SCRIPT.md). The fresh QA context is single-use and retained; do not reset/remove existing state to force setup. Credentials/raw/model artifacts/screenshots stay under ignored .local. All owned test data is retained. The QA runtime can be stopped without deleting files.

- [Structured summary](measurements/university-mvp-v1/e2e.json)
- [Import/provenance/migration/EXPLAIN](measurements/university-mvp-v1/setup.json)
- [Rule stages](measurements/university-mvp-v1/detect-rule.json) / [IF stages](measurements/university-mvp-v1/detect-isolation_forest.json)
- [Before SQL checksums](measurements/university-mvp-v1/verify-before.json) / [after](measurements/university-mvp-v1/verify-after.json)
- [Before real browser](measurements/university-mvp-v1/browser-before.json) / [after](measurements/university-mvp-v1/browser-after.json)
- [Restart/outage](measurements/university-mvp-v1/restart.json)
- [42-case final matrix](measurements/university-mvp-v1/filter-matrix-final.json)
- [Default tests](measurements/university-mvp-v1/unit-tests.json) / [guarded MySQL](measurements/university-mvp-v1/mysql-tests.json)
- [Release gates](UNIVERSITY_MVP_V1_PLAN.md) / [deferred enterprise and research](BACKLOG.md)
