# Dataset metadata CRUD and RBAC

Dataset metadata is managed through the existing Flask REST application. This
module does not upload files, import arbitrary server paths or change detector
configuration. The existing Investigation layout and explicit Demo Mode remain
separate from authenticated MySQL datasets.

## Permission and data-preservation policy

| Operation | Roles | Additional scope / guard |
|---|---|---|
| List and read metadata | viewer, analyst, manager, admin | Authenticated session; list includes only explicit UserDataset grants |
| Create | manager, admin | Valid session and X-CSRF-Token; creator receives a grant in the same transaction |
| Rename | manager, admin | Explicit dataset grant and X-CSRF-Token |
| Delete empty metadata | admin | Explicit grant, X-CSRF-Token and pristine-dataset checks |

An admin role does not bypass dataset authorization. Missing and ungranted
dataset IDs are denied consistently rather than exposing another user's
metadata. A valid session with no grants receives an empty list. Existing
operator bearer tokens do not obtain mutation privileges; their existing
read-only Log Explorer paths are unchanged.

DELETE is a real SQL DELETE, not archive UPDATE. It is allowed only when the
dataset is registered or archived, has input_revision=0, and has no dependent
records except UserDataset access links. The service locks the dataset row,
checks dependent tables, deletes its ACL links and deletes the dataset within
one transaction. Failure rolls the operation back. It does not remove the
DataSource parent, log files, source artifacts, raw records, parsed events,
labels, jobs, detection units, predictions, anomalies or incidents.

Datasets with imported data or other dependent records return 409. Busy states
also return 409. There is no force-delete parameter, cascading log deletion or
bulk-delete endpoint. Existing FK RESTRICT constraints provide another barrier
against removing a dataset still referenced by data. Archiving and restoring
datasets are not new API operations in this module.

## Endpoints and representation

| Method / path | Input / result |
|---|---|
| GET `/api/v1/datasets` | Optional `after_id`, `limit` (1..100), literal `q` (at most 200 characters); stable ID pagination; `{items, next_after_id}` |
| GET `/api/v1/datasets/{id}` | Granted metadata; `{dataset: object}` |
| POST `/api/v1/datasets` | JSON name, dataset_key; optional data_mode and source_id; 201 `{dataset: object}` |
| PATCH `/api/v1/datasets/{id}` | JSON name only; 200 `{dataset: object}` |
| DELETE `/api/v1/datasets/{id}` | Pristine metadata only, admin plus grant; 204 without a response body |

The dataset object contains:

```json
{
  "id": 123,
  "name": "BGL classroom sample",
  "dataset_key": "bgl-classroom-v1",
  "data_mode": "unverified",
  "state": "registered",
  "input_revision": 0,
  "source_id": 45,
  "source_name": "User-managed datasets"
}
```

These numbers are examples, not existing record IDs. Mutation bodies reject
unknown fields and invalid types. Names support Unicode with bounded length;
keys are bounded ASCII identifiers. data_mode accepts real, synthetic or
unverified, and defaults to unverified when registering metadata. Registration
does not prove that a file was imported or that its provenance is verified.

When source_id is omitted, the server creates or reuses the current user's
stable personal source. A supplied source_id must be the user's personal source
or a source already reachable through an authorized dataset. Guessing a source
ID cannot attach metadata to another user's source. Dataset keys are unique
within a source; duplicate registration returns 409 without partially creating
an ACL grant or dataset.

PATCH changes the human-readable name only. source_id, dataset_key, data_mode,
pipeline state, revision and ownership/grant fields cannot be changed by mass
assignment. Renaming does not alter input_revision or invalidate detector runs:
it changes metadata, not the imported data snapshot.

## Error contract

Responses use the existing JSON `{error: {code: ..., message: ...}}` convention;
message text may be omitted where the existing API does not provide it.

| HTTP | Meaning |
|---|---|
| 400 | Invalid JSON/field/type, unsupported mutation field, invalid ID or page bounds |
| 403 | No active authorized session, insufficient role, no dataset/source grant or missing/invalid CSRF token |
| 409 `dataset_conflict` | Duplicate source/dataset key or conflicting metadata operation |
| 409 `dataset_not_empty` | Revision or dependent records prevent physical deletion |
| 409 `dataset_busy` | Dataset lifecycle state prevents deletion |
| 503 | Database unavailable or required SQL privileges are not provisioned; internal SQL/credentials are not exposed |

## Provision the minimal DELETE privileges

The original application account has SELECT/INSERT/UPDATE on its schema.
Dataset deletion additionally requires DELETE on exactly two metadata tables:
datasets and user_datasets. No schema change is needed for this module, and
no migration grants privileges or deletes data.

After migrations have created both tables, an operator of the existing owned
native runtime can run:

```text
python -m scripts.run.mysql_runtime grant-dataset-crud --schema logsense_dev
```

For a separate owned QA runtime and its actual generated schema:

```text
python -m scripts.run.mysql_runtime --root .local/university-e2e-mysql grant-dataset-crud --schema ACTUAL_GENERATED_SCHEMA
```

Replace the schema placeholder with the intended existing application schema.
The command accepts only a 1..64-character ASCII alphanumeric/underscore schema
identifier. It resolves the dedicated runtime beneath project .local, validates
its private ownership marker, authenticates the loopback server and checks its
datadir/bind address/port. Both target base tables must exist before either grant
is attempted.

It issues only:

```sql
GRANT DELETE ON `YOUR_SCHEMA`.`datasets` TO 'logsense_app'@'localhost';
GRANT DELETE ON `YOUR_SCHEMA`.`user_datasets` TO 'logsense_app'@'localhost';
```

The command does not grant DELETE on schema.*, raw logs, parsed events, jobs or
any other table. It does not grant DDL, GRANT OPTION, global privileges or remote
accounts. It does not execute a data DELETE, alter existing rows, initialize a
runtime, restart a server or print a password. Passwords are read from ignored
local settings rather than command arguments.

The fixed table-level grants are idempotent. MySQL GRANT statements are DCL and
auto-commit; if the connection is interrupted, inspect the outcome and repeat the
same operation. This command does not revoke privileges granted separately by
an operator, so an external/previously broadened account still needs a separate
privilege audit before claiming minimal access.

Hosted or externally administered MySQL deployments must have their authorized
database administrator grant the same two table privileges. The owned-runtime
command is not a replacement for an external administrator's access controls.

## Verification

Run the dependency-free privilege guard tests:

```text
python -m unittest tests.test_dataset_privileges -v
```

They verify exact table scope, identifier rejection before credential/network
access, ownership/port rejection and no partial grant when a target table is
missing. They are mock tests, not proof that an actual MySQL grant was applied.

Use the existing isolated MySQL verifier for the CRUD/API/RBAC integration suite:

```text
python -m scripts.qa.verify_mysql
```

MYSQL_ADMIN_URL and DATABASE_URL must be injected privately as described in
[TESTING.md](TESTING.md). Tests provision new token-marked schemas, never reset
the retained BGL datasets. The dataset suite demonstrates physical deletion
only on new empty metadata fixtures, refuses populated/busy datasets, checks
role/grant/CSRF isolation and verifies transaction rollback. Read the actual
run report for PASS/FAIL/NOT RUN; no external SMTP, new browser result or native
macOS execution is implied by this document.
