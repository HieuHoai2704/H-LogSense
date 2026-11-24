# Database ERD

```mermaid
erDiagram
    data_sources ||--o{ datasets : contains
    datasets ||--o{ source_artifacts : owns
    source_artifacts ||--o{ raw_log_records : preserves
    raw_log_records ||--o{ log_events : parses
    datasets ||--o{ detection_units : owns
    log_events o|--o{ detection_units : anchors_event_unit
    detection_units ||--o{ unit_events : contains
    log_events ||--o{ unit_events : membership
    log_events o|--o{ ground_truth_labels : event_label
    detection_units o|--o{ ground_truth_labels : block_or_session_label
    detectors ||--o{ detector_versions : versions
    detector_versions ||--o{ detector_runs : executes
    datasets ||--o{ detector_runs : pins_revision
    detector_runs ||--o{ anomaly_outputs : flags
    detection_units ||--o{ anomaly_outputs : supports
    datasets ||--o{ processing_jobs : processes
    datasets ||--o{ coverage_intervals : describes
    detector_runs o|--o{ coverage_intervals : analysis_coverage
    users ||--o{ user_datasets : granted
    datasets ||--o{ user_datasets : scoped_access
    detector_runs ||--o{ detection_predictions : scores_all_test_units
    detection_units ||--o{ detection_predictions : scored
    detector_runs ||--o| evaluation_reports : evaluated
    datasets ||--o{ alert_rules : scopes
    alert_rules ||--o{ alert_decisions : deduplicates
    anomaly_outputs ||--o{ alert_decisions : matched
    alert_rules ||--o{ alerts : creates
    anomaly_outputs ||--o{ alerts : supports
    detector_runs ||--o{ alerts : identifies
    users o|--o{ alerts : assigned_or_acknowledged
    alerts ||--o{ alert_audit : records
    users o|--o{ alert_audit : actor
    alerts ||--o| notification_outbox : queues
```

Every scoped child has `dataset_id`; composite foreign keys enforce ownership,
not merely a service-layer convention. An output cannot reference a unit or run
in a different dataset. A run's `(detector_id, version_id)` must reference the same
logical detector. Labels target **exactly one** event or unit. Raw/event mappings
permit multiple parser outputs using `emit_index`; current BGL emits zero or one.

There are 23 domain tables at head 0004. An authenticated account can have zero dataset grants. A manager-created dataset and its creator grant are committed together. Local identity, assignment, audit and outbox are implemented. Full V3 analysis publication manifests, rollups, tenant federation and retention policies remain deferred.
