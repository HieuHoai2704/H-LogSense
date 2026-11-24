"""Provision NEW token-marked test schemas, migrate and test; never drop/reset.

Requires MYSQL_ADMIN_URL and DATABASE_URL in the process environment. The admin
must be authorized to create unique test schemas and grant the existing local
application user privileges. Credentials are never accepted as CLI arguments.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    admin_url = make_url(os.environ["MYSQL_ADMIN_URL"])
    app_url = make_url(os.environ["DATABASE_URL"])
    if admin_url.drivername != "mysql+pymysql" or app_url.drivername != "mysql+pymysql":
        raise ValueError("Real MySQL URLs required.")
    if (admin_url.host, admin_url.port) != (app_url.host, app_url.port):
        raise ValueError("Admin/application server mismatch.")
    if not re.fullmatch(r"[a-zA-Z0-9_]+", app_url.username or ""):
        raise ValueError("Use a simple existing application user name.")
    # The account host the grants go to. A server in a container sees host connections from its
    # bridge address, so such a setup uses an existing 'user'@'%' account (MYSQL_GRANT_HOST=%).
    grant_host = os.environ.get("MYSQL_GRANT_HOST", "localhost")
    if not re.fullmatch(r"[A-Za-z0-9_.%-]+", grant_host):
        raise ValueError("MYSQL_GRANT_HOST must be a plain host name, address or %.")
    token = secrets.token_hex(32)
    schema_names = []
    engine = create_engine(admin_url, hide_parameters=True)
    with engine.begin() as connection:
        for _ in range(2):
            schema = "logsense_test_" + secrets.token_hex(6)
            # Identifiers are generated locally, validated here, and never user SQL.
            assert re.fullmatch(r"logsense_test_[0-9a-f]{12}", schema)
            connection.execute(
                text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs")
            )
            connection.execute(
                text(
                    f"CREATE TABLE `{schema}`.logsense_test_guard (token_hash CHAR(64) NOT NULL) ENGINE=InnoDB"
                )
            )
            connection.execute(
                text(f"INSERT INTO `{schema}`.logsense_test_guard VALUES (:token)"),
                {"token": hashlib.sha256(token.encode()).hexdigest()},
            )
            connection.execute(
                text(
                    f"GRANT SELECT,INSERT,UPDATE,CREATE,ALTER,INDEX,REFERENCES ON `{schema}`.* TO '{app_url.username}'@'{grant_host}'"
                )
            )
            schema_names.append(schema)
    engine.dispose()
    os.environ.update(
        LOGSENSE_RUN_MYSQL_TESTS="1",
        LOGSENSE_TEST_TOKEN=token,
        TEST_DATABASE_URL=app_url.set(database=schema_names[0]).render_as_string(hide_password=False),
        SECOND_TEST_DATABASE_URL=app_url.set(database=schema_names[1]).render_as_string(hide_password=False),
    )
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*mysql*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schemas": schema_names,
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "mysql_integration": "PASS" if result.wasSuccessful() and not result.skipped else "INCOMPLETE",
        "cleanup": "No database/table/volume dropped. Generated fixtures retained.",
    }
    destination = REPO_ROOT / ".local/database-verification"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "integration-results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
