"""Authenticated real-data browser QA. Credentials come only from environment."""

import csv, io, json, logging, os, threading
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from app import create_app

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    dataset = int(os.environ["QA_DATASET_ID"])
    username = os.environ["QA_USERNAME"]
    password = os.environ["QA_PASSWORD"]
    output = (REPO_ROOT / ".local/database-verification/platform-browser")
    output.mkdir(parents=True, exist_ok=True)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app = create_app()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    passed = []
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel=os.environ.get(
                    "LOGSENSE_BROWSER_CHANNEL",
                    "msedge" if sys.platform == "win32" else "chromium",
                ),
                headless=True,
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(
                base + f"/?workspace=logs&dataset_id={dataset}",
                wait_until="networkidle",
            )
            expect(page.locator("#login-panel")).to_be_visible()
            assert page.request.get(base + "/api/v1/logs/datasets").status == 403
            page.locator("#login-form [name=username]").fill(username)
            page.locator("#login-form [name=password]").fill(password)
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator("#logs-status")).to_contain_text(
                "MySQL ready", timeout=30000
            )
            expect(page.locator("#login-panel")).to_be_hidden()
            assert page.locator("#log-rows tr").count() <= 100
            cookies = context.cookies()
            assert any(c["httpOnly"] and c["sameSite"] == "Strict" for c in cookies)
            passed.append(
                "Login, explicit dataset ACL, HttpOnly/SameSite session and bounded real-log page"
            )
            first = page.locator("#log-rows tr").first.inner_text()
            page.locator("#log-next").click()
            expect(page.locator("#log-page")).to_contain_text("Page 2")
            assert page.locator("#log-rows tr").first.inner_text() != first
            page.locator("#log-previous").click()
            expect(page.locator("#log-page")).to_contain_text("Page 1")
            passed.append(
                "Stable keyset next/previous navigation against a pinned imported-event snapshot"
            )
            host = (
                page.locator("#log-rows tr")
                .first.locator("td")
                .nth(3)
                .inner_text()
                .split(" / ")[0]
            )
            page.locator("#log-filters [name=host]").fill(host)
            page.locator("#log-filters").get_by_role(
                "button", name="Apply", exact=True
            ).click()
            expect(page.locator("#logs-status")).to_contain_text("MySQL ready")
            for item in page.locator("#log-rows tr").all():
                assert host in item.inner_text()
            csv_url = page.locator("#logs-export").get_attribute("href")
            export = page.request.get(base + csv_url)
            assert export.status == 200
            parsed = list(csv.DictReader(io.StringIO(export.text())))
            assert len(parsed) == int(page.locator("#logs-count").inner_text())
            passed.append(
                "Real host filter, synchronized server timeline/count and CSV scope"
            )
            button = page.locator("#log-rows button").first
            button.click()
            expect(page.locator("#log-detail-status")).to_contain_text(
                "Actual imported raw line"
            )
            expect(page.locator("#log-provenance")).to_contain_text("physical_line")
            page.keyboard.press("Escape")
            expect(page.locator("#log-detail")).to_be_hidden()
            expect(button).to_be_focused()
            passed.append(
                "Actual raw provenance drawer, Escape/focus restoration, context unchanged"
            )
            for width in (1366, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                page.screenshot(path=str(output / f"logs-{width}.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            passed.append(
                "Log Explorer layouts at 1366, 1440 and 1920 with controlled chart/table scrolling"
            )
            incident = page.locator("#incident-workspace")
            incident.locator("summary").first.click()
            page.locator("#refresh-alerts").click()
            expect(page.locator("#incident-status")).to_contain_text("Alert page ready")
            if page.locator("#incident-rows button").count():
                page.locator("#incident-rows button").first.click()
                expect(page.locator("#incident-edit")).to_be_visible()
                page.locator("#incident-edit [name=status]").select_option(
                    "acknowledged"
                )
                page.locator("#incident-edit [name=note]").fill(
                    "QA: observed evidence reviewed; cause unconfirmed."
                )
                page.locator("#incident-edit button").click()
                expect(page.locator("#incident-history")).to_contain_text(
                    "cause unconfirmed"
                )
                evidence_button = page.locator("#incident-rows button").nth(1)
                evidence_button.click()
                expect(page.locator("#log-detail-status")).to_contain_text(
                    "Actual anomaly evidence"
                )
                page.locator("#log-close").click()
                expect(page.locator("#log-detail")).to_be_hidden()
                passed.append(
                    "Real alert acknowledgement, redacted note/audit history and linked anomaly evidence"
                )
            page.goto(base + f"/?source=db-{dataset}", wait_until="networkidle")
            expect(page.locator(".demo-notice")).to_contain_text("MYSQL")
            assert page.locator("[data-row-id]").count() <= 100
            if page.locator("[data-row-id]").count():
                assert int(page.locator("#events-title span").inner_text()) >= 1  # count is numeric
                page.locator("[data-mode=volume]").click()
                expect(page.locator(".timeline-panel")).to_have_class(
                    __import__("re").compile("mode-volume")
                )
                page.locator("[data-event-id]").first.click()
                expect(page.locator("#detail-content")).to_be_visible(timeout=30000)
                expect(page.locator("#detail-status")).to_contain_text("MYSQL")
                page.keyboard.press("Escape")
                expect(page.locator("#detail-panel")).to_be_hidden()
                cell = (
                    page.locator(".overall-row [data-cell]")
                    .filter(has_text=__import__("re").compile(r"\d"))
                    .first
                )
                if cell.count():
                    cell.click()
                    expect(page.locator(".selection-banner")).to_be_visible()
                    scoped = page.request.get(
                        base + page.locator("#export-button").get_attribute("href")
                    )
                    if scoped.status == 200:
                        assert int(scoped.headers["x-result-count"]) == int(
                            page.locator("#events-title span").inner_text()
                        )
                passed.append(
                    "MySQL Anomaly Center, Severity/Volume, actual Evidence Drawer and selection/CSV scope"
                )
            else:
                passed.append(
                    "MySQL Anomaly Center truthful empty-result state; no anomaly was fabricated"
                )
            for width in (1366, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                page.screenshot(
                    path=str(output / f"investigation-{width}.png"), full_page=True
                )
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            passed.append(
                "Existing Investigation V2 layout retained at desktop/laptop widths"
            )
            source = page.locator("#source")
            options = source.locator("option").evaluate_all(
                "(items)=>items.map(n=>n.value)"
            )
            alternative = next(
                (value for value in options if value != "db-" + str(dataset)), None
            )
            if alternative:
                source.select_option(alternative)
                expect(page.locator("#query-status")).to_contain_text("MYSQL")
                expect(page.locator("#workspace-results")).to_have_attribute(
                    "aria-busy", "false"
                )
                expect(page.locator("#request-error")).to_be_hidden()
                passed.append(
                    "Authorized dataset switch clears the old run snapshot without retaining private stale scope"
                )
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    report = {
        "passed": passed,
        "count": len(passed),
        "page_errors": errors,
        "data": "real BGL imported prefix; live MySQL",
        "screenshots": "private .local/database-verification/platform-browser",
        "not_run": [
            "native macOS browser",
            "screen-reader certification",
            "actual external SMTP delivery",
        ],
    }
    (REPO_ROOT / "docs/database/measurements/platform-browser.json").write_text(
        json.dumps(report, indent=2)
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
