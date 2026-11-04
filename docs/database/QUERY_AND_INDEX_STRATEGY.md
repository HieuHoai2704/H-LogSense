# Query and index verification

The source schema inventory is in SCHEMA.md; `measurements/schema-audit.json`
contains actual MySQL SHOW CREATE TABLE/SHOW INDEX output. The final snapshot and reflection tests validate all 23 domain tables at head 0004. Final API EXPLAIN/ANALYZE plans are in
`measurements/api-performance.json`.

| Access path | Index/constraint | Meaning and measured scope |
|---|---|---|
| Dataset/time event page | log_events(dataset_id,timestamp,id) | UTC range and stable keyset/order; 10K, 100K, 1M parsed-event datasets |
| Dataset/host/time | log_events(dataset_id,host,timestamp,id) | Related log context and host-filtered pages; actual covering lookup captured |
| Event identity/snapshot | unique log_events(dataset_id,id) | Scoped FK identity and maximum event ID watermark |
| Import provenance | unique raw_log_records(dataset_id,artifact_id,line_number) | Retry/position identity, not text-body deduplication |
| Parser output identity | unique log_events(dataset_id,raw_id,parser_version,emit_index) | One raw source can support multiple explicit parser emissions |
| Anomaly anchor page | anomaly_outputs(dataset_id,anchor_time,id) | One output fact at its anchor, not interval fanout |
| Selected run/unit | unique anomaly_outputs(dataset_id,run_id,unit_id,signal_key) | Per-run signal deduplication; completed run filter |
| Prediction retry | unique detection_predictions(dataset_id,run_id,unit_id) | Normal and abnormal test-unit scores, one per run/unit |
| Incident deduplication | alert_decisions and alerts unique dataset/rule/anomaly | Retain cooldown decisions so later retries cannot replay old backlog |

FK-supporting and unique indexes also have write/storage cost. No blanket
priority/service indexes, partitioning, rollups, cache or analytical store were
added without evidence. The host-window anomaly workload currently has 158
outputs on 100K parsed events; it does **not** establish performance at one million
anomaly facts. A one-million parsed-event log API is a different workload.

WHERE predicates keep timestamp columns bare. GROUP BY uses exact integer
microseconds and explicitly grouped MySQL DIV. UTC query bounds are inclusive/
exclusive; a bin ending at t does not contain an event anchored at t. Only bounded
bin arrays and detector pages are densified in Python. Event membership is never
joined into a COUNT(*) over outputs.

Search is bounded literal substring LIKE with escaped wildcards. It can scan the
selected dataset/time range; the project does not claim a full-text index.
Facet queries are server grouped and capped at 100 values per dimension, retaining
selected values even if their current count is zero. Larger facet vocabularies
need a paginated facet-search API before broad production use.

No equivalent real-data endpoint existed before implementation, so a same-workload
before comparison is NOT RUN. The final measured profile records actual loopback
HTTP, total SQL duration per request, payload size, serial throughput and process
RSS. Historical six-event fixture latency is not presented as a valid speedup.
