# Operations guide: MySQL and real BGL data

Running the MySQL-backed investigation platform: the local runtime, migrations, BGL import,
accounts, workers, uploads, alerts and notifications. Start with the [README](../README.md);
the [MySQL runbook](database/MYSQL_RUNBOOK.md) covers the runtime in depth.


Follow the [Windows/macOS runbook](database/MYSQL_RUNBOOK.md). A local native
MySQL ZIP runtime uses only `.local`, port 13306 and 127.0.0.1; no service or global
configuration is installed. The lifecycle tool generates private credentials and
passes DATABASE_URL/FLASK_SECRET_KEY into child processes without printing them.
It refuses reinitialization over an existing runtime. No default login exists.

```text
python -m scripts.run.mysql_runtime start
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database register-bgl --key bgl-research-v1
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database ingest-bgl --dataset DATASET_ID --archive data/raw/BGL.zip --limit 1000
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.database create-user --username investigator --role admin --dataset DATASET_ID
python -m scripts.run.mysql_runtime exec --role app -- -m flask --app app run --host 127.0.0.1
```

Replace DATASET_ID with the actual registration result. Account creation prompts
for a password; do not put passwords in command arguments. The import limit is an
absolute physical-line target: increase to 10000/100000 to resume the same source.
The CLI archive must be the immutable locally downloaded Loghub BGL ZIP.
The extra grant is DELETE on only `datasets` and `user_datasets`, not log tables;
use the actual schema name if different. See [dataset CRUD](database/DATASET_CRUD.md).

Open `/?workspace=logs` and sign in. A manager with no initial grants can register
a first dataset. Use `create-user --username investigator --role manager --no-dataset`
with the operator command above when starting from an empty database. To investigate
completed detections, open `/?source=db-DATASET_ID`. The Investigation link uses
the selected MySQL dataset. Open `/?source=demo` for synthetic fixtures. Run the
analysis worker separately:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.worker
```

For HTTP import, use the inline dataset/upload panels in Log Explorer. A
manager/admin can first create an empty dataset; an analyst/manager/admin with
its grant can stage a compatible TXT/LOG or `raw_line` CSV. A viewer cannot
submit imports. Run the separate ingestion worker to consume queued uploads:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.ingestion_worker
```

The analysis worker does not consume upload jobs. A 202 response means queued,
not imported. The same dataset/idempotency key/content reuses its job; a new key
creates a separate artifact. Uploaded labels are explicitly user-supplied,
not independently authenticated Loghub ground truth. See
[formats, validation, provenance and recovery](database/UPLOADS.md).

Jobs are submitted from the inline analysis controls or authenticated REST API.
A queued job is not a completed detection. Use the inline Alerts panel to create
rules (manager permission), acknowledge/assign incidents and inspect actual
anomaly evidence. SMTP is disabled by default; configure it privately and invoke
`python -m scripts.run.database notify` outside HTTP requests. Tests use mocks;
external SMTP delivery was not exercised.
