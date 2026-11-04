# Investigation V3 architecture review

Status: **Proposed; no application/database migration implemented.**

Start with [V3 proposal](INVESTIGATION_V3_PROPOSAL.md). Supporting documents cover
[data/query/coverage design](V3_DATA_AND_QUERIES.md),
[new API contract](V3_TIMELINE_API.md), and
[methodology plus measured fixture baseline](../benchmarks/v3/REPORT.md).

| Requested deliverable | Location |
|---|---|
| Current architecture assessment | Proposal section 1 |
| Data volume model | Proposal section 2; data model |
| Timeline V3 API | API specification |
| Query/index strategy | Data/query document; no EXPLAIN claimed |
| Detector grouping | Proposal section 4 |
| Coverage model | Data/query document |
| Benchmark methodology | Benchmark report + workload-matrix.json |
| Actual results | Benchmark report + fixture-baseline.json; six-anomaly fixture only |
| Bottleneck report | Proposal section 6 and measured payload/profile observations |
| Roadmap and cost/complexity | Proposal section 7 |

Benchmark prerequisites are recorded in
[environment.json](../benchmarks/v3/environment.json).
The [read-only baseline script](../../scripts/benchmark_investigation_v3.py)
does not create/connect to any DB. The 10K/100K/1M parsed-event MySQL matrix remains
unexecuted because no approved running isolated database is available.
