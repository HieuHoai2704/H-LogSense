# Database, BGL ingestion and detector foundation

This implements the persistence layer inside the existing Flask application.
The public default workspace remains an explicitly synthetic demo. Authenticated
Log Explorer and MySQL Investigation modes now connect actual imported data while
preserving the existing Investigation V2 layout and stylesheet.

- [Initial audit and verified fixes](DATABASE_AUDIT.md)
- [Entity relationships](ERD.md)
- [Schema and invariants](SCHEMA.md)
- [Migrations](MIGRATIONS.md)
- [Queries and indexes](QUERY_AND_INDEX_STRATEGY.md)
- [BGL parser and import](BGL_PIPELINE.md)
- [Detector semantics](DETECTORS.md)
- [Windows/macOS operating runbook](MYSQL_RUNBOOK.md)
- [Tests](TESTING.md)
- [REST API and authorization](API.md)
- [Course/roadmap traceability](TRACEABILITY.md)
- [Measured results and limits](IMPLEMENTATION_REPORT.md)

Use Python 3.10+ in a virtual environment. Install `requirements.txt`. There is no
SQLite fallback, automatic schema creation, public real-log endpoint or background
worker started by importing the Flask app. `DATABASE_URL` is optional for the demo.
Testing selects `TEST_DATABASE_URL` and never falls back to the development URL.
Load environment variables explicitly; `.env.example` is documentation, not a
configuration loader. Never put real URLs/passwords into source or shell history.

MySQL 8.0.16+ is required for enforced CHECK constraints; verification here uses
MySQL Community 8.4.7. MariaDB is not silently treated as MySQL.

Real-data HTTP access requires login and a dataset grant, or an optional read-only
operator token plus explicit allow-list. Mutations require role permission and
CSRF protection. This is minimum local RBAC, not production identity federation.
All private routes deny access by default; changing a source parameter alone
cannot authorize access.
