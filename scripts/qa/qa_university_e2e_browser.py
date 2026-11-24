"""Read-only browser/API E2E against an isolated real-BGL QA database.

Inputs are environment variables, never command-line credentials. This script
does not create accounts, import logs, queue detectors or edit incidents.
Screenshots remain in the private QA_OUTPUT directory. It can be run before and
after an operator-controlled MySQL restart with the same dataset and user.
"""

import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import func, select
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db
from app.models import AnomalyOutput
from app.services.investigation import instant


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def query_url(base, path, values):
    return base + path + "?" + urlencode(values, doseq=True)


def sample_get(request, url, *, count=12):
    samples = []
    payload_bytes = []
    for _ in range(count):
        started = time.perf_counter()
        response = request.get(url, timeout=30000)
        body = response.body()
        assert response.status == 200
        samples.append((time.perf_counter() - started) * 1000)
        payload_bytes.append(len(body))
    return {
        "samples": len(samples),
        "p50_ms": percentile(samples, 0.5),
        "p95_ms": percentile(samples, 0.95),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "payload_bytes_min": min(payload_bytes),
        "payload_bytes_max": max(payload_bytes),
        "measurement": "authenticated loopback HTTP GET through Playwright; body fully received; warm database; not SQL-only latency",
    }


def main():
    dataset = int(os.environ["QA_DATASET_ID"])
    other = int(os.environ["QA_OTHER_DATASET_ID"])
    username = os.environ["QA_USERNAME"]
    password = os.environ["QA_PASSWORD"]
    output = Path(os.environ["QA_OUTPUT"])
    phase = os.environ.get("QA_PHASE", "before")
    if phase not in {"before", "after"} or dataset == other:
        raise ValueError("Use distinct QA datasets and before/after phase.")
    output.mkdir(parents=True, exist_ok=True)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app = create_app()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    report = {
        "phase": phase,
        "dataset_id": dataset,
        "other_dataset_id": other,
        "status": "RUNNING",
        "checks": [],
        "latency": {},
        "page_errors": [],
        "data": "actual imported Loghub BGL; isolated QA MySQL; no synthetic anomaly injection",
        "not_run": ["native macOS browser", "screen-reader certification", "external SMTP delivery"],
    }
    stage = "startup"
    started_all = time.perf_counter()

    def passed(name, **evidence):
        report["checks"].append({"name": name, "status": "PASS", **evidence})

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel=os.environ.get(
                    "LOGSENSE_BROWSER_CHANNEL", "msedge" if sys.platform == "win32" else "chromium"
                ),
                headless=True,
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(type(error).__name__))
            stage = "authentication and dataset authorization"
            page.goto(base + f"/?workspace=logs&dataset_id={dataset}", wait_until="networkidle")
            expect(page.locator("#login-panel")).to_be_visible()
            assert page.request.get(base + "/api/v1/logs/datasets").status == 403
            page.locator("#login-form [name=username]").fill(username)
            page.locator("#login-form [name=password]").fill(password)
            started = time.perf_counter()
            browser_started = page.evaluate("performance.now()")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator("#logs-status")).to_contain_text("MySQL ready", timeout=30000)
            expect(page.locator("#login-panel")).to_be_hidden()
            report["latency"]["login_to_log_render_ms"] = (time.perf_counter() - started) * 1000
            report["latency"]["login_to_log_ready_browser_ms"] = (
                page.evaluate("performance.now()") - browser_started
            )
            granted = page.request.get(base + "/api/v1/logs/datasets").json()["datasets"]
            granted_ids = {d["id"] for d in granted}
            assert dataset in granted_ids and other not in granted_ids
            info = next(d for d in granted if d["id"] == dataset)
            parsed_count = int(page.locator("#logs-count").inner_text())
            assert 0 < page.locator("#log-rows tr").count() <= 100
            cookies = context.cookies()
            assert any(c["httpOnly"] and c["sameSite"] == "Strict" for c in cookies)
            params = {
                "dataset_id": dataset,
                "start_time": info["start_time"],
                "end_time": info["end_time"],
                "limit": 50,
            }
            forbidden = dict(params, dataset_id=other)
            assert page.request.get(query_url(base, "/api/v1/logs", forbidden)).status == 403
            passed(
                "login, explicit dataset ACL and bounded real-log rendering",
                observed_parsed_count=parsed_count,
                max_page_rows=100,
            )

            stage = "keyset pagination"
            first = page.locator("#log-rows tr").first.inner_text()
            page.locator("#log-next").click()
            expect(page.locator("#log-page")).to_contain_text("Page 2")
            assert page.locator("#log-rows tr").first.inner_text() != first
            page.locator("#log-previous").click()
            expect(page.locator("#log-page")).to_contain_text("Page 1")
            assert page.locator("#log-rows tr").first.inner_text() == first
            passed("stable keyset next/previous within the imported snapshot")

            stage = "log filter, timeline, raw provenance and CSV"
            host = page.locator("#log-rows tr").first.locator("td").nth(3).inner_text().split(" / ")[0]
            assert host != "Unavailable"
            page.locator("#log-filters [name=host]").fill(host)
            page.locator("#log-filters").get_by_role("button", name="Apply", exact=True).click()
            expect(page.locator("#log-filters")).to_have_attribute("aria-busy", "false")
            expect(page.locator("#logs-status")).to_contain_text("MySQL ready")
            for row in page.locator("#log-rows tr").all():
                assert host in row.inner_text()
            filtered_count = int(page.locator("#logs-count").inner_text())
            timeline_count = sum(
                int(x) for x in page.locator("#log-bins button").all_text_contents() if x.isdigit()
            )
            assert timeline_count == filtered_count
            export_url = base + page.locator("#logs-export").get_attribute("href")
            exported = page.request.get(export_url)
            assert exported.status == 200
            rows = list(csv.DictReader(io.StringIO(exported.text())))
            assert len(rows) == filtered_count
            assert all(row["host"] == host for row in rows)
            raw_button = page.locator("#log-rows button").first
            prior_url = page.url
            raw_button.click()
            expect(page.locator("#log-detail-status")).to_contain_text("Actual imported raw line")
            expect(page.locator("#log-provenance")).to_contain_text("physical_line")
            expect(page.locator("#log-provenance")).to_contain_text("archive_sha256")
            assert len(page.locator("#log-raw").inner_text()) > 0
            page.keyboard.press("Escape")
            expect(page.locator("#log-detail")).to_be_hidden()
            expect(raw_button).to_be_focused()
            assert page.url == prior_url
            passed(
                "log host filter/table/timeline/CSV scope and raw provenance",
                filtered_count=filtered_count,
                csv_rows=len(rows),
                csv_sha256=hashlib.sha256(exported.body()).hexdigest(),
            )

            stage = "log error handling"
            retained_count = page.locator("#logs-count").inner_text()
            page.route("**/api/v1/logs?*", lambda route: route.abort("failed"))
            page.locator("#log-filters").get_by_role("button", name="Apply", exact=True).click()
            expect(page.locator("#logs-status")).to_contain_text("Query failed")
            assert page.locator("#logs-count").inner_text() == retained_count
            page.unroute("**/api/v1/logs?*")
            page.locator("#log-filters").get_by_role("button", name="Apply", exact=True).click()
            expect(page.locator("#logs-status")).to_contain_text("MySQL ready")
            assert page.request.get(query_url(base, "/api/v1/logs", dict(params, limit=101))).status == 400
            assert (
                page.request.get(query_url(base, "/api/v1/logs", dict(params, start_time="invalid"))).status
                == 400
            )
            passed("network error retains old scope; retry succeeds; invalid API input rejected")

            for width in (1366, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / f"{phase}-logs-{width}.png"), full_page=True)
            passed("Log Explorer at 1366/1440/1920 without document overflow")

            stage = "anomaly timeline and database consistency"
            page.set_viewport_size({"width": 1440, "height": 1000})
            started = time.perf_counter()
            page.goto(base + f"/?source=db-{dataset}", wait_until="networkidle")
            expect(page.locator(".demo-notice")).to_contain_text("MYSQL")
            expect(page.locator("#range option:checked")).to_have_text("Full imported range")
            expect(page.locator("#workspace-results")).to_have_attribute("aria-busy", "false")
            report["latency"]["investigation_navigation_to_ready_ms"] = (time.perf_counter() - started) * 1000
            report["latency"]["investigation_browser_navigation"] = page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0];
                return {ready_observed_ms:performance.now(), response_end_ms:nav.responseEnd,
                    dom_content_loaded_ms:nav.domContentLoadedEventEnd, load_end_ms:nav.loadEventEnd,
                    meaning:'navigation-to-observed-ready includes server response, assets, script execution and QA observation; not isolated paint/render CPU'};
            }""")
            investigation_url = base + f"/api/v1/investigation?source=db-{dataset}"
            investigation = page.request.get(investigation_url).json()
            state = investigation["state"]
            all_count = investigation["scope_count"]
            assert investigation["mode"] == "database" and all_count > 0
            assert investigation["result_count"] == all_count
            assert sum(cell["count"] for cell in investigation["timeline"]["overall"]) == all_count
            with app.app_context():
                expected_count = db.session.scalar(
                    select(func.count())
                    .select_from(AnomalyOutput)
                    .where(
                        AnomalyOutput.dataset_id == dataset,
                        AnomalyOutput.run_id.in_([int(x) for x in state["run_id"]]),
                        AnomalyOutput.anchor_time >= instant(state["start_time"]),
                        AnomalyOutput.anchor_time < instant(state["end_time"]),
                    )
                )
            assert all_count == expected_count
            assert int(page.locator("#events-title span").inner_text()) == all_count
            assert page.locator("[data-row-id]").count() <= 100
            assert all(
                text != "None"
                for text in page.locator("[data-row-id] td:nth-child(4) small").all_text_contents()
            )
            page.locator("[data-mode=volume]").click()
            expect(page.locator(".timeline-panel")).to_have_class(re.compile("mode-volume"))
            assert int(page.locator("#events-title span").inner_text()) == all_count
            page.locator("[data-mode=severity]").click()
            expect(page.locator(".timeline-panel")).not_to_have_class(re.compile("mode-volume"))
            passed(
                "server anomaly aggregation equals persisted outputs; Severity/Volume preserves membership",
                anomaly_outputs=all_count,
                selected_run_ids=state["run_id"],
            )

            stage = "timeline selection and anomaly CSV scope"
            cell = page.locator(".overall-row [data-cell]:not([data-count='0'])").first
            selected_count = int(cell.get_attribute("data-count"))
            cell.click()
            expect(page.locator(".selection-banner")).to_be_visible()
            expect(page.locator("#workspace-results")).to_have_attribute("aria-busy", "false")
            assert int(page.locator("#events-title span").inner_text()) == selected_count
            scoped_query = urlsplit(page.url).query
            selected_api = page.request.get(base + "/api/v1/investigation?" + scoped_query).json()
            assert selected_api["scope_count"] == all_count
            assert selected_api["result_count"] == selected_count
            anomaly_export_url = base + page.locator("#export-button").get_attribute("href")
            anomaly_csv = page.request.get(anomaly_export_url)
            assert anomaly_csv.status == 200
            csv_rows = list(csv.DictReader(io.StringIO(anomaly_csv.text())))
            assert len(csv_rows) == selected_count == int(anomaly_csv.headers["x-result-count"])
            assert len({row["id"] for row in csv_rows}) == len(csv_rows)
            assert all(
                row["id"].startswith("DB-") and row["run_id"] in state["run_id"] and row["version_id"]
                for row in csv_rows
            )
            passed(
                "timeline selection/results/CSV use identical additional scope",
                scope_count=all_count,
                selection_count=selected_count,
                csv_rows=len(csv_rows),
                csv_sha256=hashlib.sha256(anomaly_csv.body()).hexdigest(),
            )

            stage = "actual evidence drawer"
            opener = page.locator(".inspect-button").first
            anomaly_id = opener.get_attribute("data-event-id")
            evidence_url = base + f"/api/v1/anomalies/{anomaly_id}/evidence?" + scoped_query
            evidence_response = page.request.get(evidence_url)
            assert evidence_response.status == 200
            evidence = evidence_response.json()
            assert evidence["mode"] == "database"
            assert evidence["anomaly"]["dataset_id"] == dataset
            assert evidence["anomaly"]["model_run_id"] in [int(x) for x in state["run_id"]]
            assert evidence["raw_event"]["provenance"]["original_log_available"] is True
            assert evidence["raw_event"]["provenance"]["source_line"] > 0
            assert evidence["raw_event"]["page"]["synthetic"] is False
            assert evidence["raw_event"]["page"]["redacted"] is True
            assert evidence["summary"]["root_cause"] is None
            assert evidence["detector_evidence"]["configured_threshold"] is not None
            assert evidence["detector_evidence"]["model_version"]
            opener.click()
            expect(page.locator("#detail-content")).to_be_visible(timeout=30000)
            expect(page.locator("#detail-status")).to_contain_text("MYSQL")
            expect(page.locator("#raw-provenance")).to_contain_text("Source line")
            assert page.locator("#detail-raw").inner_text() == evidence["raw_event"]["page"]["text"]
            selection_url = page.url
            expect(page.locator("#evidence-scope")).to_contain_text("Timeline selection")
            page.keyboard.press("Escape")
            expect(page.locator("#detail-panel")).to_be_hidden()
            expect(page.locator(".selection-banner")).to_be_visible()
            expect(opener).to_be_focused()
            assert page.url == selection_url
            wrong_scope = dict(parse_qsl(scoped_query), source=f"db-{other}")
            wrong_response = page.request.get(
                query_url(base, f"/api/v1/anomalies/{anomaly_id}/evidence", wrong_scope)
            )
            assert wrong_response.status == 403
            passed(
                "actual Evidence Drawer provenance/version/threshold; closing preserves selection/focus; cross-dataset denial",
                anomaly_id=anomaly_id,
                evidence_kind=evidence["detector_evidence"]["kind"],
                source_line=evidence["raw_event"]["provenance"]["source_line"],
            )

            stage = "evidence network error and retry"
            page.route(f"**/api/v1/anomalies/{anomaly_id}/evidence?*", lambda route: route.abort("failed"))
            opener.click()
            expect(page.locator("#retry-detail")).to_be_visible()
            expect(page.locator("#detail-content")).to_be_hidden()
            page.unroute(f"**/api/v1/anomalies/{anomaly_id}/evidence?*")
            page.locator("#retry-detail").click()
            expect(page.locator("#detail-content")).to_be_visible(timeout=30000)
            page.keyboard.press("Escape")
            expect(page.locator(".selection-banner")).to_be_visible()
            passed("evidence error does not expose stale content; retry restores actual evidence")

            for width in (1366, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / f"{phase}-investigation-{width}.png"), full_page=True)
            passed("Investigation at 1366/1440/1920 without document overflow")

            stage = "authenticated latency samples"
            report["latency"]["logs_http"] = sample_get(page.request, query_url(base, "/api/v1/logs", params))
            report["latency"]["timeline_http"] = sample_get(
                page.request, base + f"/api/v1/anomalies/timeline?source=db-{dataset}"
            )
            report["latency"]["investigation_http"] = sample_get(page.request, investigation_url)
            report["latency"]["evidence_http"] = sample_get(page.request, evidence_url)
            report["latency"]["selected_csv_http"] = sample_get(page.request, anomaly_export_url)
            passed("12 warm loopback HTTP latency samples per endpoint; full response body received")

            stage = "separate DEMO mode and anonymous denial"
            demo_response = page.request.get(base + "/api/v1/investigation?source=demo")
            assert demo_response.status == 200
            demo = demo_response.json()
            assert demo["mode"] == "demo"
            assert all(event["id"].startswith("LS-") for event in demo["events"])
            anonymous = browser.new_context()
            assert anonymous.request.get(investigation_url).status == 403
            assert anonymous.request.get(evidence_url).status == 403
            assert anonymous.request.get(base + "/api/v1/investigation?source=demo").status == 200
            anonymous.close()
            page.goto(base + "/?source=demo", wait_until="networkidle")
            expect(page.locator(".demo-notice")).to_contain_text("DEMO")
            expect(page.locator("#range option:checked")).to_have_text("Sample period · 60 min")
            assert page.locator("[data-row-id^='DB-']").count() == 0
            passed(
                "DEMO remains explicitly synthetic; anonymous real-data access denied",
                demo_count=demo["scope_count"],
            )
            assert not report["page_errors"]
            report["status"] = "PASS"
            browser.close()
    except Exception as error:
        report["status"] = "FAIL"
        report["failed_stage"] = stage
        report["failure_type"] = type(error).__name__
        # Detailed messages/tracebacks may contain private raw text. Keep the
        # public report limited to stage/type; inspect owned private screenshots.
        raise
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with app.app_context():
            db.engine.dispose()
        report["wall_seconds"] = time.perf_counter() - started_all
        report["passed_groups"] = len(report["checks"])
        report["screenshots"] = "private QA_OUTPUT; actual raw source content is not committed"
        (output / f"browser-{phase}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps({k: report[k] for k in ("phase", "status", "passed_groups", "wall_seconds")}),
            flush=True,
        )


if __name__ == "__main__":
    main()
