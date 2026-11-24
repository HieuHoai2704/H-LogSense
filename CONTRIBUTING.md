# Contributing to H-logsen

This document describes how to set up a development environment and the standards every change must meet.
For a guided review of the existing code, see [REVIEWING.md](REVIEWING.md).

## Development setup

```bash
python -m venv .venv && . .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,qa]"
pre-commit install                                        # ruff check, ruff format and mypy on every commit
python -m playwright install chromium                     # browser end-to-end tests
```

On Linux the native window additionally needs the system GTK and WebKitGTK bindings; see
[packaging/posix/CAI_DAT_MAC_LINUX.txt](packaging/posix/CAI_DAT_MAC_LINUX.txt).

## Workflow

1. Branch from `main`: `feature/<topic>`, `fix/<topic>`, `refactor/<topic>` or `docs/<topic>`.
2. Keep each pull request to one purpose. A mechanical change (formatting, renames) goes in its own commit,
   and formatting-only commits are added to `.git-blame-ignore-revs`.
3. Write commit messages in the [Conventional Commits](https://www.conventionalcommits.org/) form used in
   the history: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `style:`. The body explains *why*
   and how the change was verified.
4. Open a pull request using the template and make sure CI is green.

## Standards

### Code

- `ruff check .`, `ruff format --check .` and `mypy` must pass. Configuration is in `pyproject.toml`.
- Modules listed under the strict mypy override must stay fully annotated; prefer adding a module to that
  list over leaving new code untyped.
- Shared shapes belong in `app/contracts.py`. Routes stay thin; logic lives in `app/services`.
- Every query has a bound: a `limit`, a keyset cursor or streaming with `yield_per`. Paging order ends with
  a unique column.
- OS-specific code goes in `app/workbench/platforms`; shared code does not branch on the platform.

### Data and machine learning

- Detectors and features never read labels. Splits are chronological; thresholds come from validation data.
- A run works on a snapshot (`input_revision`, highest event id) and publishes nothing if the dataset changed.
- Schema changes need a new Alembic revision. Never edit an existing revision. The model and migration
  histories must stay identical (`test_02_migration_schema_matches_models`).

### Interface and languages

- No inline `<script>` content or `on*=` attributes: the Content Security Policy blocks them. Put behaviour
  in a module under `app/static`.
- User-visible text is a whole message passed to `tr()` (templates and Python), `t()` or `tn()` (JavaScript).
  Never build a sentence from translated fragments. Use `tn(count, singular, plural, ...values)` for text
  that depends on a number.
- Add every new message to all 14 catalogs in `app/locales`. `tests/test_i18n.py` checks that each
  translation keeps the placeholders of its English source and that plural forms use CLDR categories.

### Tests

- Every behaviour change comes with a test, including its failure path.
- Changes to SQL or to services that use the database also run the MySQL suite (see below).
- Refactors keep outputs identical. For large ones, fingerprint the outputs over many generated inputs before
  and after the change and include the result in the pull request.

## Running the test suites

```bash
python -B -m unittest discover -s tests                  # unit and API tests
python -B -m unittest discover -s academic -t .          # research experiments
python -m scripts.qa.qa_workbench_browser                 # workbench end-to-end
python -m scripts.qa.qa_investigation_v2                  # investigation end-to-end
python -m scripts.qa.qa_evidence_drawer                   # evidence drawer end-to-end
```

MySQL integration tests run only against new, token-marked schemas created by `scripts.qa.verify_mysql`; they
never touch existing databases. With MySQL in a container:

```bash
docker run -d --name hlogsen-mysql -p 127.0.0.1:3307:3306 -e MYSQL_ROOT_PASSWORD=change-me mysql:8.4
docker exec -i hlogsen-mysql mysql -uroot -pchange-me -e "CREATE USER 'logsense'@'%' IDENTIFIED BY 'change-me-too'"
export MYSQL_ADMIN_URL="mysql+pymysql://root:change-me@127.0.0.1:3307/mysql"
export DATABASE_URL="mysql+pymysql://logsense:change-me-too@127.0.0.1:3307/logsense_dev"
export MYSQL_GRANT_HOST=%
python -m scripts.qa.verify_mysql
```

The packaged application is verified with a clean install:

```bash
python -m scripts.release.package_workbench --output dist/ci
python -m scripts.release.qa_portfolio_install dist/ci --desktop
```

## Pull request checklist

- [ ] Lint, format and type checks pass.
- [ ] Tests added or updated; the unit suite passes; the MySQL suite passes when SQL changed.
- [ ] User-visible text is translated in every catalog.
- [ ] Documentation updated (README, guides, API reference) where behaviour changed.
- [ ] No secrets, personal paths or real research data in code, fixtures or screenshots.
