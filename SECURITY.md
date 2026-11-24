# Security policy

## Reporting a vulnerability

Please do not report security problems in public issues or pull requests.

Use GitHub's private reporting instead: open the repository's **Security** tab and choose
**Report a vulnerability**. Include the affected version or commit, the steps or input that trigger the
problem, and its impact. You will receive an acknowledgement, and a fix or a mitigation will be coordinated
with you before any details are made public.

## Supported versions

Only the latest commit on `main` receives security fixes while the project is in preview (0.x).

## Scope

In scope:

- The Flask application and its REST API (`app/`), including authentication, authorization and CSRF.
- The workbench capability API (`/api/local/v1`): the token, the project-root sandbox, terminals and runs.
- Ingestion, uploads and the handling of untrusted log content (parsing, redaction, rendering).
- Installers and launchers in `packaging/`.

Out of scope:

- Exposing the workbench on a non-loopback interface or a shared account; it is designed for one local user.
- Denial of service from a local user who already controls the machine.
- Findings that require a compromised operating system account.

## Security design

The controls and their rationale are summarized in the [README](README.md#security-model). Relevant code:

| Area | Code |
| --- | --- |
| Sessions, roles, CSRF, CSP, error handling | [`app/security.py`](app/security.py) |
| Owner-only files | [`app/permissions.py`](app/permissions.py) |
| Workbench token, Host and Origin checks | [`app/workbench/api.py`](app/workbench/api.py) |
| Project-root sandbox and file-name rules | [`app/workbench/files.py`](app/workbench/files.py) |
| Redaction of displayed logs | [`app/services/redaction.py`](app/services/redaction.py) |
| Upload validation and staging | [`app/services/uploads.py`](app/services/uploads.py) |
