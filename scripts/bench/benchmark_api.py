"""Measured loopback HTTP/SQL latency on real imported BGL prefixes."""

from datetime import datetime
import http.cookiejar
import json
import logging
import math
import os
from pathlib import Path
import statistics
import threading
import time
import urllib.parse
import urllib.request

import psutil
from sqlalchemy import event, text
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def distribution(values):
    return {
        "p50": statistics.median(values),
        "p95": sorted(values)[math.ceil(0.95 * len(values)) - 1],
    }


def main():
    app = create_app()
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    sql_times = []
    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, "before_cursor_execute")
        def before(connection, cursor, statement, parameters, context, many):
            context.qa_started = time.perf_counter()

        @event.listens_for(engine, "after_cursor_execute")
        def after(connection, cursor, statement, parameters, context, many):
            sql_times.append((time.perf_counter() - context.qa_started) * 1000)

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    request = urllib.request.Request(
        base + "/api/v1/auth/login",
        data=json.dumps(
            {
                "username": os.environ["QA_USERNAME"],
                "password": os.environ["QA_PASSWORD"],
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    report = []
    process = psutil.Process()
    peak = process.memory_info().rss
    try:
        opener.open(request, timeout=20).read()
        datasets = json.loads(opener.open(base + "/api/v1/logs/datasets").read())["datasets"]
        for dataset in datasets:
            query = urllib.parse.urlencode(
                {
                    "dataset_id": dataset["id"],
                    "start_time": dataset["start_time"],
                    "end_time": dataset["end_time"],
                    "limit": 50,
                }
            )
            for endpoint in ("/api/v1/logs", "/api/v1/logs/timeline"):
                values = []
                database = []
                sizes = []
                count = None
                for _ in range(20):
                    previous = len(sql_times)
                    started = time.perf_counter()
                    raw = opener.open(base + endpoint + "?" + query, timeout=30).read()
                    values.append((time.perf_counter() - started) * 1000)
                    sizes.append(len(raw))
                    database.append(sum(sql_times[previous:]))
                    count = json.loads(raw)["count"]
                    peak = max(peak, process.memory_info().rss)
                report.append(
                    {
                        "endpoint": endpoint,
                        "dataset_id": dataset["id"],
                        "parsed_events_in_scope": count,
                        "requests": 20,
                        "http_ms": distribution(values),
                        "sql_total_per_request_ms": distribution(database),
                        "payload_bytes_max": max(sizes),
                        "http_requests_per_second_serial": 20000 / sum(values),
                    }
                )
        dataset_id = int(os.environ["QA_DATASET_ID"])
        values = []
        sizes = []
        for _ in range(20):
            started = time.perf_counter()
            raw = opener.open(base + f"/api/v1/investigation?source=db-{dataset_id}", timeout=30).read()
            values.append((time.perf_counter() - started) * 1000)
            sizes.append(len(raw))
            data = json.loads(raw)
        report.append(
            {
                "endpoint": "/api/v1/investigation",
                "dataset_id": dataset_id,
                "anomalies_in_scope": data["scope_count"],
                "requests": 20,
                "http_ms": distribution(values),
                "payload_bytes_max": max(sizes),
            }
        )
        with app.app_context(), engine.connect() as connection:
            plans = {}
            for dataset in datasets:
                q = "SELECT id,timestamp FROM log_events WHERE dataset_id=:ds AND timestamp>=:start AND timestamp<:end ORDER BY timestamp,id LIMIT 50"
                binds = {
                    "ds": dataset["id"],
                    "start": datetime.fromisoformat(dataset["start_time"].replace("Z", "+00:00")).replace(
                        tzinfo=None
                    ),
                    "end": datetime.fromisoformat(dataset["end_time"].replace("Z", "+00:00")).replace(
                        tzinfo=None
                    ),
                }
                plans[str(dataset["id"])] = {
                    "json": json.loads(
                        connection.execute(text("EXPLAIN FORMAT=JSON " + q), binds).scalar_one()
                    ),
                    "analyze": connection.execute(text("EXPLAIN ANALYZE " + q), binds).scalar_one(),
                }
            mysql = connection.execute(text("SELECT VERSION()")).scalar_one()
        result = {
            "mysql": mysql,
            "schema": engine.url.database,
            "measurements": report,
            "sql_explain": plans,
            "peak_process_rss_mib": peak / 1024**2,
            "memory_scope": "API loopback server and benchmark client in one Python process; excludes mysqld",
            "conditions": "20 sequential warm loopback HTTP requests per endpoint and dataset; login excluded. Existing workstation/schema, no synthetic counts.",
            "before_same_workload": "NOT RUN: real log API and real-data investigation adapter did not exist at the original baseline. Fixture latency is not a valid before comparison.",
        }
        (REPO_ROOT / "docs/database/measurements/api-performance.json").write_text(
            json.dumps(result, indent=2)
        )
        print(json.dumps({k: v for k, v in result.items() if k != "sql_explain"}, indent=2))
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
