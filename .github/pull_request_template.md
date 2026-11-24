## Summary

<!-- What changes and why. Link the issue it resolves. -->

## How it was verified

<!-- Commands run and their results. For refactors, how outputs were shown to be unchanged. -->

- [ ] `ruff check . && ruff format --check . && mypy`
- [ ] `python -B -m unittest discover -s tests`
- [ ] `python -m scripts.qa.verify_mysql` (required when SQL or database services changed)
- [ ] Browser end-to-end tests (required when the interface changed)

## Checklist

- [ ] One purpose per pull request; mechanical changes in their own commits
- [ ] Tests cover the new behaviour and its failure paths
- [ ] User-visible text is a whole message, translated in every catalog
- [ ] Schema changes come with a new migration; existing migrations are unchanged
- [ ] Documentation updated where behaviour changed
- [ ] No secrets, personal paths or real research data in code, fixtures or screenshots
