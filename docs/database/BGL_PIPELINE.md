# BGL parser and batch ingestion

Reference: [Loghub BGL](https://github.com/logpai/loghub/tree/master/BGL) and its
[structured public example](https://raw.githubusercontent.com/logpai/loghub/master/BGL/BGL_2k.log_structured.csv).
Original labels: `-` means non-alert; another category is an alert label. This is
research ground truth, not a feature, severity, probability or confirmed cause.

## Parsing

`app/parsers/bgl.py` accepts a binary stream. It reads physical lines lazily with
a 262,144-byte safety limit. Invalid UTF-8, missing fields, oversized bounded
fields and invalid timestamps are handled explicitly. Oversized lines abort the
batch rather than silently truncating source evidence. All smaller malformed
lines are retained byte-for-byte with an error code; no parsed event/label is
invented. CRLF, LF and a final unterminated line are supported.

The ten fields are Label, Timestamp, Date, Node, Time, NodeRepeat, Type, Component,
Level and Content. Host is **Node**, never a guessed substitution from NodeRepeat.
Both original node fields are retained. `service` is explicitly a projection of
BGL Component, not discovered application topology. No template ID is invented.

Timestamp policy: Unix epoch seconds are authoritative UTC. The printed local
timestamp (including its fractional part) and date are preserved separately.
The parser does not invent an offset or graft local microseconds onto the epoch.
Consequently ordering ties use the persisted event ID. Printed/epoch timezone
reconciliation remains a separate research task.

## Identity, batching and resume

An operator supplies an immutable local ZIP archive. No HTTP filename is opened.
The importer streams `BGL.log` without extracting archive paths. It validates the
member key and a 10 GiB declared member size limit. SHA-256 fingerprints the
**archive file**; physical offsets refer to the **uncompressed member**. These
are different byte domains and are named as such in evidence and reports.

Register an empty dataset, then import through the app's MySQL engine:

```text
python -m scripts.database register-bgl --key bgl-research-v1
python -m scripts.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 10000
python -m scripts.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 100000
```

`--limit` is an **absolute physical-line target**, not an additional row count.
Omit it only when deliberately importing to EOF. Batch size defaults to 500,
allowed 1..2000, with an additional 8 MiB raw-byte budget per batch. Data, labels,
counters, input revision and the byte/line checkpoint
commit in one transaction. Progress callbacks run **after** commit. Exact source
position and parser uniqueness constraints reject duplicates; changed archive or
parser version is rejected rather than overwriting an import.

A dedicated MySQL `GET_LOCK` connection serializes imports per schema/dataset.
It is released on normal exit or worker process death. Row locks protect each
batch; the database checkpoint is re-read under lock. After acquiring the lease,
a new importer can mark earlier `running` import jobs as `worker_interrupted`.
A caught batch error rolls back only that batch, records a safe error code and
keeps committed progress. Re-importing a completed prefix adds no raw/event/label
rows. A new processing-job record is intentionally retained for each attempt.

ZIP seeking may decompress earlier bytes during resume; it is memory-bounded,
but not O(1). Full-archive hashing also has a fixed I/O cost. No pre-extracted
file, parallel importer, background queue or cache is claimed.

For reproducible proofs, run `scripts.benchmark_bgl` and
`scripts.verify_import_restart` in a newly provisioned `logsense_bench_*` schema.
The latter abruptly exits an owned worker before the 50,000th-line batch commits.
Verification compares **every imported raw byte string**, physical line number,
offset, prefix SHA-256, counters, labels and retry results. It does not assume
matching row counts alone prove correctness.

Current error reporting is structured per malformed raw row plus job error code
and summary counts. An HTTP upload/progress UI, parser-upgrade replay, file
replacement and distributed job scheduling remain outside this task.
