"""Real BGL release verification in a NEW schema on an owned QA MySQL runtime.

No existing dataset is reset. Private account settings stay under .local.
Stages run in separate processes; restart only the dedicated QA runtime.
"""

import argparse
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade
import psutil
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app import create_app
from app.domain import DetectionPrediction, EvaluationReport, User, UserDataset
from app.extensions import db
from app.models import (
    AnomalyOutput,
    Dataset,
    DataSource,
    DetectionUnit,
    DetectorRun,
    GroundTruthLabel,
    LogEvent,
    ProcessingJob,
    RawLogRecord,
    SourceArtifact,
)
from app.services.bgl_ingestion import ingest_bgl
from scripts.bench.benchmark_bgl import verify_provenance
from scripts.run.mysql_runtime import load, owned_root, private_write, start, status, stop

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]

PRIVATE = REPO_ROOT / ".local/university-qa/e2e"
REPORT = REPO_ROOT / "docs/releases/measurements/university-mvp-v1"


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def runtime_url(root, role, schema):
    settings = load(root)
    username, key = {
        "app": ("logsense_app", "app_password"),
        "migrate": ("logsense_migrator", "migrator_password"),
        "root": ("root", "root_password"),
    }[role]
    return URL.create(
        "mysql+pymysql",
        username=username,
        password=settings[key],
        host="127.0.0.1",
        port=settings["port"],
        database=schema,
    )


def app_for(root, context, role="app"):
    return create_app(
        {
            "SQLALCHEMY_DATABASE_URI": runtime_url(root, role, context["schema"]),
            "SECRET_KEY": context["secret_key"],
        }
    )


def timed(call):
    begin = time.perf_counter()
    value = call()
    return value, time.perf_counter() - begin


def setup(root, archive, lines):
    if (PRIVATE / "context.json").exists():
        raise ValueError("Existing E2E context retained; never silently reuse/reset it.")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    ready = status(root)
    if ready["port"] != 13307:
        raise ValueError("Dedicated QA runtime on port 13307 required.")
    schema = "logsense_bench_" + secrets.token_hex(6)
    admin = create_engine(runtime_url(root, "root", "mysql"), hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(
            text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs")
        )
        connection.execute(text(f"GRANT SELECT,INSERT,UPDATE ON `{schema}`.* TO 'logsense_app'@'localhost'"))
        connection.execute(
            text(
                f"GRANT SELECT,INSERT,UPDATE,CREATE,ALTER,INDEX,REFERENCES ON `{schema}`.* TO 'logsense_migrator'@'localhost'"
            )
        )
    admin.dispose()
    context = {
        "schema": schema,
        "secret_key": secrets.token_hex(32),
        "username": "university-qa-" + secrets.token_hex(6),
        "password": secrets.token_urlsafe(24),
        "archive": str(archive.resolve()),
        "line_target": lines,
        "runtime_root": str(root),
    }
    migration_app = app_for(root, context, "migrate")
    with migration_app.app_context():
        _, migration_seconds = timed(upgrade)
        with db.engine.connect() as connection:
            head = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            diff = compare_metadata(MigrationContext.configure(connection), db.metadata)
        assert head == "0004" and not diff, "Migration/model difference"
        db.engine.dispose()
    app = app_for(root, context)
    with app.app_context():
        with Session(db.engine) as session, session.begin():
            source = DataSource(
                source_key="release-bgl-" + secrets.token_hex(8), name="Actual Loghub BGL University E2E"
            )
            session.add(source)
            session.flush()
            datasets = [
                Dataset(source_id=source.id, dataset_key=key, name=name, data_mode="real")
                for key, name in (
                    ("main-bgl", "Actual BGL 100K release E2E"),
                    ("forbidden-bgl", "Actual BGL restricted dataset"),
                    ("empty-bgl", "Authorized empty dataset"),
                )
            ]
            session.add_all(datasets)
            session.flush()
            context.update(
                dataset_id=datasets[0].id,
                forbidden_dataset_id=datasets[1].id,
                empty_dataset_id=datasets[2].id,
            )
            user = User(
                username=context["username"],
                password_hash=generate_password_hash(context["password"]),
                role="manager",
            )
            session.add(user)
            session.flush()
            session.add_all(
                [UserDataset(user_id=user.id, dataset_id=d.id) for d in (datasets[0], datasets[2])]
            )
        private_write(PRIVATE / "context.json", json.dumps(context))
        stages = []
        main = context["dataset_id"]
        first, elapsed = timed(lambda: ingest_bgl(db.engine, main, archive, limit=1000))
        stages.append({"target": 1000, "seconds": elapsed, "result": first})

        def interrupt(line):
            if line >= 1500:
                raise RuntimeError("Owned E2E rollback injection before batch commit")

        try:
            ingest_bgl(db.engine, main, archive, limit=2000, before_commit=interrupt)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Rollback hook did not execute")
        with Session(db.engine) as session:
            checkpoint = session.scalar(
                select(SourceArtifact.checkpoint_line).where(SourceArtifact.dataset_id == main)
            )
            raw_count = session.scalar(
                select(func.count()).select_from(RawLogRecord).where(RawLogRecord.dataset_id == main)
            )
        assert checkpoint == raw_count == 1000
        for target in (10000, lines):
            result, elapsed = timed(lambda target=target: ingest_bgl(db.engine, main, archive, limit=target))
            stages.append({"target": target, "seconds": elapsed, "result": result})
        proof, proof_seconds = timed(lambda: verify_provenance(db.engine, main, archive))
        again, repeat_seconds = timed(lambda: ingest_bgl(db.engine, main, archive, limit=lines))
        assert again["physical_lines"] == lines and proof["duplicate_lines"] == 0
        other = ingest_bgl(db.engine, context["forbidden_dataset_id"], archive, limit=1000)
        with db.engine.connect() as connection:
            version, zone = connection.execute(text("SELECT VERSION(),@@time_zone")).one()
            explain = (
                connection.execute(
                    text(
                        "EXPLAIN SELECT id,timestamp FROM log_events WHERE dataset_id=:ds AND timestamp>=:a AND timestamp<:b ORDER BY timestamp,id LIMIT 50"
                    ),
                    {"ds": main, "a": "2005-06-03", "b": "2005-06-06"},
                )
                .mappings()
                .all()
            )
        db.engine.dispose()
    report = {
        "status": "PASS",
        "data": "actual immutable Loghub BGL prefix",
        "schema": schema,
        "dataset_id": main,
        "restricted_dataset_id": context["forbidden_dataset_id"],
        "lines": lines,
        "mysql": version,
        "timezone": zone,
        "port": 13307,
        "migrations": {"head": head, "model_diff": [], "seconds": migration_seconds, "status": "PASS"},
        "imports": stages,
        "rollback": {"status": "PASS", "checkpoint_after_injected_failure": checkpoint},
        "provenance": proof,
        "provenance_seconds": proof_seconds,
        "repeat_import": {"seconds": repeat_seconds, "result": again, "status": "PASS"},
        "restricted_dataset_imported_lines": other["physical_lines"],
        "log_query_explain": [dict(row) for row in explain],
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    save(PRIVATE / "setup.json", report)
    save(REPORT / "setup.json", report)
    print(
        json.dumps(
            {
                "setup": "PASS",
                "dataset_id": main,
                "lines": lines,
                "import_seconds": [s["seconds"] for s in stages],
                "raw_sha256": proof["raw_prefix_sha256"],
            }
        ),
        flush=True,
    )


def login(app, context):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/login", json={"username": context["username"], "password": context["password"]}
    )
    assert response.status_code == 200
    return client, {"X-CSRF-Token": response.json["csrf_token"]}


def detect(root, kind):
    context = read(PRIVATE / "context.json")
    app = app_for(root, context)
    import app.services.window_detection as wd
    from scripts.run.worker import run_once

    counters = {
        "feature_stream_seconds": 0.0,
        "feature_units": 0,
        "fit_seconds": 0.0,
        "score_seconds": 0.0,
        "persist_seconds": 0.0,
        "evaluation_seconds": 0.0,
        "sql_seconds": 0.0,
        "sql_statements": 0,
    }
    original_aggregate, original_fit = wd.aggregate_windows, wd.IsolationForest.fit
    original_score, original_persist, original_evaluate = (
        wd.IsolationForest.score_samples,
        wd.persist_predictions,
        wd.evaluate_windows,
    )

    def aggregate(*args, **kwargs):
        iterator = iter(original_aggregate(*args, **kwargs))
        while True:
            begin = time.perf_counter()
            try:
                record = next(iterator)
            except StopIteration:
                counters["feature_stream_seconds"] += time.perf_counter() - begin
                break
            counters["feature_stream_seconds"] += time.perf_counter() - begin
            counters["feature_units"] += 1
            yield record

    def measured(key, function):
        def invoke(*args, **kwargs):
            begin = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                counters[key] += time.perf_counter() - begin

        return invoke

    peak = [psutil.Process().memory_info().rss]
    done = threading.Event()

    def monitor():
        while not done.wait(0.02):
            peak[0] = max(peak[0], psutil.Process().memory_info().rss)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        with app.app_context():
            client, headers = login(app, context)
            body = {
                "dataset_id": context["dataset_id"],
                "idempotency_key": "release-e2e-" + kind,
                "configuration": {"detector": kind, "window_seconds": 300, "seed": 42},
            }
            queued, queue_seconds = timed(
                lambda: client.post("/api/v1/detection/jobs", json=body, headers=headers)
            )
            assert queued.status_code == 202
            job_id = queued.json["job_id"]
            assert client.post("/api/v1/detection/jobs", json=body, headers=headers).json["job_id"] == job_id

            @event.listens_for(db.engine, "before_cursor_execute")
            def before(connection, cursor, statement, parameters, context, many):
                context._qa_start = time.perf_counter()

            @event.listens_for(db.engine, "after_cursor_execute")
            def after(connection, cursor, statement, parameters, context, many):
                counters["sql_seconds"] += time.perf_counter() - context._qa_start
                counters["sql_statements"] += 1

            with (
                patch.object(wd, "aggregate_windows", aggregate),
                patch.object(wd.IsolationForest, "fit", measured("fit_seconds", original_fit)),
                patch.object(wd.IsolationForest, "score_samples", measured("score_seconds", original_score)),
                patch.object(wd, "persist_predictions", measured("persist_seconds", original_persist)),
                patch.object(wd, "evaluate_windows", measured("evaluation_seconds", original_evaluate)),
            ):
                executed, worker_seconds = timed(lambda: run_once(db.engine))
            assert executed
            with Session(db.engine) as session:
                job = session.get(ProcessingJob, job_id)
                assert job.state == "completed", "Worker did not complete"
                run = session.get(DetectorRun, job.result["run_id"])
                predictions = session.scalar(
                    select(func.count())
                    .select_from(DetectionPrediction)
                    .where(DetectionPrediction.run_id == run.id)
                )
                flags = session.scalar(
                    select(func.count())
                    .select_from(DetectionPrediction)
                    .where(DetectionPrediction.run_id == run.id, DetectionPrediction.predicted.is_(True))
                )
                anomalies = session.scalar(
                    select(func.count()).select_from(AnomalyOutput).where(AnomalyOutput.run_id == run.id)
                )
                metrics = session.scalar(
                    select(EvaluationReport.metrics).where(EvaluationReport.run_id == run.id)
                )
                assert predictions == run.evaluated_units == run.configuration["split_counts"]["test"]
                assert flags == anomalies and run.state == "completed"
                report = {
                    "status": "PASS",
                    "kind": kind,
                    "job_id": job_id,
                    "run_id": run.id,
                    "queue_seconds_inprocess": queue_seconds,
                    "worker_seconds": worker_seconds,
                    "evaluated_units": predictions,
                    "anomaly_outputs": anomalies,
                    "configuration": run.configuration,
                    "metrics": metrics,
                    "timings": counters,
                    "sampling_note": "Existing legacy policy, unchanged. Functional E2E, not model selection.",
                    "timing_note": "Feature stream includes DB reads; persist includes score calls and SQL. Timings overlap and must not be summed.",
                }
            db.engine.dispose()
    finally:
        done.set()
        thread.join(timeout=2)
    report["peak_rss_mib_sampled_20ms"] = peak[0] / 1048576
    save(PRIVATE / ("detect-" + kind + ".json"), report)
    save(REPORT / ("detect-" + kind + ".json"), report)
    print(
        json.dumps(
            {
                "detector": kind,
                "status": "PASS",
                "predictions": predictions,
                "outputs": anomalies,
                "worker_seconds": worker_seconds,
                "timings": counters,
            }
        ),
        flush=True,
    )


def normalized(value):
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def schema_checksums(engine):
    result = {}
    with engine.connect() as connection:
        names = (
            connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema=DATABASE() ORDER BY table_name"
                )
            )
            .scalars()
            .all()
        )
        for name in names:
            assert name.replace("_", "").isalnum()
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(text(f"SELECT * FROM `{name}` ORDER BY 1")).yield_per(500):
                digest.update(
                    json.dumps(list(row), default=normalized, sort_keys=True, separators=(",", ":")).encode()
                )
                count += 1
            result[name] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def verify(root, phase):
    context = read(PRIVATE / "context.json")
    app = app_for(root, context)
    with app.app_context():
        client, headers = login(app, context)
        ds = context["dataset_id"]
        with Session(db.engine) as session:
            first, last = session.execute(
                select(func.min(LogEvent.timestamp), func.max(LogEvent.timestamp)).where(
                    LogEvent.dataset_id == ds
                )
            ).one()
            runs = session.scalars(
                select(DetectorRun)
                .where(DetectorRun.dataset_id == ds, DetectorRun.state == "completed")
                .order_by(DetectorRun.id)
            ).all()
            output_count = session.scalar(
                select(func.count()).select_from(AnomalyOutput).where(AnomalyOutput.dataset_id == ds)
            )
            host, host_count = session.execute(
                select(DetectionUnit.host, func.count())
                .join(
                    AnomalyOutput,
                    (AnomalyOutput.dataset_id == DetectionUnit.dataset_id)
                    & (AnomalyOutput.unit_id == DetectionUnit.id),
                )
                .where(AnomalyOutput.dataset_id == ds)
                .group_by(DetectionUnit.host)
                .order_by(func.count().desc())
            ).first()
            run_ids = [r.id for r in runs]
            prediction_counts = {str(r.id): r.evaluated_units for r in runs}
        assert len(run_ids) == 2 and output_count > 0
        reused_jobs = []
        for kind in ("rule", "isolation_forest"):
            repeated = client.post(
                "/api/v1/detection/jobs",
                headers=headers,
                json={
                    "dataset_id": ds,
                    "idempotency_key": "release-e2e-" + kind,
                    "configuration": {"detector": kind, "window_seconds": 300, "seed": 42},
                },
            )
            assert repeated.status_code == 200 and repeated.json["state"] == "completed"
            reused_jobs.append(repeated.json["job_id"])
        params = {"source": "db-" + str(ds), "run_id": [str(r) for r in run_ids]}
        response = client.get("/api/v1/investigation", query_string=params)
        assert response.status_code == 200
        data = response.json
        assert data["scope_count"] == data["result_count"] == output_count
        assert sum(c["count"] for c in data["timeline"]["overall"]) == output_count
        assert len(data["events"]) <= data["state"]["limit"]
        all_csv_response = client.get("/api/v1/anomalies/export", query_string=params)
        assert all_csv_response.status_code == 200
        all_csv = list(csv.DictReader(io.StringIO(all_csv_response.text)))
        with Session(db.engine) as session:
            expected_ids = set(
                session.scalars(
                    select(AnomalyOutput.id).where(
                        AnomalyOutput.dataset_id == ds, AnomalyOutput.run_id.in_(run_ids)
                    )
                )
            )
        assert len(all_csv) == len(expected_ids) == output_count
        assert {int(r["id"][3:]) for r in all_csv} == expected_ids
        table_ids = []
        for number in range(1, data["page_count"] + 1):
            page_data = client.get("/api/v1/investigation", query_string=dict(params, page=number)).json
            table_ids.extend(int(r["id"][3:]) for r in page_data["events"])
        assert len(table_ids) == len(set(table_ids)) == output_count
        assert set(table_ids) == expected_ids
        host_scope = dict(params, host=host)
        host_data = client.get("/api/v1/investigation", query_string=host_scope).json
        assert host_data["scope_count"] == host_count
        cell = next(c for c in data["timeline"]["overall"] if c["count"])
        selection = dict(params, selection_start=cell["start"], selection_end=cell["end"])
        selected = client.get("/api/v1/investigation", query_string=selection).json
        assert selected["result_count"] == cell["count"]
        csv_response = client.get("/api/v1/anomalies/export", query_string=selection)
        assert csv_response.status_code == 200
        csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
        assert len(csv_rows) == selected["result_count"] == int(csv_response.headers["X-Result-Count"])
        assert data["state"]["dataset_mode"] == "real"
        assert all(r["id"].startswith("DB-") and int(r["run_id"]) in run_ids for r in csv_rows)
        anomaly = selected["events"][0]["id"]
        evidence = client.get(f"/api/v1/anomalies/{anomaly}/evidence", query_string=selection)
        assert evidence.status_code == 200
        material = evidence.json
        # Browser checks the rich drawer contract. Here verify bounded real provenance.
        assert material["mode"] == "database"
        raw = material["raw_event"]
        assert raw["provenance"]["source_line"] > 0 and raw["page"]["text"]
        log_params = {
            "dataset_id": ds,
            "start_time": first.isoformat(),
            "end_time": (last + timedelta(seconds=1)).isoformat(),
            "limit": 50,
        }
        logs = client.get("/api/v1/logs", query_string=log_params).json
        assert logs["count"] == context["line_target"] and len(logs["items"]) == 50
        scoped = dict(log_params, scope_token=logs["scope_token"])
        volume = client.get("/api/v1/logs/timeline", query_string=scoped).json
        assert volume["count"] == logs["count"]
        error_status = {
            "anonymous_private": app.test_client().get("/api/v1/logs/datasets").status_code,
            "other_dataset": client.get(
                "/api/v1/logs", query_string=dict(log_params, dataset_id=context["forbidden_dataset_id"])
            ).status_code,
            "invalid_limit": client.get(
                "/api/v1/logs", query_string=dict(log_params, limit=10001)
            ).status_code,
            "invalid_time": client.get(
                "/api/v1/logs", query_string=dict(log_params, start_time="invalid")
            ).status_code,
            "missing_evidence": client.get(
                "/api/v1/anomalies/DB-999999999/evidence", query_string=params
            ).status_code,
            "missing_csrf": client.post("/api/v1/detection/jobs", json={}).status_code,
        }
        assert error_status == {
            "anonymous_private": 403,
            "other_dataset": 403,
            "invalid_limit": 400,
            "invalid_time": 400,
            "missing_evidence": 404,
            "missing_csrf": 403,
        }
        empty = client.get(
            "/api/v1/logs", query_string=dict(log_params, dataset_id=context["empty_dataset_id"])
        ).json
        assert empty["count"] == 0 and empty["items"] == []
        demo = app.test_client().get("/api/v1/investigation?source=demo").json
        assert demo["mode"] == "demo" and demo["scope_count"] == 6
        checksums = schema_checksums(db.engine)
        report = {
            "status": "PASS",
            "phase": phase,
            "parsed_event_count": logs["count"],
            "anomaly_output_count": output_count,
            "evaluated_units_by_run": prediction_counts,
            "host_scope_count": host_count,
            "selection_scope_count": len(csv_rows),
            "timeline_table_csv_consistent": True,
            "raw_provenance": "PASS",
            "idempotent_completed_job_ids": reused_jobs,
            "error_statuses": error_status,
            "authorized_empty": "PASS",
            "demo_separate": "PASS",
            "anomaly_csv_sha256": hashlib.sha256(csv_response.data).hexdigest(),
            "full_csv_sha256": hashlib.sha256(all_csv_response.data).hexdigest(),
            "all_table_pages_match_full_csv_and_sql": True,
            "schema_checksums": checksums,
        }
        db.engine.dispose()
    if phase == "after":
        before = read(PRIVATE / "verify-before.json")
        assert checksums == before["schema_checksums"], "Rows changed across MySQL restart"
        assert report["anomaly_csv_sha256"] == before["anomaly_csv_sha256"]
        assert report["full_csv_sha256"] == before["full_csv_sha256"]
        report["all_table_restart_checksums"] = "PASS"
        report["csv_after_restart_identical"] = True
    save(PRIVATE / ("verify-" + phase + ".json"), report)
    save(REPORT / ("verify-" + phase + ".json"), report)
    print(json.dumps({k: v for k, v in report.items() if k != "schema_checksums"}), flush=True)


def browser(root, phase):
    context = read(PRIVATE / "context.json")
    env = dict(
        os.environ,
        DATABASE_URL=runtime_url(root, "app", context["schema"]).render_as_string(hide_password=False),
        FLASK_SECRET_KEY=context["secret_key"],
        QA_DATASET_ID=str(context["dataset_id"]),
        QA_OTHER_DATASET_ID=str(context["forbidden_dataset_id"]),
        QA_USERNAME=context["username"],
        QA_PASSWORD=context["password"],
        QA_OUTPUT=str(PRIVATE / "browser"),
        QA_PHASE=phase,
    )
    result = subprocess.run([sys.executable, "-m", "scripts.qa.qa_university_e2e_browser"], env=env)
    if result.returncode:
        raise RuntimeError("Browser E2E failed; inspect private diagnostic output.")
    source = PRIVATE / "browser" / ("browser-" + phase + ".json")
    save(REPORT / ("browser-" + phase + ".json"), read(source))


def restart(root):
    context = read(PRIVATE / "context.json")
    assert context["runtime_root"] == str(root)
    assert read(PRIVATE / "verify-before.json")["status"] == "PASS"
    assert read(PRIVATE / "browser" / "browser-before.json")["status"] == "PASS"
    assert status(root)["port"] == 13307
    app = app_for(root, context)
    with app.app_context():
        client, _ = login(app, context)
        before = client.get("/api/v1/investigation?source=db-" + str(context["dataset_id"]))
        assert before.status_code == 200
        before_count = before.json["scope_count"]
        shutdown, stop_seconds = timed(lambda: stop(root))
        try:
            health_down = client.get("/api/v1/health/database")
            query_down = client.get("/api/v1/investigation?source=db-" + str(context["dataset_id"]))
            demo_down = client.get("/api/v1/investigation?source=demo")
            assert health_down.status_code == query_down.status_code == 503
            assert demo_down.status_code == 200 and demo_down.json["mode"] == "demo"
            assert query_down.json["error"]["code"] == "database_unavailable"
        finally:
            startup, start_seconds = timed(lambda: start(root))
        recovered, recovery_seconds = timed(
            lambda: client.get("/api/v1/investigation?source=db-" + str(context["dataset_id"]))
        )
        assert recovered.status_code == 200 and recovered.json["scope_count"] == before_count
        db.engine.dispose()
    save(
        REPORT / "restart.json",
        {
            "status": "PASS",
            "dedicated_qa_only": True,
            "shutdown": shutdown,
            "startup": startup,
            "stop_seconds": stop_seconds,
            "start_seconds": start_seconds,
            "database_health_during_outage": health_down.status_code,
            "private_query_during_outage": query_down.status_code,
            "demo_during_outage": demo_down.status_code,
            "same_app_connection_pool_recovers": "PASS",
            "recovered_query_seconds_inprocess": recovery_seconds,
            "recovered_scope_count": recovered.json["scope_count"],
            "original_mysql_13306_untouched": True,
        },
    )
    print(
        json.dumps({"restart": "PASS", "stop_seconds": stop_seconds, "start_seconds": start_seconds}),
        flush=True,
    )


def summary(root):
    filter_key = "filter-matrix-final" if (REPORT / "filter-matrix-final.json").exists() else "filter-matrix"
    names = [
        "setup",
        "detect-rule",
        "detect-isolation_forest",
        "verify-before",
        "browser-before",
        "restart",
        "verify-after",
        "browser-after",
        filter_key,
    ]
    evidence = {name: read(REPORT / (name + ".json")) for name in names}
    assert all(r["status"] == "PASS" for r in evidence.values())
    fixtures = {name: read(REPORT / (name + ".json")) for name in ("demo-workspace", "demo-evidence")}
    assert all(
        r["count"] > 0 and r["count"] == len(r["passed"]) and not r["page_errors"] for r in fixtures.values()
    )
    context = read(PRIVATE / "context.json")
    app = app_for(root, context)
    with app.app_context(), Session(db.engine) as session:
        ds = context["dataset_id"]
        counts = {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model).where(model.dataset_id == ds)
            )
            for model in (
                RawLogRecord,
                LogEvent,
                GroundTruthLabel,
                DetectionUnit,
                DetectionPrediction,
                AnomalyOutput,
            )
        }
        counts["unique_flagged_units"] = session.scalar(
            select(func.count(func.distinct(AnomalyOutput.unit_id))).where(AnomalyOutput.dataset_id == ds)
        )
        db.engine.dispose()
    report = {
        "status": "PASS",
        "scope": "Functional real-BGL E2E; not complete University MVP acceptance",
        "release_decision": "HOLD: full dataset CRUD, validated HTTP upload/REST ingestion, Flask-WTF and scope review remain open",
        "workload": {
            "main_dataset_lines": context["line_target"],
            "other_dataset_lines": 1000,
            "authorized_empty_dataset": True,
            "data": "real immutable Loghub BGL prefix",
            "window_seconds": 300,
            "mode": "legacy rule and IF, unchanged; not threshold tuning",
        },
        "counts_main_dataset": counts,
        "checks": {
            name: {"status": result["status"], "report": name + ".json"} for name, result in evidence.items()
        },
        "full_table_restart_checksums": evidence["verify-after"]["all_table_restart_checksums"],
        "csv_after_restart_identical": evidence["verify-after"]["csv_after_restart_identical"],
        "latency": {phase: evidence["browser-" + phase]["latency"] for phase in ("before", "after")},
        "timings_seconds": {
            "import_1k": evidence["setup"]["imports"][0]["seconds"],
            "resume_1k_to_10k": evidence["setup"]["imports"][1]["seconds"],
            "resume_10k_to_100k": evidence["setup"]["imports"][2]["seconds"],
            "rule_worker": evidence["detect-rule"]["worker_seconds"],
            "if_worker": evidence["detect-isolation_forest"]["worker_seconds"],
        },
        "tests": {
            "default": read(REPORT / "unit-tests.json")["commands"]["unit"],
            "mysql": read(REPORT / "mysql-tests.json"),
            "real_browser_groups_per_phase": evidence["browser-before"]["passed_groups"],
            "demo_browser_groups": {name: result["count"] for name, result in fixtures.items()},
            "filter_matrix_cases": len(evidence[filter_key]["cases"]),
        },
        "ui_fixes": [
            "Real dataset range now says Full imported range; DEMO keeps Sample period 60 min",
            "Missing host/service displays Unavailable rather than raw None; layout unchanged",
        ],
        "limitations": [
            "Single-user warm loopback measurements, 12 samples per endpoint per phase; no load-test SLO",
            "No actual upload path: CLI import only",
            "Default IF quality still weak; no new tuning in this E2E",
            "Native macOS execution NOT RUN",
            "External SMTP delivery NOT RUN (mock tests only)",
            "Manual screen reader certification NOT RUN",
            "Official lecturer rubric UNVERIFIED",
            "Manual timed defense rehearsal NOT RUN",
            "Full BGL archive/1M chain not rerun in this task",
        ],
        "original_mysql_status": status(owned_root(".local/mysql-foundation")),
        "publication": "No push, merge or release tag",
        "artifacts": {
            name + ".json": hashlib.sha256((REPORT / (name + ".json")).read_bytes()).hexdigest()
            for name in names
        },
    }
    save(REPORT / "e2e.json", report)
    print(json.dumps({"status": "PASS", "release": "HOLD", "counts": counts}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=".local/university-e2e-mysql")
    parser.add_argument(
        "--stage", required=True, choices=["setup", "detect", "verify", "browser", "restart", "summary"]
    )
    parser.add_argument("--kind", choices=["rule", "isolation_forest"])
    parser.add_argument("--phase", default="before", choices=["before", "after"])
    parser.add_argument("--archive", type=Path, default=(REPO_ROOT / "data/raw/BGL.zip"))
    parser.add_argument("--lines", type=int, default=100000)
    args = parser.parse_args()
    if not 10000 <= args.lines <= 1000000:
        parser.error("Use a bounded 10K..1M line target; this recorded workload is 100K.")
    root = owned_root(args.runtime_root)
    if root.name != "university-e2e-mysql":
        parser.error("Dedicated university-e2e-mysql runtime required.")
    if args.stage == "setup":
        setup(root, args.archive, args.lines)
    elif args.stage == "detect":
        if not args.kind:
            parser.error("--kind required")
        detect(root, args.kind)
    elif args.stage == "verify":
        verify(root, args.phase)
    elif args.stage == "browser":
        browser(root, args.phase)
    elif args.stage == "restart":
        restart(root)
    else:
        summary(root)


if __name__ == "__main__":
    main()
