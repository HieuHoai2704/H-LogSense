# Reviewing H-logsen

Thank you for reviewing. This guide gets you from a fresh clone to an informed review in about an hour:
how to set up, what to read first, how to verify the claims in the [README](README.md), what to look for
in each area, and which decisions are intentional.

## Contents

1. [How to give feedback](#how-to-give-feedback)
2. [Set up in fifteen minutes](#set-up-in-fifteen-minutes)
3. [Reading order](#reading-order)
4. [Verify the README](#verify-the-readme)
5. [Review checklists](#review-checklists)
6. [Intentional decisions](#intentional-decisions)
7. [Severity guide](#severity-guide)

## How to give feedback

| You found | Please |
| --- | --- |
| A problem in a specific change | Comment on the pull request line; suggest a fix when you can |
| A problem in existing code | Open an issue with the **Review finding** template |
| A security weakness | Do not open a public issue; follow [SECURITY.md](SECURITY.md) |
| A design concern | Open an issue describing the trade-off you would make instead |

Each finding is most useful with: the file and line, what happens, the input or steps that trigger it, and
what you expected. A failing test or a command that reproduces it is ideal.

## Set up in fifteen minutes

```bash
git clone https://github.com/HieuHoai2704/H-LogSense.git && cd H-LogSense
python -m venv .venv && . .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,qa]"
python -m playwright install chromium                    # only for the browser end-to-end tests

ruff check . && ruff format --check . && mypy            # static analysis: should be clean
python -B -m unittest discover -s tests                  # about 240 tests run; MySQL tests are skipped
python -m flask --app app run --host 127.0.0.1           # open /?source=demo for the synthetic investigation
python -m scripts.run.workbench --browser                 # the workbench; open any project folder
```

To run the MySQL integration suite you need a MySQL 8.4 server you can create schemas on. A disposable
container is the simplest option:

```bash
docker run -d --name hlogsen-mysql -p 127.0.0.1:3307:3306 -e MYSQL_ROOT_PASSWORD=change-me mysql:8.4
docker exec -i hlogsen-mysql mysql -uroot -pchange-me -e "CREATE USER 'logsense'@'%' IDENTIFIED BY 'change-me-too'"
export MYSQL_ADMIN_URL="mysql+pymysql://root:change-me@127.0.0.1:3307/mysql"
export DATABASE_URL="mysql+pymysql://logsense:change-me-too@127.0.0.1:3307/logsense_dev"
export MYSQL_GRANT_HOST=%                                 # the container sees the host on its bridge address
python -m scripts.qa.verify_mysql                         # creates new token-marked test schemas; drops nothing
docker rm -f hlogsen-mysql                                # when you are done
```

## Reading order

The codebase is about 43,000 lines in `app/` including templates, styles and catalogs. This order follows
a request from the boundary inward and covers the parts that matter most in about two hours.

| Step | Read | What you should come away with |
| --- | --- | --- |
| 1 | [`app/contracts.py`](app/contracts.py) | The shapes that cross layers: the validated investigation scope, job configuration, `db-<id>` and `DB-<id>` identities |
| 2 | [`app/api/anomalies.py`](app/api/anomalies.py), [`app/api/sources.py`](app/api/sources.py) | Thin routes over one interface; how demo and database backends stay interchangeable |
| 3 | [`app/services/investigation.py`](app/services/investigation.py) | Query validation order, timeline bins, facets that exclude their own filter, coverage semantics |
| 4 | [`app/services/mysql_investigation.py`](app/services/mysql_investigation.py) | The same view in SQL: grouped buckets, coverage proofs, keyset paging |
| 5 | [`app/parsers/bgl.py`](app/parsers/bgl.py), [`app/services/bgl_ingestion.py`](app/services/bgl_ingestion.py) | Parser versions, exact bytes and offsets, batches committed with their checkpoint, resume rules |
| 6 | [`app/services/detection.py`](app/services/detection.py), [`app/services/window_detection.py`](app/services/window_detection.py) | Snapshot-based runs, label-blind features, chronological splits, thresholds chosen on validation |
| 7 | [`app/services/database_evidence.py`](app/services/database_evidence.py) | How a finding is traced back to raw bytes, provenance and related anomalies |
| 8 | [`app/models.py`](app/models.py), [`app/domain.py`](app/domain.py), [`migrations/versions`](migrations/versions) | Composite dataset keys, CHECK constraints, indexes; migrations are immutable history |
| 9 | [`app/security.py`](app/security.py), [`app/permissions.py`](app/permissions.py) | Authentication, RBAC, CSRF, CSP nonces, owner-only storage |
| 10 | [`app/workbench/api.py`](app/workbench/api.py), [`app/workbench/files.py`](app/workbench/files.py), [`app/workbench/platforms`](app/workbench/platforms) | The local capability API, the root sandbox and the per-OS integration |
| 11 | [`scripts/run/supervision.py`](scripts/run/supervision.py), [`app/services/alerts.py`](app/services/alerts.py) | Worker back-off and recovery; the alert outbox and its failure modes |

Supporting material: [code structure map](docs/development/CODE_STRUCTURE_VI.md),
[API reference](docs/database/API.md), [schema](docs/database/SCHEMA.md),
[detector semantics](docs/database/DETECTORS.md).

## Verify the README

Every quantitative or behavioural claim in the README can be checked. Start here:

| Claim | How to verify |
| --- | --- |
| Static analysis is clean | `ruff check . && ruff format --check . && mypy --platform linux && mypy --platform win32 && mypy --platform darwin` |
| 240+ tests without a database | `python -B -m unittest discover -s tests` (the MySQL suites are reported as skipped) |
| 125 MySQL integration tests | `python -m scripts.qa.verify_mysql` with the container above; the report ends with `"mysql_integration": "PASS"` |
| Migration history matches the models | `test_02_migration_schema_matches_models` in [`tests/test_mysql_integration.py`](tests/test_mysql_integration.py) runs `compare_metadata` against a freshly migrated schema |
| Dataset isolation is enforced in SQL | `test_06` to `test_08` and `test_22`/`test_23` in the same file insert cross-dataset references and expect the database to reject them |
| Labels never reach the detectors | `test_12_window_features_deterministic_no_labels` in [`tests/test_platform_mysql.py`](tests/test_platform_mysql.py); `features()` in [`detection.py`](app/services/detection.py) takes only message and severity |
| Ingestion resumes safely after a crash | `test_16`/`test_17` in `test_mysql_integration.py`; `python -m scripts.qa.verify_import_restart` kills a worker mid-import |
| CSP blocks injected script | [`tests/test_workbench.py`](tests/test_workbench.py) `ContentSecurityPolicyTest`; inspect any HTML response header |
| Catalogs are whole messages | [`tests/test_i18n.py`](tests/test_i18n.py) `CatalogShapeTest` (over 17,000 checks) |
| Browser behaviour | `python -m scripts.qa.qa_workbench_browser`, `qa_investigation_v2`, `qa_evidence_drawer` |
| The package installs cleanly | `python -m scripts.release.package_workbench --output dist/ci` then `python -m scripts.release.qa_portfolio_install dist/ci --desktop` |

## Review checklists

### Correctness and data integrity

- [ ] Every multi-step write is one transaction, or its partial state is detectable and recoverable.
- [ ] Re-running an operation (import, detection job, alert generation) is idempotent or explicitly rejected.
- [ ] Rows that belong to a dataset are always filtered by `dataset_id`; joins keep the dataset in the join key.
- [ ] Time is UTC end to end; intervals are half-open `[start, end)`; display time zones never change membership.
- [ ] Ordering used for paging or cut-offs has a unique tie-breaker (usually `id`).

### Machine learning and evaluation

- [ ] No feature, threshold or model selection reads labels or test-period data.
- [ ] Train, validation and test periods are chronological and disjoint; boundaries align to window edges.
- [ ] Metrics name their cohort, unit and label source; user-supplied labels stay separate.
- [ ] A frozen model is loaded only after its checksum is verified, and inference never refits.

### Security

- [ ] New routes declare their roles and dataset scope; the default is deny.
- [ ] Inputs are validated by type, range and size at the boundary; errors do not leak internals.
- [ ] No inline script or event handler is added to templates (the CSP would block it, by design).
- [ ] File paths from users go through the workbench sandbox; nothing follows symlinks out of the project.
- [ ] Secrets never appear in logs, URLs, error messages, fixtures or screenshots.

### Database and migrations

- [ ] Schema changes come with a new Alembic revision; existing revisions are never edited.
- [ ] Models and migrations agree (`compare_metadata` stays empty).
- [ ] New queries on large tables use an index that matches their filter and order.
- [ ] Queries are bounded (`limit`, keyset cursor or streaming with `yield_per`).

### API and interface

- [ ] Response shapes stay identical for the demo and database sources.
- [ ] User-visible text goes through `tr()`, `t()` or `tn()`, as a whole message, translated in every catalog.
- [ ] Controls are reachable by keyboard and have accessible names; motion respects reduced-motion settings.
- [ ] Behaviour is the same in the native window and in a browser.

### Cross-platform

- [ ] OS-specific code lives in `app/workbench/platforms`; shared code does not test `sys.platform`.
- [ ] Paths use `pathlib`; text files are read and written with an explicit encoding and newline policy.
- [ ] Installers keep CRLF for `.cmd` and LF with the executable bit for `.sh` and `.command`.

### Code quality

- [ ] Functions do one thing at one level of abstraction; long functions are split into named steps.
- [ ] Modules listed as typed in `pyproject.toml` stay fully annotated.
- [ ] Tests cover the behaviour, including the failure paths; refactors keep outputs identical.

## Intentional decisions

These are deliberate. Please challenge them in an issue if you disagree, but they are not defects.

| Decision | Why |
| --- | --- |
| Server-rendered pages and plain JavaScript, no bundler | One runtime for three OS web views and a browser; nothing to build or audit in a toolchain |
| English sentences as catalog keys | Readable templates and an automatic fallback; catalogs are checked for placeholder parity |
| `dict(key=value)` for JSON payloads | Consistent house style for response bodies (ruff rule C408 is disabled on purpose) |
| Nested `with` blocks for a lease around a transaction | They read as two boundaries; combining them hides the lock scope |
| Gradual typing | Core modules are strict; the rest is annotated as it changes |
| A synthetic demo source | Lets the investigation interface run without a database; it is always labelled as synthetic |
| Isolation Forest as the main model | A transparent baseline; the evaluation discipline matters more than the model family here |
| Vietnamese documents beside English ones | The project began as Vietnamese coursework; user-facing documentation is kept in both languages |

## Severity guide

| Level | Meaning | Examples |
| --- | --- | --- |
| **Blocker** | Data loss or corruption, a security hole, wrong results presented as correct | Cross-dataset access, a label leaking into features, an unbounded query on raw logs |
| **Major** | A feature fails for real users, or a guarantee in the docs does not hold | A route returns 500 on valid input, a resume duplicates rows |
| **Minor** | Works, but is fragile, inconsistent or hard to maintain | A missing tie-breaker, an untranslated message, a long function |
| **Nit** | Style or wording | Naming, comments, formatting not caught by the tools |
