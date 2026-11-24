"""Automated axe-core scan, not accessibility or screen-reader certification."""

import json
import logging
import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

from app import create_app

# Repository root: paths below do not depend on the current working directory.
REPO_ROOT = Path(__file__).resolve().parents[2]


def main():
    axe = REPO_ROOT / ".local/qa-tools/node_modules/axe-core/axe.min.js"
    if not axe.is_file():
        raise RuntimeError("Install the pinned QA-only axe-core package under .local/qa-tools.")
    app = create_app()
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    reports = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel=os.environ.get(
                    "LOGSENSE_BROWSER_CHANNEL",
                    "msedge" if os.name == "nt" else "chromium",
                ),
                headless=True,
            )
            context = browser.new_context(viewport={"width": 1366, "height": 1000})
            login = context.request.post(
                base + "/api/v1/auth/login",
                data={
                    "username": os.environ["QA_USERNAME"],
                    "password": os.environ["QA_PASSWORD"],
                },
            )
            assert login.status == 200
            page = context.new_page()
            for name, path in [
                ("demo", "/"),
                ("logs", "/?workspace=logs&dataset_id=" + os.environ["QA_DATASET_ID"]),
                ("mysql-investigation", "/?source=db-" + os.environ["QA_DATASET_ID"]),
            ]:
                page.goto(base + path, wait_until="networkidle")
                page.add_script_tag(path=str(axe.resolve()))
                result = page.evaluate(
                    "async()=>await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})"
                )
                violations = [
                    {
                        "id": v["id"],
                        "impact": v["impact"],
                        "help": v["help"],
                        "help_url": v["helpUrl"],
                        "targets": [n["target"] for n in v["nodes"]],
                    }
                    for v in result["violations"]
                ]
                reports.append(
                    {
                        "page": name,
                        "violations": violations,
                        "passes": len(result["passes"]),
                        "incomplete_checks": len(result["incomplete"]),
                    }
                )
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
    report = {
        "tool": "axe-core 4.10.3",
        "viewport": 1366,
        "checks": reports,
        "status": "PASS" if not any(r["violations"] for r in reports) else "FAIL",
        "limits": "Automated checks only. Screen reader, manual contrast in every state and native macOS testing NOT RUN.",
    }
    (REPO_ROOT / "docs/database/measurements/accessibility.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
