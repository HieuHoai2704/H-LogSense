"""Verify mysql.connector CRUD on a dedicated schema and save a Workbench worksheet."""

import argparse
import csv
import json
from pathlib import Path
from secrets import token_hex

import mysql.connector

from scripts.mysql_runtime import connect, load, owned_root, status


def run(runtime_root, source_csv, output):
    root = owned_root(runtime_root)
    status(root)
    info = load(root)
    with source_csv.open(newline="", encoding="utf-8-sig") as handle:
        row = next(csv.DictReader(handle), None)
    if row is None:
        raise ValueError("The exported log CSV must contain at least one row.")
    event_id = int(row["id"])
    host = row["host"][:200]
    if not 0 < event_id < 2**63 or not host:
        raise ValueError("The first exported record must have a valid ID and host.")
    output.mkdir(parents=True, exist_ok=False)
    schema = "logsense_course_" + token_hex(6)
    with connect(info) as admin, admin.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4")
        cursor.execute(f"""CREATE TABLE `{schema}`.log_references (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_id BIGINT UNSIGNED NOT NULL,
            source_host VARCHAR(200) NOT NULL,
            reviewed BOOLEAN NOT NULL DEFAULT FALSE
        ) ENGINE=InnoDB""")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{schema}`.log_references TO 'logsense_app'@'localhost'")

    with mysql.connector.connect(host="127.0.0.1", port=info["port"], database=schema,
                                 user="logsense_app", password=info["app_password"],
                                 connection_timeout=5) as connection, connection.cursor() as cursor:
        cursor.execute("INSERT INTO log_references (event_id, source_host) VALUES (%s, %s)", (event_id, host))
        reference = cursor.lastrowid
        cursor.execute("SELECT event_id, source_host, reviewed FROM log_references WHERE id=%s", (reference,))
        inserted = cursor.fetchone()
        if inserted != (event_id, host, 0):
            raise RuntimeError("INSERT/SELECT mismatch.")
        cursor.execute("UPDATE log_references SET reviewed=TRUE WHERE id=%s", (reference,))
        cursor.execute("SELECT reviewed FROM log_references WHERE id=%s", (reference,))
        if cursor.fetchone() != (1,):
            raise RuntimeError("UPDATE/SELECT mismatch.")
        cursor.execute("DELETE FROM log_references WHERE id=%s", (reference,))
        cursor.execute("SELECT COUNT(*) FROM log_references WHERE id=%s", (reference,))
        if cursor.fetchone() != (0,):
            raise RuntimeError("DELETE mismatch.")
        connection.commit()

    host_hex = host.encode("utf-8").hex()
    (output / "workbench.sql").write_text(f"""-- Open in MySQL Workbench on 127.0.0.1:{info["port"]} as logsense_app.
-- This worksheet uses the dedicated course schema and rolls back its own changes.
USE `{schema}`;
SHOW TABLES;
SHOW COLUMNS FROM log_references;
START TRANSACTION;
INSERT INTO log_references (event_id, source_host)
VALUES ({event_id}, CONVERT(0x{host_hex} USING utf8mb4));
SET @course_reference = LAST_INSERT_ID();
SELECT * FROM log_references WHERE id = @course_reference;
UPDATE log_references SET reviewed = TRUE WHERE id = @course_reference;
SELECT * FROM log_references WHERE id = @course_reference;
DELETE FROM log_references WHERE id = @course_reference;
SELECT COUNT(*) AS remaining FROM log_references WHERE id = @course_reference;
ROLLBACK;
""", encoding="utf-8")
    result = {"schema": schema, "port": info["port"], "source_event_id": event_id,
              "connector": mysql.connector.__version__, "insert_read_update_delete": "PASS",
              "worksheet": "workbench.sql", "workbench_gui": "not_run"}
    (output / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default=".local/university-e2e-mysql")
    parser.add_argument("--source-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.runtime, args.source_csv, args.output), indent=2))
    except (mysql.connector.Error, OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Course SQL verification failed ({type(error).__name__}).\n")


if __name__ == "__main__":
    main()
