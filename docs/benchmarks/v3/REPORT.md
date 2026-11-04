# Investigation V3 — benchmark methodology and measured baseline

Date: 2026-11-03, Asia/Ho_Chi_Minh. **Architecture/reporting task only.**
No application changes, DB migration, database creation, import or infrastructure
startup. Raw research archives and user data are untouched.

## Execution status

| Test layer | Status | Meaning |
|---|---|---|
| Existing correctness suite | See `unit-test-report.txt` | Fixture/API regressions only |
| Current API, six synthetic anomalies | Executed, 11 cases, 60 timed HTTP repetitions each after 5 warmups | A V2 fixture baseline, not a large-data benchmark |
| Current browser DOM, six synthetic anomalies | Executed, 2 cases, 60 timed repetitions after 5 warmups | DOM replacement/chart setup, not full end-to-end interaction latency |
| MySQL EXPLAIN/index/storage | NOT EXECUTED | No reachable approved isolated DB target |
| 10K / 100K / 1M parsed events | NOT EXECUTED | No SQLAlchemy repository/schema, MySQL server/connection or SQL driver |
| Cold DB cache, concurrent large-data load | NOT EXECUTED | No DB; no cache reset or infrastructure operation performed |

Environment check: no mysql/mysqld commands, MySQL/MariaDB service/process or
3306/33060 listener detected. Docker CLI is installed, but `docker info` cannot
connect to the Docker Desktop Linux-engine pipe. SQLAlchemy/PyMySQL are not
installed. A remote server might exist but none was configured/provided here.
The machine's RAM/disk do not themselves establish a feasible isolated DB test.

## Actual fixture measurements

The workload has **6 anomaly fixtures and 4 logical detectors**. Raw lines, parsed
events and detection units are unknown/not stored; they are NOT six by inference.
The 120-bin case increases rendered aggregation size, not event/anomaly volume.

| Case | p50 HTTP ms | p95 HTTP ms | Max payload bytes | Bins / cells |
|---|---:|---:|---:|---|
| timeline_1h | 1.83 | 15.82 | 19,693 | 12 / 60 |
| timeline_24h | 2.23 | 22.31 | 39,191 | 25 / 125 |
| timeline_7d | 2.29 | 19.52 | 45,186 | 29 / 145 |
| timeline_30d | 2.30 | 18.45 | 48,187 | 31 / 155 |
| timeline_120_bins | 4.96 | 31.11 | 181,930 | 120 / 600 |
| timeline_entity_filter | 1.87 | 19.17 | 19,656 | 12 / 60 |
| timeline_empty_result | 1.93 | 25.34 | 19,608 | 12 / 60 |
| workspace_1h | 7.43 | 30.81 | 107,122 | 12 / 60 |
| workspace_120_bins | 52.77 | 76.29 | 869,706 | 120 / 600 |
| results_page | 1.73 | 16.26 | 1,183 | — / — |
| evidence | 1.92 | 17.20 | 3,797 | — / — |

Loopback serial HTTP against the owned threaded Werkzeug server; latency includes
request/body transfer, excludes client JSON decoding. `perf_counter`, nearest-rank
p95 (`ceil(.95*N)`, N=60), median p50. Warm Python/template/OS state; APIs specify
no-store. No SQL/cache/read-replica timing exists. This is a shared Windows host
without CPU isolation, so tail scheduling noise and the small sample must not be
interpreted as a production SLO or confidence interval. Raw samples are retained.

| Browser case | Cells | DOM nodes | HTML bytes | p95 DOM/setup ms | p95 second-frame proxy ms |
|---|---:|---:|---:|---:|---:|
| workspace_1h | 60 | 609 | 79,801 | 3.40 | 12.60 |
| workspace_120_bins | 600 | 1797 | 650,232 | 11.80 | 22.20 |

Browser: headless Microsoft Edge at 1440x900. The same fetched server-generated
HTML is reused for each repetition; timing includes DOM replacement and
`initializeChart()`, excludes fetch/JSON decode. A second-requestAnimationFrame
duration is a frame-scheduling proxy, not a guarantee of completed paint. This is
not measured multi-detector/large-source rendering or a browser memory benchmark.

Measured Python process peak working set before browser: **65,613,824 bytes (62.57 MiB)**. Instrumented one-service-build Python allocation peak at 120 bins: **618,604 bytes**. These measure different scopes. SQL/database/browser peak memory: not measured.

Windows peak working set is a process-lifetime high-water mark of the Python
benchmark/server process before browser startup, not per-query RSS delta or SQL
memory. [Microsoft memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters).
The instrumented Python build uses tracemalloc and does not include all native,
browser or database allocations. [Python tracemalloc](https://docs.python.org/3/library/tracemalloc.html).

## What the baseline establishes

- Correctness assertions checked Overall sum and all four detector-row sums
  against scoped anomaly counts on every applicable measured response.
- Increasing bins creates substantial repeated HTML/JSON/link payload even with
  only six anomalies. This supports evaluating the proposed compact data contract;
  it does not establish a MySQL bottleneck or justify another database.
- cProfile covers 30 fixture service builds: see `fixture-profile.txt`. Redaction,
  display formatting and repeated timestamp conversion are visible work at this
  size. Instrumented timings are not ordinary HTTP latency and do not forecast
  million-row cost; source inspection establishes the unbounded materialization.
- No p95 <2s large-data target is declared met. No database-size estimate, SQL
  execution measurement or million-event throughput number is fabricated.

## Reproduce the executed baseline

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_investigation_v3.py --repetitions 60 --browser
```

Flask/tzdata are existing runtime dependencies; Playwright and installed Edge are
local QA utilities. The script uses an ephemeral loopback port, stops its server
in `finally`, never connects to a database and verifies hashes of application,
test, config and requirement files before/after. Results: `fixture-baseline.json`.
It intentionally cannot be used as a 1M parsed-event/MySQL benchmark runner.

## Proposed isolated SQL benchmark methodology

This protocol is **not executed**. It is the next approved measurement gate.

### Isolation and staged execution

1. Provide a dedicated MySQL benchmark instance/database and restricted benchmark
   user. The harness must require a benchmark database-name prefix, a unique
   manifest marker and matching server identity; reject any production/user DB.
   Never enumerate/drop databases or write outside the marked benchmark schema.
2. Record exact server/driver/SQLAlchemy versions, hardware/storage, connection
   pool, buffer-pool size, page-size/collation, SQL modes, UTC session and app
   commit/source hash. Credentials come from environment/secure input and are
   neither printed nor written into result artifacts.
3. Create the APPROVED benchmark schema only, seed 10K parsed events in batches,
   and verify all counts and oracles before performance repetitions.
4. Run 100K only after correctness and resource limits pass; run 1M only after
   100K passes. Stop on count errors, disk pressure, memory budget violation,
   repeated timeouts or unexpected DB identity. Keep partial result status honest.
5. Cleanup is a separate explicit operation on the verified isolated schema; this
   report does not authorize deletion or provisioning of any instance.

### Data generation and cardinalities

Use deterministic seed 2704, a fixed 30-day UTC interval, immutable dataset ID and
manifest digest. Record R/P/U/E/A separately for every workload. Core event-based
workloads use exactly P=10K/100K/1M parsed events; U=P event units shared across D
detectors; E=P*D synthetic evaluations. Generate flagged outputs separately from
parsed input. This benchmarks storage/query performance, not detector accuracy or
real ML execution throughput.

One reproducible exact selection algorithm: for each detector choose seeded a,b
with gcd(a,P)=1; the permutation `(a*i+b) mod P` defines unit rank. Flag the first
`floor(P*rate_ppm/1_000_000)` ranks. A=D*K exactly for this core workload. Reusing
the permutation nests rates without changing P. Rate is explicitly per evaluated
unit, not per raw line or per parsed event across all detectors. Keep each output's
run/unit/signal uniqueness invariant.

Raw fixtures are a separate input stream: R=P+floor(P/49) physical single-line
records, with exactly floor(P/49) quarantined malformed lines and P successful
one-to-one parsed events. Additional correctness workloads exercise multiline,
multiple parser outputs, event/window/session units and unknown timestamps. Do
not assume the core R/P or U/E ratios apply to those workloads.

Use a uniform profile and a hot-burst profile (e.g. 80% parsed events and eligible
flagged units in one explicit hour). Validate available unit-pool sizes before
assigning exact anomaly counts; never duplicate units to fake a requested rate.
Include actual boundary timestamps and microseconds, same timestamp/different ID,
long intervals, and DST label cases in the correctness oracle dataset.

### Matrix and query cases

Declarative configuration: `workload-matrix.json`.

- Core: 3 parsed sizes * 3 per-evaluation anomaly rates (0.1%, 1%, 10%) * 4 ranges
  (1h,24h,7d,30d) * 2 time profiles = 72 cells.
- Empty filters: one known-empty query per size/range = 12 additional cells.
- Factor sensitivity, not an automatic full Cartesian product: D=32/128; host
  counts 4/100/1000; service counts 2/10/50; hot-entity skew; short/long query
  text; selective host/service/detector/priority/run combinations. Start these at
  100K and extend selected worst cases to 1M if resources permit.
- Add repeated identical queries and randomized round-robin query order. Scope
  expected counts come from the generator's independent streaming oracle, not
  the production aggregation implementation under test.

Capture timeline, list, facets, CSV and evidence scope parity. For intervals,
verify exact anchor-start counts and explicitly separate overlap-active counts.
Test multi-entity/session joins for fanout and filtered facets for own-dimension
exclusion. Refresh/publish a late batch and reanalysis version; reject stale
revisions or serve a retained pinned snapshot consistently across every endpoint.

### Metrics and repetitions

- API p50/p95: at least 100 warm timed requests/cell after 10 warmups, 3 separate
  rounds/processes. Preserve raw samples; record failures/timeouts separately,
  never drop them to improve quantiles. Do not average p95 values into a fake
  global p95; report per-cell/round distributions or a correctly pooled sample.
- SQL: ordinary execution/fetch timing plus DB-side Performance Schema where
  enabled. Separately save EXPLAIN JSON/ANALYZE, actual/estimated rows and loops,
  sort/temp/spill indicators. ANALYZE instrumentation is a separate measurement.
- Memory: process RSS/working-set high-water mark, per-worker allocation traces
  and DB memory/config; fresh worker per workload distinguishes process history.
  Measure import and query phases independently, including driver buffering.
- Payload: exact uncompressed JSON bytes, optional compressed wire bytes and
  row/bin/field cardinalities; no full raw-log response. Keep long labels/filter
  arrays and full allowed page sizes in payload tests.
- Storage: table data/index bytes and total benchmark DB allocated bytes after
  import/checkpoint; report redo/undo/temp/backup separately, not payload formulas.
- Browser: representative pre-fetched aggregate renders at target widths, paint/
  interaction proxies and DOM counts, plus response-to-visible timing. Browser
  peak memory only if instrumentation can actually measure it.

Warm: explicit priming pass, stable buffer pool/OS state reported. Cold: only on a
dedicated approved instance, with documented restart/buffer-pool preload and OS
cache conditions; restarting an app alone is not cold MySQL. If true cold control
is unavailable, label the first-query condition precisely and leave cold-cache
results unmeasured. Never restart a shared/user DB for benchmark convenience.

### Proposed targets, not achievements

| Target | Initial workload / check |
|---|---|
| Timeline p95 <2s | 1M parsed events, D4, 100 hosts, 10 services, 0.1% flagged evaluations, 24h and 30d, <=120 bins/12 visible rows, warm serial approved MySQL workload |
| Stress visibility | Same workload at 10% flags, bursts, 32/128 detectors and selective filters; report all results, do not hide slower cases behind the base target |
| Timeline payload <=512 KiB | Proposed compact v2 JSON, bins<=120/rows<=20; exact counts, bounded names/metadata; independent of raw-line payload size |
| Bounded app memory | Initial isolated query-worker budget <=512 MiB above startup baseline, import batch <=1000 rows; refine with measured row sizes and available memory |
| Correctness | All raw/parsed/unit/output counts and independent aggregation/filter/export oracles exact; no silent partial results |
| Responsiveness | No full raw transfer; existing cancellation/stale-response behavior preserved; representative prefetched render target p95 <=100ms on recorded laptop-class hardware |

The measured V2 composite 120-bin response and the PROPOSED V3 timeline response
have different contracts; do not mark the V3 payload target failed/passed by
comparing them without that distinction. The V2 number identifies optimization
opportunity, not a validated replacement implementation.

## Stop boundary

The architecture and fixture baseline report are complete. MySQL 10K/100K/1M,
SQL execution, indexes and physical DB size remain unmeasured. No new production
capability is claimed; provision/implementation requires the next approved scope.
