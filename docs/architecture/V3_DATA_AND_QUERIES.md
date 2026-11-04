# V3 data model, coverage and query/index strategy

Status: proposed, not an applied schema or migration. MySQL target/version must
be confirmed before DDL is approved; MySQL 8.4 documentation is used as reference.
No EXPLAIN plan or database-size measurement has been executed in this audit.

## Domain and storage model

| Entity | Important fields and invariant |
|---|---|
| Dataset | ID, tenant/owner, mode, ingestion revision, retention policy; server-enforced read scope |
| Source artifact | Dataset, immutable checksum, storage reference, byte length, encoding, import manifest; no client file-path access |
| Import batch | Source, byte/line checkpoint, imported-line/quarantine counters, state, publication revision; idempotent source+offset keys |
| Raw record provenance | Dataset/source/batch, original timestamp string, byte offset/length, physical line range; one record may span lines |
| Parsed event | Dataset/batch, parser/version, UTC event timestamp, ingest timestamp, host/service IDs, template and narrow search projection |
| Event-source link | Dataset, event ID, raw record reference; supports zero/one/multiple parser outputs without equating line and event counts |
| Detection unit | Dataset, stable unit key/type/definition version, exact event anchor or window/session boundaries, grouping dimensions |
| Unit-event membership | Dataset, unit ID, event ID; many-to-many if needed; do not multiply anomaly counts through this join |
| Unit-entity membership | Dataset, unit ID, host/service/session IDs; unique membership rows, explicit filter semantics |
| Detector | Stable logical ID/slug, family, display name, unit policy; independent of versions |
| Detector version | Detector ID, rule/model version, feature schema/config hash, score semantics and priority policy version |
| Analysis run | Dataset, detector/version, input revision, evaluated-unit count, execution status, timings, coverage publication |
| Analysis snapshot | Dataset/input revision and published selected run set; immutable query manifest |
| Snapshot-run link | MVP unique snapshot+detector key and snapshot+run key: one published run per logical detector; later disjoint-shard run sets require explicit unit ownership |
| Anomaly output | Dataset, run, unit, detector, signal key, anchor UTC, priority, native score, evidence reference; unique run+unit+signal |
| Coverage segment | Dataset/input revision, detector/run where applicable, UTC interval, scope, state/reason, publication revision |

Use UTC `DATETIME(6)` for event/anchor/window times; configure connection/session
timezone UTC. Preserve original timestamp and parser interpretation separately.
Application conversion accepts explicit offsets/IANA display zones; ambiguous
local input must be disambiguated or rejected, not guessed.

Use numeric internal IDs and externally stable opaque/logical IDs. Foreign keys
must prevent cross-dataset references: composite `(dataset_id, referenced_id)`
keys or an equivalent verified constraint. Denormalized detector IDs on anomaly
facts must agree with the referenced run. Include foreign-key/unique-index write
costs in the index inventory rather than counting only explicit query indexes.

Persist only the normal evaluation data required by the project. An E=N*D count
does not require N*D full feature/output rows: completed-batch manifests and
per-run counters may suffice, while flagged outputs/evidence are persisted. Make
that retention choice explicit and preserve proofs of processed coverage.

## Streaming import and publication

1. Inspect archive members with size limits; stream content without extracting
   arbitrary member paths. Treat source files as immutable research inputs.
2. Iterate bounded chunks/lines, record encoding/parse errors and line/byte offsets.
   A final line without newline and multiline parsing have explicit count policies.
3. Batch parameterized inserts initially around 1,000 rows; tune by measured
   row bytes, packet limits, transaction time, worker memory and rollback cost.
4. Checkpoint a batch only after commit. Deduplicate retries by source/checksum,
   parser version and input offset. Counters change atomically with committed data.
5. Publish input revision and eligible records after validation; failed/uncommitted
   batches cannot appear as a completed import.
6. Analyse explicit units against a pinned input revision. Publish outputs and
   analysis coverage together. A retry cannot append duplicate flagged outputs.

Do not load full archives into a list/dataframe before filtering. Parquet may
later be an immutable batch feature/research artifact after its need is measured.

## Exact SQL query patterns

The following SELECTs are **illustrative specifications**, not executed SQL.
Bind parameters, validate/filter numeric IDs, and generate multivalue predicates
through SQLAlchemy rather than interpolating text. Every fact query includes
dataset authorization and selected input/analysis snapshot predicates.

Timeline anchor count (exact signed floor division, including pre-epoch instants):

```sql
WITH scoped AS (
  SELECT a.detector_id, a.priority,
         TIMESTAMPDIFF(MICROSECOND, '1970-01-01 00:00:00', a.anchor_utc) AS anchor_us
  FROM anomaly_outputs AS a
  JOIN snapshot_runs AS sr
    ON sr.run_id = a.run_id AND sr.analysis_snapshot_id = :snapshot_id
  WHERE a.dataset_id = :authorized_dataset
    AND a.anchor_utc >= :start_utc AND a.anchor_utc < :end_utc
    /* AND common validated host/service/priority/detector/search predicates */
)
SELECT detector_id,
       (anchor_us DIV :bin_microseconds)
         - (anchor_us < 0 AND MOD(anchor_us, :bin_microseconds) <> 0) AS bin_id,
       COUNT(*) AS anomaly_count,
       SUM(priority = 1) AS low_count,
       SUM(priority = 2) AS medium_count,
       SUM(priority = 3) AS high_count,
       SUM(priority = 4) AS critical_count,
       MAX(priority) AS max_priority
FROM scoped
GROUP BY detector_id, bin_id;
```

Use exact integer microseconds; no floating Unix timestamp calculation at bin
boundaries. `bin_microseconds > 0`. WHERE keeps the time column bare for range
access; bucket expressions belong in SELECT/GROUP BY. Densify at most B bins for
Overall and the selected detector page in Python. Do not densify full raw data.
Get Overall independently over ALL matched detectors, not only the displayed page.

Use `EXISTS` for unit/entity/event membership filters. Joining one anomaly to
many raw events and calling `COUNT(*)` is invalid. Prefer one anomaly fact row
after predicates. Facet grouping over multi-entity membership must count unique
anomaly IDs per candidate entity; the sum of those facets is not the result total.

Result/evidence navigation keyset, newest first:

```sql
SELECT a.id, a.anchor_utc, a.detector_id, a.priority, a.unit_id
FROM anomaly_outputs AS a
JOIN snapshot_runs AS sr
  ON sr.run_id = a.run_id AND sr.analysis_snapshot_id = :snapshot_id
WHERE a.dataset_id = :authorized_dataset
  AND a.anchor_utc >= :start_utc AND a.anchor_utc < :end_utc
  /* same validated shared filters as timeline */
  AND (a.anchor_utc < :cursor_time
       OR (a.anchor_utc = :cursor_time AND a.id < :cursor_id))
ORDER BY a.anchor_utc DESC, a.id DESC
LIMIT :page_size_plus_one;
```

Related raw context is a different entity: query `parsed_events` with authorized
dataset/input revision, bounded context range, optional entity/session predicates
and timestamp+ID keyset. Project references and safe previews, not every raw log.
Fetch authorized raw provenance/body on demand. A future real-data context mode
must say whether it shows parsed logs or flagged anomaly outputs.

## Index hypotheses and verification protocol

No index is added by this document. Start with primary/required unique/FK indexes
and one broad dataset/time path; benchmark candidates one at a time.

| Query pattern | Candidate fact index | Validation / cost question |
|---|---|---|
| Dataset/time + newest result page | `(dataset_id, anchor_utc, id)` | Range rows read, descending traversal/sort and table lookups |
| Selected detector/time | `(dataset_id, detector_id, anchor_utc, id)` | Detector selectivity; multi-detector IN may require merge/sort |
| Selected run/time | `(dataset_id, run_id, anchor_utc, id)` | Compare with snapshot-run join and dataset/time path |
| Host/time for single-host units | `(dataset_id, host_id, anchor_utc, id)` | Only if entity projection is semantically valid and measured useful |
| Service/time | `(dataset_id, service_id, anchor_utc, id)` | Avoid by default if low cardinality or uncommon filter |
| Priority/time | `(dataset_id, priority, anchor_utc, id)` | Low selectivity may not justify write/storage cost |
| Related parsed events | `(dataset_id, host_id, event_time_utc, id)` | Bounded keyset and host-filter skew |
| Multi-entity unit membership | `(dataset_id, entity_type, entity_id, unit_id)` | EXISTS candidate count and fanout; preserve uniqueness |

Order choices are workload hypotheses. MySQL documents leftmost-prefix use for
composite indexes; equality/range placement must be assessed for the actual plan,
not inferred from a column appearing somewhere in an index. [MySQL composite indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html).

For the isolated database, record server/version/config, `SHOW CREATE TABLE`,
`SHOW INDEX`, row counts and data/index sizes. Run `EXPLAIN FORMAT=JSON`, then
`EXPLAIN ANALYZE` on read-only SELECTs and capture estimated versus actual rows,
loops, access path, sorts/temp work and timings. ANALYZE executes the statement;
do not treat its instrumentation timing as ordinary API latency. Compare normal
query repetitions separately. [MySQL EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html).

After changing one candidate index, measure insert/import throughput and storage
as well as read latency. Remove unused/redundant candidates only in the isolated
benchmark, never by automatically modifying user indexes. Do not create an index
for every filter permutation. [MySQL index optimization](https://dev.mysql.com/doc/refman/8.4/en/optimization-indexes.html).

## Search policy

Preserve literal substring semantics by normalizing a bounded, redacted search
projection and query with a pinned Unicode normalization/case policy; use bound
`LOCATE`/equivalent binary-normalized comparison rather than wildcard expansion.
Benchmark the scoped scan. MySQL FULLTEXT is a different token-based search mode;
it cannot silently replace the current Python casefold substring behavior.
Never join/scan unbounded original secret-bearing raw bodies for global search.

## Coverage model

Keep ingestion, parsing, analysis and query execution separate:

```text
input_coverage(dataset_revision, source_manifest, scope, [start,end), state, reason)
parse_coverage(input_revision, parser_version, checkpoints, quarantined_count)
analysis_coverage(snapshot, detector/run, scope, [start,end), state, evaluated_units)
query_status(execution_complete, input_revision, analysis_snapshot, requested_scope)
```

Earliest/latest processed timestamps are descriptive extrema, not proof that all
intervening data was received or analysed. Missing intervals require trusted
source/checkpoint evidence. Sparse natural events do not create missing data.
Unknown-timestamp parse failures need an explicit source/range uncertainty warning,
not a false complete bin. Historical files have no live freshness promise.

| State | Meaning / UI |
|---|---|
| `complete_zero` | Complete eligible input AND selected analysis for the bin, count 0; never a healthy-system assertion |
| `no_raw_data` | Published source/input manifest establishes no input for this query; distinct from no anomalies |
| `not_analyzed` | Input exists but required detector coverage has not been published |
| `partial_ingestion` | Source processing is incomplete or known input chunks are missing |
| `partial_analysis` | Some selected detectors/units completed; counts and max priority are observed lower-bound information |
| `unknown` | No trustworthy completeness metadata for this scope |
| `query_failed` | Request did not finish; retain labelled old results, do not publish partial SQL rows as complete |
| `complete` | Query finished over a valid published snapshot; input/analysis completeness still independently reported |

Coverage may be detector- and entity-scoped. Overall completeness requires all
selected detector coverage under that scope; visible row paging must not change
it. Priority/search filters do not turn missing analysis into complete coverage.
Record `event_watermark`, ingestion progress and analysis progress separately.
For live sources report freshness/lag relative to an explicit server as-of time,
handling clock skew/future timestamps. Files show historical mode instead.

## Conditional summaries/cache

Add only after baseline SQL misses documented targets. Sparse summary buckets
may store count plus four severity counts per detector/run/entity scope. They
must preserve input/analysis revision and supported grouping dimensions. Arbitrary
search or unsupported entity filters fall back to exact fact queries; never reuse
a dataset-only summary for a host-filtered query.

Roll up only compatible, aligned complete buckets. Edge partial bins and finer
queries require fact queries; do not interpolate counts or average priorities.
Zero buckets can remain sparse; completeness comes from coverage, not row absence.
Late input invalidates affected units/windows/sessions and their ANCHOR buckets,
which may differ from the arrival timestamp's bucket. Publish recomputed versions
atomically; no double-increment on retry. Corrections/retractions require rebuilding
affected counts/severity, not assuming all updates are append-only additions.

Cache keys include authorization-policy version, dataset/input revision, analysis
snapshot, canonical filters, interval/resolution and detector paging/sort. Selection
belongs in result/export keys; display mode need not change aggregate values.
Reject stale revisions or use an explicitly retained immutable snapshot; TTL alone
does not establish consistency. Partitioning/storage changes remain deferred.
