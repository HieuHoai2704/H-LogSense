"""Browser CRUD QA; mutations affect only a newly registered empty dataset.

DATABASE_URL, FLASK_SECRET_KEY, QA_USERNAME/PASSWORD and QA_OUTPUT are private
environment inputs. QA_DATASET_ID may select a retained dataset; it is never
renamed/deleted. Optional QA_VIEWER_USERNAME/PASSWORD test read-only UI controls.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.extensions import db


def main():
    output = Path(os.environ["QA_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    phase = "dataset-crud-browser"
    destination = output / (phase + ".json")
    if destination.exists():
        raise ValueError("Choose a fresh QA_OUTPUT to retain previous browser evidence.")
    username, password = os.environ["QA_USERNAME"], os.environ["QA_PASSWORD"]
    selected_dataset = os.environ.get("QA_DATASET_ID")
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app = create_app({"LOGIN_REQUIRED": False})
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    started = time.perf_counter()
    result = {
        "status": "RUNNING",
        "checks": [],
        "page_errors": [],
        "not_run": [],
        "data_safety": "Only a newly registered empty dataset is renamed and physically deleted. Existing dataset metadata/logs remain unchanged.",
    }
    stage = "start"
    created_id = None

    def passed(name, **fields):
        result["checks"].append({"name": name, "status": "PASS", **fields})

    def sign_in(page, name, value):
        expect(page.locator("#login-panel")).to_be_visible()
        page.locator("#login-form [name=username]").fill(name)
        page.locator("#login-form [name=password]").fill(value)
        page.get_by_role("button", name="Sign in", exact=True).click()
        expect(page.locator("#login-panel")).to_be_hidden()
        expect(page.locator("#dataset-workspace")).to_be_visible()
        expect(page.locator("#dataset-status")).to_contain_text("Dataset metadata ready", timeout=30000)
        if selected_dataset:
            expect(page.locator("#log-filters [name=dataset_id]")).to_have_value(selected_dataset)
            expect(page.locator("#logs-status")).to_contain_text("MySQL ready", timeout=30000)
            expect(page.locator("#log-filters")).to_have_attribute("aria-busy", "false")

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
            page.on("pageerror", lambda error: result["page_errors"].append(type(error).__name__))
            url = base + "/?workspace=logs"
            if selected_dataset:
                url += "&dataset_id=" + selected_dataset
            page.goto(url, wait_until="networkidle")
            expect(page.locator("#dataset-workspace")).to_be_hidden()
            assert page.request.get(base + "/api/v1/datasets").status == 403
            stage = "authenticated dataset panel"
            sign_in(page, username, password)
            auth = page.request.get(base + "/api/v1/auth/me").json()
            assert auth["user"]["role"] == "admin", "Admin QA account required for the complete CRUD path"
            panel = page.locator("#dataset-workspace")
            panel.locator("summary").first.click()
            expect(page.locator("#dataset-create-panel")).to_be_visible()
            page.locator("#dataset-create-panel summary").click()
            original_scope = page.locator("#log-filters").evaluate(
                "(form)=>Object.fromEntries(new FormData(form))"
            )
            original_url = page.url
            passed("anonymous denial; signed-in admin sees inline granted metadata without page navigation")

            stage = "register empty dataset and safe name rendering"
            suffix = uuid4().hex[:12]
            key = "browser-" + suffix
            name = '<img src=x onerror="window.datasetXss=1"> ' + suffix
            page.evaluate("window.datasetXss=0")
            create = page.locator("#dataset-create")
            create.locator("[name=name]").fill(name)
            create.locator("[name=dataset_key]").fill(key)
            create.locator("[name=data_mode]").select_option("unverified")
            with page.expect_response(
                lambda response: (
                    response.url == base + "/forms/datasets" and response.request.method == "POST"
                )
            ) as response_info:
                create.get_by_role("button", name="Register dataset", exact=True).click()
            response = response_info.value
            assert response.status == 201
            created = response.json()["dataset"]
            created_id = created["id"]
            row = page.locator(f'#dataset-rows tr[data-dataset-id="{created_id}"]')
            expect(row).to_be_visible()
            expect(row.locator("td").first.locator("strong")).to_have_text(name)
            assert page.locator("#dataset-rows img").count() == 0 and page.evaluate("window.datasetXss") == 0
            if original_scope.get("dataset_id"):
                expect(page.locator("#log-filters [name=dataset_id]")).to_have_value(
                    original_scope["dataset_id"]
                )
                current = page.locator("#log-filters").evaluate(
                    "(form)=>Object.fromEntries(new FormData(form))"
                )
                if current != original_scope or page.url != original_url:
                    result["scope_mismatch"] = {
                        "before": original_scope,
                        "after": current,
                        "before_url": original_url,
                        "after_url": page.url,
                    }
                assert current == original_scope and page.url == original_url
            assert page.request.get(base + f"/api/v1/datasets/{created_id}").json()["dataset"]["name"] == name
            passed(
                "register/creator grant/detail and safe text rendering; existing Explorer scope preserved",
                new_empty_dataset_id=created_id,
            )

            stage = "duplicate validation"
            create.locator("[name=name]").fill("Duplicate attempt")
            create.locator("[name=dataset_key]").fill(key)
            with page.expect_response(
                lambda response: (
                    response.url == base + "/forms/datasets" and response.request.method == "POST"
                )
            ) as response_info:
                create.get_by_role("button", name="Register dataset", exact=True).click()
            assert response_info.value.status == 409
            expect(row).to_be_visible()
            passed("duplicate key receives 409 without removing current metadata or creating another dataset")

            stage = "rename existing empty metadata"
            row.locator("button").filter(has_text="Rename").click()
            expect(page.locator("#dataset-edit")).to_be_visible()
            renamed = "Renamed browser dataset " + suffix
            page.locator("#dataset-edit [name=name]").fill(renamed)
            with page.expect_response(
                lambda response: (
                    response.url == base + f"/forms/datasets/{created_id}/rename"
                    and response.request.method == "POST"
                )
            ) as response_info:
                page.get_by_role("button", name="Save dataset name", exact=True).click()
            assert response_info.value.status == 200
            expect(row.locator("td").first.locator("strong")).to_have_text(renamed)
            expect(page.locator("#dataset-edit")).to_be_hidden()
            saved = page.request.get(base + f"/api/v1/datasets/{created_id}").json()["dataset"]
            assert saved["name"] == renamed and saved["dataset_key"] == key and saved["input_revision"] == 0
            passed("rename updates only display metadata through the existing workspace")

            stage = "retained dataset protected against deletion"
            if selected_dataset:
                protected = page.request.get(base + f"/api/v1/datasets/{selected_dataset}").json()["dataset"]
                if protected["input_revision"] > 0:
                    denied = page.request.delete(
                        base + f"/api/v1/datasets/{selected_dataset}",
                        headers={"X-CSRF-Token": auth["csrf_token"]},
                    )
                    assert denied.status == 409
                    assert (
                        page.request.get(base + f"/api/v1/datasets/{selected_dataset}").json()["dataset"]
                        == protected
                    )
                    passed("populated retained dataset rejects delete with409; metadata unchanged")
                else:
                    result["not_run"].append(
                        "Retained dataset has no positive import revision; no deletion request attempted"
                    )
            else:
                result["not_run"].append(
                    "Populated dataset protection: QA_DATASET_ID not supplied; covered by API/integration tests separately"
                )

            stage = "explicit deletion confirmation"
            row.locator("button").filter(has_text="Delete").click()
            expect(page.locator("#dataset-delete-confirm")).to_be_visible()
            expect(page.locator("#dataset-delete-message")).to_contain_text(renamed)
            page.get_by_role("button", name="Cancel deletion", exact=True).click()
            expect(page.locator("#dataset-delete-confirm")).to_be_hidden()
            assert page.request.get(base + f"/api/v1/datasets/{created_id}").status == 200
            row.locator("button").filter(has_text="Delete").click()
            with page.expect_response(
                lambda response: (
                    response.url == base + f"/forms/datasets/{created_id}/delete"
                    and response.request.method == "POST"
                )
            ) as response_info:
                page.get_by_role("button", name="Delete empty dataset", exact=True).click()
            assert response_info.value.status == 204
            expect(row).to_have_count(0)
            assert page.request.get(base + f"/api/v1/datasets/{created_id}").status == 403
            if original_scope.get("dataset_id"):
                expect(page.locator("#log-filters [name=dataset_id]")).to_have_value(
                    original_scope["dataset_id"]
                )
            passed(
                "cancel preserves dataset; explicit confirmation physically deletes only new empty metadata"
            )

            stage = "network error and recovery"
            page.route("**/api/v1/datasets?*", lambda route: route.abort("failed"))
            page.get_by_role("button", name="Refresh datasets", exact=True).click()
            expect(page.locator("#dataset-status")).to_contain_text("Dataset query failed")
            page.unroute("**/api/v1/datasets?*")
            page.get_by_role("button", name="Refresh datasets", exact=True).click()
            expect(page.locator("#dataset-status")).to_contain_text("Dataset metadata ready")
            passed("metadata request error is visible; retry restores granted metadata")

            for width in (1366, 1440, 1920):
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.screenshot(path=str(output / f"dataset-crud-{width}.png"), full_page=True)
            passed("inline panel retains laptop/desktop layout at1366/1440/1920")

            stage = "signed form CSRF enforcement"
            auth = page.request.get(base + "/api/v1/auth/me").json()
            rejected = page.request.post(
                base + "/forms/datasets",
                form={
                    "name": "Missing form token",
                    "dataset_key": "missing-csrf-" + suffix,
                    "data_mode": "unverified",
                },
                headers={"X-CSRF-Token": auth["csrf_token"]},
            )
            assert rejected.status == 400 and "csrf_token" in rejected.json()["error"]["fields"]
            token = page.request.get(base + "/api/v1/forms/csrf").json()["csrf_token"]
            rejected = page.request.post(
                base + "/forms/datasets",
                form={
                    "name": "Missing role token",
                    "dataset_key": "missing-role-" + suffix,
                    "data_mode": "unverified",
                    "csrf_token": token,
                },
            )
            assert rejected.status == 403
            passed("live forms require both Flask-WTF signed CSRF and the existing role/header CSRF guard")

            stage = "real file upload and queued ingestion worker"
            supplied_file = os.environ.get("QA_UPLOAD_FILE")
            if supplied_file:
                file_path = Path(supplied_file)
                assert file_path.is_file() and 0 < file_path.stat().st_size <= 16 * 1024 * 1024
                create.locator("[name=name]").fill("Browser upload target " + suffix)
                create.locator("[name=dataset_key]").fill("upload-" + suffix)
                create.locator("[name=data_mode]").select_option("real")
                with page.expect_response(
                    lambda response: (
                        response.url == base + "/forms/datasets" and response.request.method == "POST"
                    )
                ) as info:
                    create.get_by_role("button", name="Register dataset", exact=True).click()
                assert info.value.status == 201
                upload_dataset = info.value.json()["dataset"]["id"]
                upload_panel = page.locator("#upload-workspace")
                expect(upload_panel).to_be_visible()
                upload_panel.locator("summary").first.click()
                upload_form = page.locator("#upload-form")
                upload_form.locator("[name=dataset_id]").select_option(str(upload_dataset))
                upload_form.locator("[name=file]").set_input_files(str(file_path.resolve()))
                with page.expect_response(
                    lambda response: (
                        response.url == base + "/api/v1/uploads" and response.request.method == "POST"
                    )
                ) as info:
                    upload_form.get_by_role("button", name="Queue BGL import", exact=True).click()
                assert info.value.status == 202
                queued = info.value.json()
                assert queued["state"] == "queued"
                expect(page.locator("#upload-status")).to_contain_text("queued")
                worker_started = time.perf_counter()
                with (output / "ingestion-worker.log").open("w", encoding="utf-8") as worker_log:
                    worker = subprocess.run(
                        [sys.executable, "-m", "scripts.run.ingestion_worker", "--once"],
                        stdout=worker_log,
                        stderr=subprocess.STDOUT,
                        timeout=120,
                    )
                assert worker.returncode == 0
                page.get_by_role("button", name="Refresh import status", exact=True).click()
                expect(page.locator("#upload-status")).to_contain_text("Import completed", timeout=30000)
                imported = page.request.get(base + queued["status_url"]).json()
                assert imported["state"] == "completed" and imported["parsed_events"] > 0
                assert (
                    imported["provenance"]["original_sha256"]
                    == hashlib.sha256(file_path.read_bytes()).hexdigest()
                )
                page.locator("#log-filters [name=dataset_id]").select_option(str(upload_dataset))
                page.locator("#log-filters").get_by_role("button", name="Apply", exact=True).click()
                expect(page.locator("#logs-status")).to_contain_text("MySQL ready", timeout=30000)
                expect(page.locator("#logs-count")).to_have_text(str(imported["parsed_events"]))
                page.locator("#log-rows button").first.click()
                expect(page.locator("#log-detail-status")).to_contain_text("Actual imported raw line")
                expect(page.locator("#log-provenance")).to_contain_text("original_sha256")
                page.keyboard.press("Escape")
                assert (
                    page.request.delete(
                        base + f"/api/v1/datasets/{upload_dataset}",
                        headers={"X-CSRF-Token": auth["csrf_token"]},
                    ).status
                    == 409
                )
                passed(
                    "actual signed upload→queued worker→MySQL→Explorer/raw provenance; imported data protected",
                    uploaded_dataset_id=upload_dataset,
                    parsed_events=imported["parsed_events"],
                    malformed_rows=imported["malformed_rows"],
                    worker_to_verified_explorer_seconds=time.perf_counter() - worker_started,
                    timing_note="Includes worker execution, status/Explorer/raw evidence and protected-delete checks; excludes upload staging.",
                    original_sha256=imported["provenance"]["original_sha256"],
                )
            else:
                result["not_run"].append("Browser upload/worker: QA_UPLOAD_FILE not supplied")

            stage = "logout and viewer permissions"
            page.locator("#logs-logout").click()
            expect(page.locator("#login-panel")).to_be_visible()
            expect(page.locator("#dataset-workspace")).to_be_hidden()
            viewer_name, viewer_password = (
                os.environ.get("QA_VIEWER_USERNAME"),
                os.environ.get("QA_VIEWER_PASSWORD"),
            )
            if viewer_name and viewer_password:
                # A different account starts from an explicitly authorized URL,
                # not the upload target belonging only to the admin session.
                page.goto(url, wait_until="networkidle")
                sign_in(page, viewer_name, viewer_password)
                page.locator("#dataset-workspace summary").first.click()
                expect(page.locator("#dataset-create-panel")).to_be_hidden()
                assert page.locator("#dataset-rows button").count() == 0
                passed("logout hides private metadata; viewer receives no mutation controls")
            else:
                passed("logout hides private dataset metadata")
                result["not_run"].append(
                    "Viewer browser login: optional viewer credentials absent; backend roles tested separately"
                )
            assert not result["page_errors"]
            result["status"] = "PASS"
            browser.close()
    except Exception as error:
        result.update(
            status="FAIL",
            failed_stage=stage,
            failure_type=type(error).__name__,
            created_empty_dataset_id=created_id,
            note="On failure, retained new empty metadata may need a later authorized cleanup. No existing data is deleted.",
        )
        raise
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with app.app_context():
            db.engine.dispose()
        result["wall_seconds"] = time.perf_counter() - started
        result["passed_groups"] = len(result["checks"])
        result["screenshots"] = "Private QA_OUTPUT only; no passwords/raw research logs committed."
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps({key: result[key] for key in ("status", "passed_groups", "wall_seconds")}), flush=True
        )


if __name__ == "__main__":
    main()
