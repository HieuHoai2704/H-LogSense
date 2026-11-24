# Migration operations

`0001` is the initial frozen DDL. It contains 14 domain tables with InnoDB,
utf8mb4 case-sensitive collation, microsecond UTC DATETIME columns and named
constraints. It does not import current ORM models at migration runtime.

The current head is `0004`, with 23 domain tables. `0002` adds user/dataset grants,
window predictions/evaluation, queued jobs and incidents/outbox, plus nullable
window metadata and additional anomaly identity constraints. `0003` adds job
idempotency keys; `0004` records alert/cooldown decisions. No existing source rows
are deleted or rewritten. Older temporary verification schemas remain at their
original versions; only explicitly selected owned schemas are upgraded.

Initialization uses **Flask-Migrate/Alembic**, never `db.create_all()`:

```text
python -m flask --app app db upgrade
python -m flask --app app db current
python -m flask --app app db check
```

Set `DATABASE_URL` to the dedicated migration user's URL in the child process.
For the private ZIP runtime, use the credential-safe wrapper:

```text
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db upgrade
python -m scripts.run.mysql_runtime exec --role migrate -- -m flask --app app db current
```

No database connection means no migration CLI is registered; configure it first.
The migration environment checks MySQL >=8.0.16 and rejects an unversioned database
containing unknown tables. An isolated test ownership-marker table is permitted.
Existing versioned databases still require operator review before upgrades.

MySQL DDL auto-commits. A failed initial migration can leave partial tables;
do not rerun blindly, stamp a broken schema, drop tables, or downgrade. Inspect it
and provision a new isolated schema or design an explicitly reviewed forward
repair. The initial destructive downgrade is deliberately disabled.

Verification creates two new uniquely named schemas, applies `0001`, reflects
tables/constraints and checks model/schema agreement with Alembic. It never drops
or rebuilds an existing schema. Changes after an approved migration require a new
revision; do not edit an already distributed migration.

During this uncommitted implementation, changing SQLAlchemy's `Float(53)` spelling
to MySQL `DOUBLE(asdecimal=False)` removed a false reflection difference. Both
render the same DOUBLE DDL; no data/type conversion was executed.
