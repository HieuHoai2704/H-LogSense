# Applied schema reference

Current head: `0004`; 23 domain tables, InnoDB, utf8mb4_0900_as_cs. Internal IDs are signed BIGINT. ORM defaults are client-side unless specified; direct SQL must supply required fields. Existing data is retained by four forward migrations.

UTC timestamps bind as aware datetimes and store/load DATETIME(6) UTC. Intervals are [start,end); windows require positive duration, event units have no invented end. Raw/parsed/evaluated/prediction/output/incident counts are distinct. Original BGL epoch and printed time are preserved separately.

Dataset ownership is enforced by composite FKs. Identity/role and dataset grants guard APIs independently. Source bytes and credentials are private; only bounded redacted evidence is returned. An absent coverage row means unknown, not complete or healthy.

## data_sources

| Column | MySQL type | Nullable |
|---|---|---|
| source_key | VARCHAR(100) | no |
| name | VARCHAR(200) | no |
| id | BIGINT | no |

Primary key: id.

- Unique: source_key.

## detectors

| Column | MySQL type | Nullable |
|---|---|---|
| detector_key | VARCHAR(100) | no |
| family | VARCHAR(32) | no |
| id | BIGINT | no |

Primary key: id.

- Unique: detector_key.

## users

| Column | MySQL type | Nullable |
|---|---|---|
| username | VARCHAR(100) | no |
| password_hash | VARCHAR(512) | no |
| role | VARCHAR(16) | no |
| active | BOOL | no |
| auth_version | INTEGER | no |
| id | BIGINT | no |

Primary key: id.

- Check: `role IN ('viewer','analyst','manager','admin')`.
- Unique: username.

## datasets

| Column | MySQL type | Nullable |
|---|---|---|
| source_id | BIGINT | no |
| dataset_key | VARCHAR(100) | no |
| name | VARCHAR(200) | no |
| data_mode | VARCHAR(16) | no |
| state | VARCHAR(16) | no |
| input_revision | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `data_mode IN ('real','synthetic','unverified')`.
- Check: `state IN ('registered','importing','partial','imported','failed','archived')`.
- FK source_id -> data_sources.id.
- Unique: source_id, dataset_key.

## detector_versions

| Column | MySQL type | Nullable |
|---|---|---|
| detector_id | BIGINT | no |
| version | VARCHAR(64) | no |
| configuration | JSON | no |
| feature_schema | JSON | yes |
| score_direction | VARCHAR(32) | yes |
| id | BIGINT | no |

Primary key: id.

- FK detector_id -> detectors.id.
- Unique: detector_id, id.
- Unique: detector_id, version.

## alert_rules

| Column | MySQL type | Nullable |
|---|---|---|
| name | VARCHAR(100) | no |
| detector_id | BIGINT | yes |
| min_priority | VARCHAR(16) | no |
| host | VARCHAR(128) | yes |
| cooldown_seconds | INTEGER | no |
| enabled | BOOL | no |
| last_alert_at | DATETIME(6) | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `cooldown_seconds >= 0 AND cooldown_seconds <= 86400`.
- Check: `min_priority IN ('Low','Medium','High','Critical')`.
- FK dataset_id -> datasets.id.
- FK detector_id -> detectors.id.
- Unique: dataset_id, id.

## detector_runs

| Column | MySQL type | Nullable |
|---|---|---|
| detector_id | BIGINT | no |
| version_id | BIGINT | no |
| run_key | VARCHAR(100) | no |
| state | VARCHAR(16) | no |
| input_revision | BIGINT | no |
| evaluated_units | BIGINT | no |
| configuration | JSON | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `state IN ('running','completed','failed')`.
- FK dataset_id -> datasets.id.
- FK detector_id, version_id -> detector_versions.detector_id, detector_versions.id.
- Unique: dataset_id, id.
- Unique: dataset_id, run_key.

## processing_jobs

| Column | MySQL type | Nullable |
|---|---|---|
| kind | VARCHAR(16) | no |
| state | VARCHAR(16) | no |
| processed_count | BIGINT | no |
| error_code | VARCHAR(64) | yes |
| configuration | JSON | yes |
| result | JSON | yes |
| job_key | VARCHAR(100) | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `kind IN ('ingestion','parsing','analysis')`.
- Check: `state IN ('queued','running','completed','failed')`.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, id.
- Unique: dataset_id, job_key.

## source_artifacts

| Column | MySQL type | Nullable |
|---|---|---|
| artifact_key | VARCHAR(200) | no |
| sha256 | VARCHAR(64) | no |
| byte_length | BIGINT | no |
| parser_version | VARCHAR(64) | no |
| checkpoint_line | BIGINT | no |
| checkpoint_byte | BIGINT | no |
| parsed_count | BIGINT | no |
| malformed_count | BIGINT | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `byte_length >= 0 AND checkpoint_line >= 0 AND checkpoint_byte >= 0 AND checkpoint_byte <= byte_length AND parsed_count >= 0 AND malformed_count >= 0 AND parsed_count + malformed_count = checkpoint_line`.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, artifact_key.
- Unique: dataset_id, id.

## user_datasets

| Column | MySQL type | Nullable |
|---|---|---|
| user_id | BIGINT | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id -> datasets.id.
- FK user_id -> users.id.
- Unique: user_id, dataset_id.

## coverage_intervals

| Column | MySQL type | Nullable |
|---|---|---|
| run_id | BIGINT | yes |
| layer | VARCHAR(16) | no |
| state | VARCHAR(16) | no |
| start_time | DATETIME(6) | no |
| end_time | DATETIME(6) | no |
| evidence_reference | VARCHAR(200) | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `end_time > start_time`.
- Check: `layer IN ('ingestion','parsing','analysis')`.
- Check: `state <> 'complete' OR evidence_reference IS NOT NULL`.
- Check: `(layer = 'analysis' AND run_id IS NOT NULL) OR (layer <> 'analysis' AND run_id IS NULL)`.
- Check: `state IN ('complete','partial','unknown','failed','not_processed')`.
- FK dataset_id -> datasets.id.
- FK dataset_id, run_id -> detector_runs.dataset_id, detector_runs.id.

## evaluation_reports

| Column | MySQL type | Nullable |
|---|---|---|
| run_id | BIGINT | no |
| metrics | JSON | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id -> datasets.id.
- FK dataset_id, run_id -> detector_runs.dataset_id, detector_runs.id.
- Unique: dataset_id, run_id.

## raw_log_records

| Column | MySQL type | Nullable |
|---|---|---|
| artifact_id | BIGINT | no |
| line_number | BIGINT | no |
| byte_offset | BIGINT | no |
| raw_bytes | LONGBLOB | no |
| parse_error | VARCHAR(64) | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `line_number > 0 AND byte_offset >= 0`.
- FK dataset_id, artifact_id -> source_artifacts.dataset_id, source_artifacts.id.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, artifact_id, line_number.
- Unique: dataset_id, id.

## log_events

| Column | MySQL type | Nullable |
|---|---|---|
| raw_id | BIGINT | no |
| parser_version | VARCHAR(64) | no |
| emit_index | INTEGER | no |
| timestamp | DATETIME(6) | no |
| raw_timestamp | VARCHAR(100) | no |
| host | VARCHAR(128) | yes |
| service | VARCHAR(128) | yes |
| severity | VARCHAR(32) | yes |
| message | LONGTEXT | no |
| attributes | JSON | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id, raw_id -> raw_log_records.dataset_id, raw_log_records.id.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, id.
- Unique: dataset_id, raw_id, parser_version, emit_index.
- Query index ix_events_dataset_host_time: dataset_id, host, timestamp, id.
- Query index ix_events_dataset_time_id: dataset_id, timestamp, id.

## detection_units

| Column | MySQL type | Nullable |
|---|---|---|
| unit_key | VARCHAR(200) | no |
| kind | VARCHAR(16) | no |
| event_id | BIGINT | yes |
| start_time | DATETIME(6) | no |
| end_time | DATETIME(6) | yes |
| host | VARCHAR(128) | yes |
| definition | JSON | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `(kind = 'event' AND event_id IS NOT NULL AND end_time IS NULL) OR (kind = 'window' AND event_id IS NULL AND end_time IS NOT NULL AND end_time > start_time) OR (kind IN ('block','session') AND event_id IS NULL AND (end_time IS NULL OR end_time > start_time))`.
- FK dataset_id -> datasets.id.
- FK dataset_id, event_id -> log_events.dataset_id, log_events.id.
- Unique: dataset_id, id.
- Unique: dataset_id, unit_key.

## anomaly_outputs

| Column | MySQL type | Nullable |
|---|---|---|
| run_id | BIGINT | no |
| unit_id | BIGINT | no |
| signal_key | VARCHAR(64) | no |
| anchor_time | DATETIME(6) | no |
| priority | VARCHAR(16) | yes |
| score | DOUBLE | yes |
| evidence | JSON | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `priority IS NULL OR priority IN ('Low','Medium','High','Critical')`.
- FK dataset_id -> datasets.id.
- FK dataset_id, run_id -> detector_runs.dataset_id, detector_runs.id.
- FK dataset_id, unit_id -> detection_units.dataset_id, detection_units.id.
- Unique: dataset_id, id.
- Unique: dataset_id, id, run_id.
- Unique: dataset_id, run_id, unit_id, signal_key.
- Query index ix_anomalies_dataset_anchor_id: dataset_id, anchor_time, id.

## detection_predictions

| Column | MySQL type | Nullable |
|---|---|---|
| run_id | BIGINT | no |
| unit_id | BIGINT | no |
| score | DOUBLE | no |
| predicted | BOOL | no |
| features | JSON | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id -> datasets.id.
- FK dataset_id, run_id -> detector_runs.dataset_id, detector_runs.id.
- FK dataset_id, unit_id -> detection_units.dataset_id, detection_units.id.
- Unique: dataset_id, run_id, unit_id.

## ground_truth_labels

| Column | MySQL type | Nullable |
|---|---|---|
| event_id | BIGINT | yes |
| unit_id | BIGINT | yes |
| source | VARCHAR(64) | no |
| version | VARCHAR(64) | no |
| label | VARCHAR(128) | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `(event_id IS NULL) <> (unit_id IS NULL)`.
- FK dataset_id -> datasets.id.
- FK dataset_id, event_id -> log_events.dataset_id, log_events.id.
- FK dataset_id, unit_id -> detection_units.dataset_id, detection_units.id.
- Unique: dataset_id, event_id, source, version.
- Unique: dataset_id, unit_id, source, version.

## unit_events

| Column | MySQL type | Nullable |
|---|---|---|
| unit_id | BIGINT | no |
| event_id | BIGINT | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id, event_id -> log_events.dataset_id, log_events.id.
- FK dataset_id, unit_id -> detection_units.dataset_id, detection_units.id.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, unit_id, event_id.

## alert_decisions

| Column | MySQL type | Nullable |
|---|---|---|
| rule_id | BIGINT | no |
| anomaly_id | BIGINT | no |
| outcome | VARCHAR(20) | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK dataset_id -> datasets.id.
- FK dataset_id, anomaly_id -> anomaly_outputs.dataset_id, anomaly_outputs.id.
- FK dataset_id, rule_id -> alert_rules.dataset_id, alert_rules.id.
- Unique: dataset_id, rule_id, anomaly_id.

## alerts

| Column | MySQL type | Nullable |
|---|---|---|
| rule_id | BIGINT | no |
| anomaly_id | BIGINT | no |
| run_id | BIGINT | no |
| status | VARCHAR(20) | no |
| assigned_to | BIGINT | yes |
| acknowledged_by | BIGINT | yes |
| created_at | DATETIME(6) | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `status IN ('open','acknowledged','investigating','resolved')`.
- FK dataset_id, anomaly_id, run_id -> anomaly_outputs.dataset_id, anomaly_outputs.id, anomaly_outputs.run_id.
- FK dataset_id, rule_id -> alert_rules.dataset_id, alert_rules.id.
- FK acknowledged_by -> users.id.
- FK assigned_to -> users.id.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, id.
- Unique: dataset_id, rule_id, anomaly_id.

## alert_audit

| Column | MySQL type | Nullable |
|---|---|---|
| alert_id | BIGINT | no |
| actor_id | BIGINT | yes |
| action | VARCHAR(40) | no |
| details | JSON | no |
| timestamp | DATETIME(6) | no |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- FK actor_id -> users.id.
- FK dataset_id -> datasets.id.
- FK dataset_id, alert_id -> alerts.dataset_id, alerts.id.

## notification_outbox

| Column | MySQL type | Nullable |
|---|---|---|
| alert_id | BIGINT | no |
| state | VARCHAR(16) | no |
| attempts | INTEGER | no |
| next_attempt | DATETIME(6) | no |
| error_code | VARCHAR(32) | yes |
| dataset_id | BIGINT | no |
| id | BIGINT | no |

Primary key: id.

- Check: `attempts >= 0 AND attempts <= 3`.
- FK dataset_id, alert_id -> alerts.dataset_id, alerts.id.
- FK dataset_id -> datasets.id.
- Unique: dataset_id, alert_id.

## Publication and retention boundaries

- Events are append-only through this application. Log snapshots sign max event ID and input revision; anomaly views pin one completed run per logical detector. Full V3 publication manifests/retention/RBAC federation remain future work.
- BGL import checkpoints, counters and input revision commit together. Window jobs persist all normal/abnormal test predictions; historical event baselines materialize flagged units only and retain an evaluated count.
- Unit-event rows for windows are explicitly sampled supporting evidence, bounded to the first 20 observed events. They are not claimed to be exhaustive window membership.
- Labels target exactly one event or block/session/window unit. HDFS schema support is not an implemented HDFS parser or importer.
- Cooldown decisions are permanent per rule/anomaly identity. Alert/anomaly/run composite references cannot disagree across datasets.
- No cascading delete API, table reset, startup DDL, partitioning, rollups or columnar storage was introduced.
