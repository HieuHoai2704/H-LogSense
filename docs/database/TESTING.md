# Verification protocol

## Default suite (does not require MySQL)

```text
python -B -m unittest discover -s tests -q
python -B -m compileall -q app scripts tests migrations
```

MySQL tests are skipped unless explicitly opted in; a skip is **NOT RUN**, never
a database PASS. The original 50 demo/backend tests are retained unchanged.
Parser and database-unit tests cover byte preservation, epoch policy, malformed
UTF-8, offsets/CRLF/final line, missing host, Node versus NodeRepeat, safe text,
lazy reads, bounded line length, feature label independence, UTC conversion,
finite scores, URL validation and disabled-by-default real access.

## Actual MySQL integration

Privately inject MYSQL_ADMIN_URL and DATABASE_URL for the same owned server,
then run `python -m scripts.verify_mysql`. Neither URL is a command argument.
The application username must already exist at localhost. This harness creates
two **new** `logsense_test_<12 hex>` schemas and token-hash ownership markers,
grants only schema-scoped permissions and sets TEST_DATABASE_URL for its process.
It never drops, truncates or rebuilds an existing schema.

`tests/test_mysql_integration.py` additionally requires
`LOGSENSE_RUN_MYSQL_TESTS=1`, a correctly formatted schema name and a matching
`LOGSENSE_TEST_TOKEN`. A development URL cannot pass this guard. Fixtures are
retained; each test uses a new dataset. The second fresh schema is migrated
independently to prove reproducibility. The harness reports a skip as INCOMPLETE.

Integration cases include real connectivity/UTC, migration reflection, dataset
archive, byte/JSON persistence, exact half-open boundaries and keyset ties,
cross-dataset raw/event, membership, run/output and unit/output FK violations,
version identity, negative scores, duplicate rejection, full rollback, coverage
proof checks, instant/interval checks, block labels without invented events,
malformed import, atomic checkpoint rollback, source-change rejection, persisted
rule/ML output, protected actual evidence access, second clean schema, exclusive
import lease and interrupted-job recovery.

## Real BGL measurements

Use a new migrated `logsense_bench_*` schema. Run separate processes:

```text
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 1000 --output .local/bgl-1k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 10000 --output .local/bgl-10k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 100000 --output .local/bgl-100k.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 1000000 --output .local/bgl-1m.json
python -m scripts.benchmark_bgl --archive data/raw/BGL.zip --lines 100000 --resume --output .local/bgl-resume.json
python -m scripts.verify_import_restart --archive data/raw/BGL.zip
python -m scripts.verify_detectors --dataset DATASET_ID
```

The benchmark refuses a development schema and creates new datasets. Elapsed
ingestion time includes archive SHA-256, validation and database commits. Source
comparison and warm SELECT measurements are reported separately. RSS is sampled
every 10 ms for the importer process, not mysqld/OS cache or whole-machine RAM.
Single workload runs do not establish an ingestion latency p95. The query p50/p95
is over 20 warm, bounded event-page SELECTs, not a timeline benchmark.

Both injected exception and `os._exit(77)` worker-crash tests interrupt before
the line-50,000 commit; the committed checkpoint must remain 49,500. Resume and
retry compare all raw bytes/offsets/checksums/counts, not just final row count.
The crash fixture is genuine BGL data; the exit behavior is deliberately induced.

## Browser regression

Install Playwright separately as a QA tool. Set LOGSENSE_QA_OUTPUT to a new
private directory for each script, then run:

```text
python -B scripts/qa_investigation_v2.py
python -B scripts/qa_evidence_drawer.py
```

Windows defaults to Edge, macOS to the installed Playwright Chromium channel.
These two legacy scripts verify Demo Mode. `python -m scripts.qa_platform` adds login, real Log Explorer, MySQL Investigation/Evidence Drawer and incident E2E using private QA credentials. `python -m scripts.qa_accessibility` runs the pinned local axe-core scan; it is not screen-reader certification.

## Operations and security

Exercise initialize/start/stop in a new directory/unused port. Compare all-table
checksums across a graceful restart, logical backup and new-schema restore.
Check the app's development grant is SELECT/INSERT/UPDATE and migration DDL is
separate. Scan prospective Git content against actual private credential values,
ensure `.local`/datasets/artifacts are ignored, and verify frontend blob hashes
are unchanged. Do not print a secret while reporting a scan match.

The final real suite includes both `test_mysql_integration.py` and `test_platform_mysql.py`: schema/FK/rollback tests plus log snapshots, RBAC/CSRF, CSV injection, deterministic window runs, job retry leases, incidents, SMTP mocks and exact microsecond-bin boundaries. Default discovery reports these cases as NOT RUN unless the guarded harness enables them.
