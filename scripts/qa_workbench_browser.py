"""Run Windows/Edge Workbench E2E against an isolated loopback launcher and project."""

import logging
import os
import re
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.parse import parse_qs, urlsplit

import psutil
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.workbench.api import mount


TRAIN_SCRIPT = """\
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import time

start = datetime.now(timezone.utc).replace(microsecond=0)
def timestamp(seconds):
    return (start + timedelta(seconds=seconds)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

print(f'{timestamp(0)} INFO epoch=1 loss=0.8', flush=True)
print(f'{timestamp(1)} INFO checkpoint saved <b>model.pt</b>', flush=True)
print(f'{timestamp(2)} INFO epoch=3', flush=True)
print(f'{timestamp(3)} INFO epoch=3', flush=True)
local_checkpoint = (start + timedelta(seconds=1)).astimezone(timezone(timedelta(hours=7)))
Path(os.environ['H_LOGSEN_METRICS_CSV']).write_text(
    'epoch,train_loss,val_loss,timestamp\\n1,0.8,0.9,\\n'
    f'2,0.5,0.6,{local_checkpoint.isoformat()}\\n3,0.4,,\\n',
    encoding='utf-8',
)
directory = Path(os.environ['H_LOGSEN_ARTIFACTS_DIR']) / 'checkpoints'
directory.mkdir()
(directory / 'model.pt').write_bytes(b'result')
time.sleep(3.5)
print(f'{timestamp(4)} INFO training finished', flush=True)
"""


class WorkbenchBrowserTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.project = root / "project"
        self.project.mkdir()
        (self.project / "train.py").write_text(TRAIN_SCRIPT, encoding="utf-8")
        app = create_app({"TESTING": True})
        token = secrets.token_urlsafe()
        self.local = mount(app, token, root / "state")
        self.addCleanup(self.local["terminals"].shutdown)
        server = make_server("127.0.0.1", 0, app, threaded=True)
        self.local["port"] = server.server_port
        self.addCleanup(server.server_close)
        Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        channel = os.environ.get("LOGSENSE_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
        browser = playwright.chromium.launch(channel=channel or None, headless=True)
        self.addCleanup(browser.close)
        self.page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.page.goto(f"http://127.0.0.1:{server.server_port}/#workbench={token}")

    def open_project(self):
        folder_button = self.page.locator("#open-project-file")
        try:
            expect(folder_button).to_be_enabled()
        except AssertionError as error:
            status = self.page.locator("#local-status").text_content()
            raise AssertionError(f"Folder picker did not initialize: {status!r}, {self.page_errors!r}") from error
        folder_button.click()
        self.page.locator("#local-root").fill(str(self.project))
        self.page.locator("#local-project-form button[type=submit]").click()
        expect(self.page.locator("#local-active-root")).to_have_text(str(self.project))
        expect(self.page.locator('#local-tree button[data-path="train.py"]')).to_be_visible()

    def test_real_training_chart_click_keyboard_checkpoint_and_pinned_context(self):
        self.open_project()
        page = self.page
        page.locator('#local-tree button[data-path="train.py"]').click()
        expect(page.locator("#monitor")).to_be_visible()
        page.locator("#local-open-editor").click()
        with page.expect_response(lambda response: response.url.endswith("/runs") and response.request.method == "POST") as created:
            page.locator("#local-run-file").click()
        run_id = created.value.json()["id"]
        detail = page.locator("#run-detail")
        expect(detail).to_contain_text(run_id)
        expect(detail).to_contain_text("1 điểm loss")
        loss = page.locator("#run-loss svg")
        expect(loss).to_be_visible()
        expect(page.locator("#run-machine svg")).to_be_visible()
        point = loss.locator("circle").first
        point.click()
        expect(page.locator("#run-log-context mark")).to_contain_text("epoch=1")
        slider = page.locator("#run-time")
        before = page.locator("#run-time-value").text_content()
        slider.press("End")
        self.assertNotEqual(page.locator("#run-time-value").text_content(), before)
        marker = page.locator("#run-checkpoints button")
        expected_time = marker.get_attribute("title").split()[0]
        marker.click()
        expect(page.locator("#run-time-value")).to_have_text(expected_time)
        expect(page.locator("#run-loss")).to_contain_text("Train loss 0.5")
        expect(page.locator("#run-log-context mark")).to_contain_text("<b>model.pt</b>")
        expect(page.locator("#run-log-context b")).to_have_count(0)
        expect(page.locator("#run-detail-meta")).to_contain_text("completed", timeout=12000)
        expect(page.locator("#run-time-value")).to_have_text(expected_time)
        expect(page.locator("#run-log-context mark")).to_contain_text("checkpoint saved")
        page.locator("#run-profile summary").click()
        expect(page.locator("#run-profile-metadata")).to_contain_text("Môi trường Python")
        expect(page.locator("#run-profile-metadata")).to_contain_text("SHA-256 mã chạy")
        expect(page.locator("#run-profile-files")).to_contain_text("checkpoints/model.pt")
        expect(page.locator("#run-profile-files")).to_contain_text("machine.jsonl")
        page.locator("#run-profile-refresh").click()
        expect(page.locator("#run-profile-status")).to_have_text("Đã đọc hồ sơ.")
        expect(page.locator("#run-follow")).to_have_attribute("aria-pressed", "false")
        page.locator("#run-follow").click()
        expect(page.locator("#run-follow")).to_have_attribute("aria-pressed", "true")
        self.assertEqual(self.page_errors, [])

    def test_attach_existing_python_process_investigates_its_files_and_pid(self):
        (self.project / "external.log").write_text("2026-11-08T02:00:00Z INFO external training\n", encoding="utf-8")
        (self.project / "external.csv").write_text(
            "epoch,train_loss,timestamp\n1,0.6,2026-11-08T02:00:00Z\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(40)"], cwd=self.project)
        try:
            self.open_project()
            page = self.page
            page.locator("#open-attach-run").click()
            form = page.locator("#attach-run-form")
            form.locator('[name="pid"]').fill(str(process.pid))
            form.locator('[name="log"]').fill("external.log")
            form.locator('[name="metrics"]').fill("external.csv")
            form.locator('button[type="submit"]').click()
            expect(page.locator("#attach-run-dialog")).to_be_hidden()
            expect(page.locator("#local-run-status")).to_contain_text(str(process.pid))
            expect(page.locator("#terminal-body")).to_contain_text("external training")
            expect(page.locator("#training-chart svg")).to_be_visible()
            expect(page.locator("#local-stop-run")).to_be_hidden()
            page.locator('[data-panel="machine"]').click()
            page.locator('#machine-chart [data-resource="ram"]').click()
            expect(page.locator("#machine-source")).to_contain_text("PID " + str(process.pid))
            expect(page.locator("#machine-capacity")).to_contain_text("GiB")
            self.assertIsNone(process.poll())
            process.terminate()
            process.wait(timeout=10)
            expect(page.locator("#local-run-status")).to_contain_text("ended")
            expect(page.locator("#terminal-body")).to_contain_text("external training")
            self.assertEqual(self.page_errors, [])
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)

    def test_analysis_profiles_csv_jsonl_and_parquet(self):
        self.open_project()
        import pyarrow as arrow
        import pyarrow.parquet as parquet

        (self.project / "data.csv").write_bytes(b"epoch,loss\n1,0.2\n1,0.2\n2,\n")
        (self.project / "data.jsonl").write_bytes(b'{"a":1,"b":"<b>literal</b>"}\n{"a":2}\nmalformed\n')
        parquet.write_table(arrow.table({"epoch": [1, 2], "loss": [0.2, None]}), self.project / "data.parquet")
        page = self.page
        page.get_by_role("link", name="Phân tích", exact=True).click()
        expect(page.locator("#local-active-root")).to_have_text(str(self.project))
        page.locator("#local-search-input").fill("data.csv")
        page.locator("#local-search-results button").click()
        expect(page.locator('#external-preview [name="path"]')).to_have_value("data.csv")
        expect(page.locator('#external-preview [name="format"]')).to_have_value("csv")
        form = page.locator("#external-preview form")
        status = page.locator("#external-status")
        sample = page.locator("#external-sample")
        for kind, expected in (("csv", "1 trùng"), ("jsonl", "1 lỗi"), ("parquet", "2/2")):
            form.locator('[name="path"]').fill("data." + kind)
            form.locator('[name="format"]').select_option(kind)
            form.get_by_role("button", name="Phân tích tệp").click()
            expect(status).to_contain_text(expected)
            expect(sample.locator("tbody tr")).to_have_count(3 if kind == "csv" else 2)
            expect(page.locator("#external-distribution progress").first).to_be_visible()
            if kind == "jsonl":
                expect(sample).to_contain_text("<b>literal</b>")
                expect(sample.locator("b")).to_have_count(0)
        self.assertEqual(self.page_errors, [])

    def test_black_glass_palette_reaches_code_terminal_and_analysis(self):
        (self.project / "glass.log").write_text("2026-11-08T10:00:00Z WARN qa-glass\n", encoding="utf-8")
        self.open_project()
        page = self.page
        page.get_by_role("link", name="Thiết lập", exact=True).click()
        choice = page.get_by_role("radio", name=re.compile("Kính đen"))
        choice.check()
        expect(page.locator("html")).to_have_attribute("data-theme", "glass")
        page.reload()
        expect(choice).to_be_checked()
        page.get_by_role("link", name="Dự án", exact=True).click()
        page.locator('#local-tree button[data-path="glass.log"]').click()
        expect(page.locator("#severity-chart .heatmap button").first).to_have_css("font-size", "12px")
        expect(page.locator("#severity-chart .heatmap button").first).to_have_css("font-weight", "650")
        page.locator('[data-terminal-action="log"]').click()
        expect(page.locator("#terminal-body")).to_be_visible()
        expect(page.locator("#terminal-body")).to_contain_text("qa-glass")
        expect(page.locator("#terminal-body")).to_have_css("font-size", "12px")
        page.get_by_role("link", name="Code", exact=True).click()
        expect(page.locator(".code-pane").first).to_have_css("background-color", "rgb(8, 10, 11)")
        page.locator('[data-terminal-action="new"]').click()
        shell = page.locator("#terminal-panes .live-shell").last
        expect(shell).to_have_css("background-color", "rgb(6, 8, 9)")
        expect(shell.locator(".xterm-helper-textarea")).to_be_focused()
        page.get_by_role("link", name="Phân tích", exact=True).click()
        expect(page.locator("html")).to_have_attribute("data-theme", "glass")
        expect(page.locator("html")).to_have_css("background-color", "rgb(8, 10, 11)")
        self.assertEqual(self.page_errors, [])

    def test_glass_frame_transparency_persists_and_resets(self):
        page = self.page
        root = page.locator("html")
        (self.project / "glass.log").write_text(
            "2026-11-08T10:00:00Z WARN qa-glass\n", encoding="utf-8"
        )
        self.open_project()
        page.locator('#local-tree button[data-path="glass.log"]').click()
        neutral_bin = page.locator(".heatmap button:not([data-tone])").first
        warning_bin = page.locator('.heatmap button[data-tone="WARN"]').first
        expect(neutral_bin).to_be_visible()
        expect(warning_bin).to_be_visible()
        page.get_by_role("link", name="Thiết lập", exact=True).click()
        page.get_by_role("radio", name=re.compile("Kính đen")).check()
        slider = page.locator("#glass-transparency")
        expect(slider).to_be_hidden()
        expect(page.locator("#glass-unavailable")).to_be_visible()

        # The browser has no desktop bridge. Simulate a successful native backdrop.
        root.evaluate("(node) => node.setAttribute('data-native-glass', '')")
        expect(slider).to_have_value("39")
        slider.press("Home")
        expect(page.locator("#glass-transparency-value")).to_have_text("0%")
        expect(root).to_have_css("background-color", "rgb(8, 10, 11)")

        page.reload()
        root.evaluate("(node) => node.setAttribute('data-native-glass', '')")
        expect(slider).to_have_value("0")
        slider.press("End")
        expect(page.locator("#glass-transparency-value")).to_have_text("100%")
        expect(root).to_have_css("background-color", "rgba(8, 10, 11, 0)")
        expect(page.locator(".xterm-scrollable-element").first).to_have_css("background-color", "rgba(0, 0, 0, 0)")
        expect(page.locator(".monitor-visuals .chart-panel").first).to_have_css("background-color", "rgba(0, 0, 0, 0)")
        expect(neutral_bin).to_have_css("background-color", "rgba(8, 10, 11, 0)")
        expect(warning_bin).not_to_have_css("background-color", "rgba(0, 0, 0, 0)")
        for selector in ("#terminal-panes .live-shell", ".xterm-viewport", ".code-pane", ".editor-panel"):
            background = page.locator(selector).first.evaluate(
                "(node) => getComputedStyle(node).backgroundColor"
            )
            self.assertEqual(background, "rgba(0, 0, 0, 0)", selector)
        expect(page.locator("#terminal-panes .live-shell")).to_have_css("opacity", "1")

        page.reload()
        root.evaluate("(node) => node.setAttribute('data-native-glass', '')")
        expect(slider).to_have_value("100")
        page.locator("#glass-reset").click()
        expect(slider).to_have_value("39")
        expect(root).to_have_css("background-color", "rgba(8, 10, 11, 0.61)")
        self.assertEqual(self.page_errors, [])

    def test_glass_surfaces_and_selection_across_workspaces(self):
        (self.project / "glass.log").write_text("2026-11-08T10:00:00Z WARN qa-glass\n", encoding="utf-8")
        self.open_project()
        page = self.page
        root = page.locator("html")
        page.locator('#local-tree button[data-path="glass.log"]').click()
        page.get_by_role("link", name="Thiết lập", exact=True).click()
        page.get_by_role("radio", name=re.compile("Kính đen")).check()
        root.evaluate("(node) => node.setAttribute('data-native-glass', '')")
        page.locator("#glass-transparency").press("End")
        clear_tint = "rgba(8, 10, 11, 0)"
        expect(page.locator("#settings-nav button").first).to_have_css("background-color", clear_tint)
        page.get_by_role("link", name="Dự án", exact=True).click()
        expect(page.locator(".monitor-visuals .charts")).to_have_css("background-color", "rgba(0, 0, 0, 0)")
        for selector in (".project-search input", "#local-runs", "#bucket", '[data-dock-tab="terminal"]'):
            expect(page.locator(selector).first).to_have_css("background-color", clear_tint)
        cell = page.locator(".heatmap button:not([data-tone])").first
        cell.click()
        expect(cell).to_have_attribute("aria-pressed", "true")
        expect(cell).to_have_css("outline-color", "rgba(0, 0, 0, 0.76)")

        page.get_by_role("link", name="Phân tích", exact=True).click()
        root.evaluate("(node) => node.setAttribute('data-native-glass', '')")
        for selector in ("#external-preview", ".demo-notice", "#search", ".timeline-panel",
                         ".investigation", ".heat.priority-0.coverage-complete"):
            expect(page.locator(selector).first).to_have_css("background-color", clear_tint)
        expect(page.locator(".heat.priority-4").first).to_have_css("background-color", "rgb(174, 36, 66)")
        self.assertEqual(self.page_errors, [])

    def test_colored_glass_palettes_persist_across_workspaces(self):
        page = self.page
        root = page.locator("html")
        settings = page.get_by_role("link", name="Thiết lập", exact=True)
        for theme, label, background, terminal in (
            ("glass-forest", "Kính xanh lá đậm", "rgb(10, 26, 20)", "rgb(9, 23, 17)"),
            ("glass-mint", "Kính xanh lá nhạt", "rgb(220, 241, 230)", "rgb(229, 243, 235)"),
            ("glass-blue", "Kính xanh dương", "rgb(5, 16, 25)", "rgb(5, 14, 23)"),
        ):
            with self.subTest(theme=theme):
                settings.click()
                option = page.get_by_role("radio", name=re.compile(label))
                option.check()
                expect(root).to_have_attribute("data-theme", theme)
                page.reload()
                expect(option).to_be_checked()
                page.get_by_role("link", name="Dự án", exact=True).click()
                expect(page.locator(".project-shell")).to_have_css("background-color", background)
                expect(page.locator("#terminal-panes .live-shell")).to_have_css("background-color", terminal)
                page.get_by_role("link", name="Code", exact=True).click()
                expect(root).to_have_attribute("data-theme", theme)
                page.get_by_role("link", name="Phân tích", exact=True).click()
                expect(root).to_have_attribute("data-theme", theme)
                expect(root).to_have_css("background-color", background)
        self.assertEqual(self.page_errors, [])

    def test_preferences_translate_workbench_and_share_analysis_palette(self):
        page = self.page
        page.get_by_role("link", name="Thiết lập", exact=True).click()
        page.locator('input[name="appearance"][value="paper"]').check()
        project_color = page.locator(".project-shell").evaluate("(el) => getComputedStyle(el).backgroundColor")
        page.locator('[data-setting="language"]').click()
        page.locator("#interface-language").select_option("en")
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.locator("#setting-language")).to_be_visible()
        expect(page.get_by_role("link", name="Settings", exact=True)).to_be_visible()
        page.get_by_role("link", name="Analysis", exact=True).click()
        expect(page.locator("html")).to_have_attribute("data-theme", "paper")
        expect(page.get_by_role("heading", name="Investigation", exact=True)).to_be_visible()
        analysis_color = page.locator("html").evaluate("(el) => getComputedStyle(el).backgroundColor")
        self.assertEqual(project_color, analysis_color)
        page.get_by_role("link", name="Project", exact=True).click()
        expect(page.get_by_role("heading", name="Project workspace")).to_be_visible()
        expect(page.locator("#open-project-file")).to_be_visible()
        self.assertEqual(self.page_errors, [])

    def test_monitor_layout_fills_window_and_gives_space_to_live_data(self):
        page = self.page
        activity = page.locator("#activity-state")
        expect(activity).to_have_text("Chờ nguồn log")
        expect(page.locator("#training-state")).to_have_text("Sẵn sàng")
        for width, height in ((1920, 1010), (1440, 880), (1024, 620)):
            page.set_viewport_size({"width": width, "height": height})
            layout = page.locator("#monitor").evaluate("""el => {
              const [top, charts, terminal] = [...el.children].map(node => node.getBoundingClientRect());
              return {height: el.clientHeight, top:top.height, charts:charts.height, terminal:terminal.height,
                      bottom:terminal.bottom, paneBottom:el.querySelector('#terminal-panes').getBoundingClientRect().bottom};
            }""")
            self.assertLess(layout["top"], 105)
            self.assertAlmostEqual(layout["charts"], layout["terminal"], delta=1)
            self.assertAlmostEqual(layout["top"] + layout["charts"] + layout["terminal"], layout["height"], delta=1)
            self.assertAlmostEqual(layout["bottom"], height, delta=2)
            self.assertAlmostEqual(layout["paneBottom"], height, delta=2)
        page.locator('[data-terminal-action="collapse"]').click()
        expect(page.locator("#terminal-panes")).to_be_hidden()
        page.locator('[data-terminal-action="collapse"]').click()
        expect(page.locator("#terminal-panes")).to_be_visible()
        self.open_project()
        log = self.project / "train.log"
        log.write_bytes(b"INFO ready\n")
        (self.project / "metrics.csv").write_bytes(b"epoch,train_loss,val_loss\n1,0.4,0.5\n2,0.2,0.3\n")
        expect(activity).to_have_text("Chưa ghi nhận cảnh báo hoặc lỗi", timeout=10000)
        expect(page.locator("#training-state")).to_have_text("Có dữ liệu", timeout=10000)
        expect(page.locator("#training-chart svg")).to_be_visible()
        self.assertGreater(page.locator("#severity-chart .heatmap").bounding_box()["height"], 80)
        self.assertGreater(page.locator("#training-chart svg").bounding_box()["height"], 80)
        with log.open("ab") as stream:
            stream.write(b"ERROR newly appended\n")
        expect(activity).to_have_text("Có cảnh báo hoặc lỗi", timeout=7000)
        expect(page.locator("#terminal-body")).to_contain_text("ERROR newly appended")
        self.assertEqual(self.page_errors, [])

    def test_folder_switch_identifies_new_root_and_explains_failed_or_canceled_selection(self):
        self.open_project()
        page = self.page
        new_root = self.project / self.project.name
        new_root.mkdir()
        (new_root / "unique.log").write_text("INFO new folder", encoding="utf-8")
        feedback = page.locator("#local-folder-feedback")
        active_root = page.locator("#local-active-root")

        def choose(path):
            if page.locator("#local-project-form").is_hidden():
                page.locator("#open-project-file").click()
            page.locator("#local-root").fill(str(path))
            page.locator("#local-project-form button[type=submit]").click()

        choose(new_root)
        expect(feedback).to_have_text("Đã đổi thư mục.")
        expect(page.locator("#local-root-name")).to_have_text("Đang mở · " + new_root.name)
        expect(active_root).to_have_text(str(new_root))
        expect(page.locator('button[data-path="unique.log"]')).to_be_visible()
        expect(page.locator('button[data-path="train.py"]')).to_have_count(0)
        choose(new_root)
        expect(feedback).to_have_text("Thư mục này đang mở.")
        choose(new_root / "missing")
        expect(feedback).to_contain_text("Mở thư mục thất bại")
        expect(feedback).to_have_attribute("data-tone", "error")
        expect(active_root).to_have_text(str(new_root))
        page.locator("#local-folder-cancel").click()
        expect(feedback).to_have_text("Đã hủy chọn thư mục.")
        self.assertEqual(self.page_errors, [])

    def test_folders_are_independent_and_code_saves_by_keyboard(self):
        code = self.project.parent / "code"
        analysis = self.project.parent / "analysis"
        code.mkdir()
        analysis.mkdir()
        (code / "train.py").write_text("print('code')\n", encoding="utf-8")
        (analysis / "results.csv").write_text("metric,value\nloss,0.3\n", encoding="utf-8")
        monitor_text = (self.project / "train.py").read_bytes()
        self.open_project()
        page = self.page

        def choose(folder):
            page.locator("#open-project-file").click()
            page.locator("#local-root").fill(str(folder))
            page.locator("#local-project-form button[type=submit]").click()
            expect(page.locator("#local-active-root")).to_have_text(str(folder))

        page.get_by_role("link", name="Code", exact=True).click()
        choose(code)
        expect(page.locator("#local-explorer-title")).to_have_text("Thư mục Code")
        page.locator('#local-tree button[data-path="train.py"]').click()
        editor = page.locator("#local-code")
        expect(editor).to_have_value("print('code')\n")
        editor.fill("print('ctrl')\n")
        page.locator("#code-left .code-tab").press("Control+s")
        expect(page.locator("#local-status")).to_have_text("Đã lưu train.py.")
        editor.fill("print('meta')\n")
        with page.expect_response(lambda response: response.url.endswith("/file") and response.request.method == "PUT") as saved:
            editor.press("Meta+s")
        self.assertTrue(saved.value.ok)
        self.assertEqual((code / "train.py").read_text(encoding="utf-8"), "print('meta')\n")
        self.assertEqual((self.project / "train.py").read_bytes(), monitor_text)
        page.locator("#local-run-file").click()
        expect(page.locator("#dock-output-text")).to_contain_text("meta", timeout=15000)
        expect(page.locator("#editor")).to_be_visible()

        page.get_by_role("link", name="Phân tích", exact=True).click()
        choose(analysis)
        expect(page.locator("#analysis-explorer-title")).to_have_text("Thư mục phân tích")
        page.locator('#local-tree button[data-path="results.csv"]').click()
        expect(page.locator('#external-preview [name="path"]')).to_have_value("results.csv")
        page.locator('#external-preview button[type="submit"]').click()
        expect(page.locator("#external-sample")).to_contain_text("loss")
        page.get_by_role("link", name="Dự án", exact=True).click()
        expect(page.locator("#local-active-root")).to_have_text(str(self.project))
        page.get_by_role("link", name="Code", exact=True).click()
        expect(page.locator("#local-active-root")).to_have_text(str(code))
        page.get_by_role("link", name="Phân tích", exact=True).click()
        expect(page.locator("#local-active-root")).to_have_text(str(analysis))
        self.assertEqual(self.page_errors, [])

    def test_machine_sample_syncs_log_and_loss_and_switches_named_gpu(self):
        import json

        def gpu(index, name, used, utilization):
            return {"index": index, "uuid": "test-" + str(index), "name": name, "percent": utilization,
                    "vram_used_mib": used, "vram_total_mib": 8192}

        first = "2026-11-08T02:00:00Z"
        middle = "2026-11-08T02:00:04Z"
        last = "2026-11-08T02:00:08Z"
        records = [
            {"timestamp": first, "gpu": [gpu(0, "NVIDIA One", 1024, 8), gpu(1, "NVIDIA Two", 2048, 21)]},
            {"timestamp": middle, "gpu": [gpu(0, "NVIDIA One", 1024, 10)]},
            {"timestamp": last, "gpu": [gpu(1, "NVIDIA Two", 4096, 60), gpu(0, "NVIDIA One", 1024, 12)]},
        ]
        (self.project / "machine.jsonl").write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
        (self.project / "metrics.csv").write_text(
            f"epoch,train_loss,val_loss,timestamp\n1,0.8,0.9,{first}\n2,0.3,0.4,{last}\n", encoding="utf-8")
        (self.project / "train.log").write_text(
            f"{first} INFO first epoch\n{middle} WARN checkpoint from actual log\n{last} INFO last epoch\n", encoding="utf-8")
        self.open_project()
        page = self.page
        page.locator('[data-panel="machine"]').click()
        page.locator('[data-resource="gpu"]').click()
        device = page.locator("#machine-device")
        expect(device.locator("option")).to_have_text(["GPU 0 · NVIDIA One", "GPU 1 · NVIDIA Two"])
        device.select_option("uuid:test-1")
        expect(page.locator("#machine-value")).to_have_text("60%")
        page.locator('[data-resource="vram"]').click()
        expect(page.locator("#machine-capacity")).to_have_text("4 / 8 GiB")
        graph = page.locator("#machine-trend")
        graph.press("ArrowLeft")
        expect(page.locator("#machine-value")).to_have_text("—")
        expect(page.locator("#terminal-body .machine-log-anchor")).to_contain_text("checkpoint from actual log")
        expect(page.locator("#terminal-scope")).to_contain_text("Log trùng mốc")
        page.locator('[data-panel="training"]').click()
        expect(page.locator("#training-sync")).to_contain_text("Lệch 4 s")
        page.locator('[data-panel="machine"]').click()
        graph.press("End")
        page.locator('[data-panel="training"]').click()
        expect(page.locator("#training-sync")).to_contain_text("Epoch 2 · Trùng mốc")
        expect(page.locator('#training-chart [data-epoch="2"]')).to_have_count(1)
        page.locator('[data-panel="machine"]').click()
        page.locator("#machine-latest").click()
        expect(page.locator("#training-sync")).to_be_hidden()
        expect(page.locator("#terminal-body .machine-log-anchor")).to_have_count(0)
        self.assertEqual(self.page_errors, [])

    def test_workspace_trees_and_open_files_restore_after_reload(self):
        folder = self.project / "nested" / "inner"
        folder.mkdir(parents=True)
        (folder / "live.log").write_text("INFO restored log\n", encoding="utf-8")
        (folder / "program.py").write_text("print('restored editor')\n", encoding="utf-8")
        (folder / "data.csv").write_text("metric,value\nloss,0.1\n", encoding="utf-8")
        self.open_project()
        page = self.page

        def open_branches():
            page.locator('details[data-path="nested"] > summary').click()
            page.locator('details[data-path="nested/inner"] > summary').click()

        open_branches()
        page.locator('button[data-path="nested/inner/live.log"]').click()
        expect(page.locator("#terminal-body")).to_contain_text("restored log")
        page.get_by_role("link", name="Code", exact=True).click()
        open_branches()
        page.locator('button[data-path="nested/inner/program.py"]').click()
        expect(page.locator("#local-code")).to_have_value("print('restored editor')\n")
        with page.expect_response(lambda response: "/view-state" in response.url and response.request.method == "PUT"):
            page.locator("#code-split").click()
        page.reload()
        expect(page.locator("#local-code")).to_have_value("print('restored editor')\n")
        expect(page.locator("#code-right")).to_be_visible()
        expect(page.locator('button[data-path="nested/inner/program.py"]')).to_be_visible()
        page.get_by_role("link", name="Dự án", exact=True).click()
        expect(page.locator('button[data-path="nested/inner/live.log"]')).to_be_visible()
        expect(page.locator("#terminal-panes .live-shell")).to_have_attribute("title", re.compile(re.escape(str(self.project))))
        expect(page.locator("#terminal-body")).to_be_hidden()
        page.locator('[data-terminal-action="log"]').click()
        expect(page.locator("#terminal-body")).to_be_visible()
        expect(page.locator("#terminal-body")).to_contain_text("restored log")
        page.get_by_role("link", name="Phân tích", exact=True).click()
        open_branches()
        with page.expect_response(lambda response: "/view-state" in response.url and response.request.method == "PUT"):
            page.locator('button[data-path="nested/inner/data.csv"]').click()
        page.reload()
        expect(page.locator('button[data-path="nested/inner/data.csv"]')).to_have_attribute("aria-pressed", "true")
        expect(page.locator('#external-preview [name="path"]')).to_have_value("nested/inner/data.csv")
        self.assertEqual(self.page_errors, [])

    def test_machine_resources_show_samples_and_keep_missing_gpu_distinct_from_zero(self):
        page = self.page
        page.locator('[data-panel="machine"]').click()
        expect(page.locator("#machine-empty")).to_have_text("Đang chờ dữ liệu tải máy")
        expect(page.locator("#machine-value")).to_have_text("—")
        self.open_project()
        page.locator('[data-panel="machine"]').click()
        expect(page.locator("#machine-state")).to_have_text("Lấy mẫu trực tiếp")
        expect(page.locator("#machine-source")).to_contain_text("Máy này")
        source = self.project / "machine.jsonl"
        source.write_text(
            '{"timestamp":"2026-11-08T02:00:00Z","cpu_percent":12,"ram_percent":40,"gpu_percent":0,'
            '"vram_used_mib":1024,"vram_total_mib":16384}\n'
            '{"timestamp":"2026-11-08T02:00:04Z","cpu_percent":18,"ram_percent":42,'
            '"ram_used_bytes":14495514624,"ram_total_bytes":34359738368}\n'
            '{"timestamp":"2026-11-08T02:00:08Z","cpu_percent":28,"ram_percent":44,"gpu_percent":35,'
            '"ram_used_bytes":15032385536,"ram_total_bytes":34359738368,"vram_used_mib":2048,"vram_total_mib":16384}\n',
            encoding="utf-8",
        )
        expect(page.locator("#machine-source")).to_contain_text("Tệp chỉ số dự án")
        expect(page.locator("#machine-state")).to_have_text("Có dữ liệu")
        expect(page.locator("#machine-value")).to_have_text("28%")
        gpu = page.locator('#machine-chart [data-resource="gpu"]')
        gpu.click()
        expect(gpu).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#machine-value")).to_have_text("35%")
        graph = page.locator("#machine-trend")
        expect(graph.locator(".machine-line")).to_have_count(2)
        graph.press("ArrowLeft")
        expect(page.locator("#machine-value")).to_have_text("—")
        graph.press("Home")
        expect(page.locator("#machine-value")).to_have_text("0%")
        expect(graph).to_be_focused()
        page.locator("#machine-latest").click()
        expect(page.locator("#machine-value")).to_have_text("35%")
        expect(graph).to_be_focused()
        page.locator('#machine-chart [data-resource="vram"]').click()
        expect(page.locator("#machine-value")).to_have_text("12,5%")
        expect(page.locator("#machine-capacity")).to_have_text("2 / 16 GiB")
        page.locator('#machine-chart [data-resource="ram"]').click()
        expect(page.locator("#machine-capacity")).to_have_text("14 / 32 GiB")
        for width, height in ((1440, 880), (1024, 620), (600, 850)):
            page.set_viewport_size({"width": width, "height": height})
            geometry = page.locator("#machine").evaluate("""el => ({
                width: el.clientWidth, scrollWidth: el.scrollWidth,
                height: el.clientHeight, scrollHeight: el.scrollHeight,
                trend: el.querySelector('#machine-trend').clientHeight
            })""")
            self.assertEqual(geometry["width"], geometry["scrollWidth"])
            self.assertGreaterEqual(geometry["trend"], 72)
            if width > 700:
                self.assertLessEqual(geometry["scrollHeight"], geometry["height"] + 1)
        self.assertEqual(self.page_errors, [])

    def test_explorer_search_and_text_file_open_are_independent_of_log_mode(self):
        cache = self.project / "nested" / "cache_heldout"
        cache.mkdir(parents=True)
        (cache / "Base_s42.npz").write_bytes(b"binary")
        (self.project / "requirements.txt").write_bytes(b"flask==3.1.3\n")
        self.open_project()
        page = self.page
        search = page.locator("#local-search-input")
        results = page.locator("#local-search-results")
        search.fill("s42")
        expect(results).to_contain_text("nested/cache_heldout/Base_s42.npz")
        results.locator("button").click()
        expect(page.locator("#local-selected")).to_have_text("nested/cache_heldout/Base_s42.npz")
        search.fill("cache_heldout")
        results.get_by_role("button").click()
        expect(page.locator('details[data-path="nested/cache_heldout"]')).to_have_attribute("open", "")
        expect(page.locator("#local-tree")).to_be_visible()
        search.fill("requirements.txt")
        results.get_by_role("button").click()
        expect(page.locator("#monitor")).to_be_visible()
        expect(page.locator("#editor")).to_be_hidden()
        page.locator("#local-open-editor").click()
        expect(page.locator("#local-code")).to_have_value("flask==3.1.3\n")
        expect(page.locator("#editor")).to_be_visible()
        page.locator("#local-watch-log").click()
        expect(page.locator("#monitor")).to_be_visible()
        expect(page.locator("#terminal-body")).to_contain_text("flask==3.1.3")
        expect(page.locator("#local-status")).not_to_contain_text("before initialization")
        search.press("Escape")
        expect(results).to_be_hidden()
        self.assertEqual(self.page_errors, [])

    def test_code_split_pdf_and_explorer_inline_creation(self):
        import pypdfium2 as pdf

        with pdf.PdfDocument.new() as document:
            document.new_page(280, 320).close()
            document.new_page(400, 350).close()
            document.save(self.project / "report.pdf")
        self.open_project()
        page = self.page
        page.locator('[data-file-action="file"]').click()
        page.locator("#local-target").fill("notes.py")
        page.locator("#local-manage button[type=submit]").click()
        created = page.locator('#local-tree button[data-path="notes.py"]')
        expect(created).to_be_visible()
        page.locator('[data-file-action="rename"]').click()
        page.locator("#local-target").fill("experiment.py")
        page.locator("#local-manage button[type=submit]").click()
        renamed = page.locator('#local-tree button[data-path="experiment.py"]')
        expect(renamed).to_be_visible()
        self.assertFalse((self.project / "notes.py").exists())
        renamed.click()
        expect(page.locator("#monitor")).to_be_visible()
        page.locator("#local-open-editor").click()
        expect(page.get_by_role("link", name="Code", exact=True)).to_have_attribute("aria-current", "page")
        left = page.locator("#local-code")
        left.fill("print('left')\n")
        page.locator("#code-split").click()
        page.locator('#local-tree button[data-path="train.py"]').click()
        right = page.locator("#local-code-right")
        expect(right).to_have_value(TRAIN_SCRIPT)
        right.fill("print('right')\n")
        page.locator("#local-save").click()
        expect(page.locator("#local-status")).to_have_text("Đã lưu train.py.")
        expect(left).to_have_value("print('left')\n")
        page.locator("#code-divider").press("ArrowLeft")
        expect(page.locator("#code-divider")).to_have_attribute("aria-valuenow", "45")
        page.locator('#local-tree button[data-path="report.pdf"]').click()
        pdf_pane = page.locator("#code-right")
        expect(pdf_pane.locator(".pdf-page")).to_have_text("1 / 2")
        image = pdf_pane.locator("img")
        expect(image).to_have_js_property("naturalWidth", 280)
        pdf_pane.locator('[data-pdf="next"]').click()
        expect(pdf_pane.locator(".pdf-page")).to_have_text("2 / 2")
        pdf_pane.locator("select").select_option("150")
        expect(image).to_have_js_property("naturalWidth", 600)
        expect(left).to_have_value("print('left')\n")
        left.press("Control+s")
        expect(page.locator("#local-status")).to_have_text("Đã lưu experiment.py.")
        self.assertEqual((self.project / "experiment.py").read_text(), "print('left')\n")
        for width, height in ((1440, 880), (1024, 620)):
            page.set_viewport_size({"width": width, "height": height})
            geometry = page.locator("#editor").evaluate("""el => ({
                bottom: el.querySelector('#terminal-panes').getBoundingClientRect().bottom,
                height: el.querySelector('#code-panes').getBoundingClientRect().height,
                viewport: innerHeight
            })""")
            self.assertAlmostEqual(geometry["bottom"], geometry["viewport"], delta=2)
            self.assertGreater(geometry["height"], 190)
        self.assertEqual(self.page_errors, [])

    def test_dock_tools_follow_the_clicked_pane_without_replacing_the_split(self):
        (self.project / "worker.log").write_text("WARN pane-local warning\n", encoding="utf-8")
        self.open_project()
        page = self.page
        page.locator('#local-tree button[data-path="worker.log"]').click()
        page.locator('[data-terminal-action="log"]').click()
        shell = page.locator("#terminal-panes .live-shell")
        cmd_pane = shell.locator("xpath=..")
        log_pane = page.locator("#terminal-log-content").locator("xpath=..")
        sessions = page.locator("#terminal-sessions")
        terminal_tab = page.locator('[data-dock-tab="terminal"]')
        problems_tab = page.locator('[data-dock-tab="problems"]')
        output_tab = page.locator('[data-dock-tab="output"]')

        page.locator("#terminal-body").click()
        expect(sessions).to_have_value(log_pane.get_attribute("data-pane"))
        problems_tab.click()
        expect(log_pane.locator("#dock-problems")).to_contain_text("pane-local warning")
        expect(shell).to_be_visible()

        shell.locator(".xterm-screen").click()
        expect(sessions).to_have_value(cmd_pane.get_attribute("data-pane"))
        expect(terminal_tab).to_have_attribute("aria-pressed", "true")
        page.keyboard.insert_text("echo CMD_UNCHANGED")
        page.keyboard.press("Enter")
        expect(shell.locator(".xterm-rows").get_by_text("CMD_UNCHANGED", exact=True)).to_have_count(1)

        output_tab.click()
        expect(cmd_pane.locator("#dock-output")).to_be_visible()
        expect(log_pane.locator("#dock-problems")).to_be_visible()
        cmd_pane.get_by_role("button", name=re.compile("^Phóng to")).click()
        expect(page.locator("#dock-problems")).to_be_hidden()
        cmd_pane.get_by_role("button", name=re.compile("^Khôi phục")).click()
        expect(log_pane.locator("#dock-problems")).to_be_visible()
        log_pane.locator(".pane-select").click()
        output_tab.click()
        expect(log_pane.locator("#dock-output")).to_be_visible()
        expect(shell).to_be_visible()
        cmd_pane.locator(".pane-select").click()
        expect(shell.locator(".xterm-helper-textarea")).to_be_focused()
        expect(shell.locator(".xterm-rows").get_by_text("CMD_UNCHANGED", exact=True)).to_have_count(1)

        log_pane.locator(".pane-select").click()
        expect(output_tab).to_have_attribute("aria-pressed", "true")
        terminal_tab.click()
        expect(log_pane.locator("#terminal-body")).to_be_visible()
        expect(shell).to_be_visible()
        self.assertEqual(self.page_errors, [])

    def test_dock_output_problems_ports_and_interactive_debugger(self):
        self.open_project()
        page = self.page
        log = self.project / "worker.log"
        log.write_text('WARN <b>literal</b>\n  File "train.py", line 2, in run\n', encoding="utf-8")
        page.locator('#local-tree button[data-path="worker.log"]').click()
        expect(page.locator("#terminal-body")).to_contain_text("WARN")
        page.locator('[data-dock-tab="output"]').click()
        expect(page.locator("#dock-output-text")).to_contain_text("<b>literal</b>")
        expect(page.locator("#dock-output-text b")).to_have_count(0)
        page.locator('[data-dock-tab="ports"]').click()
        expect(page.locator("#dock-port-rows")).to_contain_text(str(self.local["port"]))
        page.locator('[data-dock-tab="problems"]').click()
        page.get_by_role("button", name="Mở train.py:2").click()
        expect(page.locator("#local-editor-status")).to_contain_text("train.py · dòng 2")
        page.locator('[data-dock-tab="debug"]').click()
        page.locator("#dock-debug-start").click()
        debugger = page.locator("#dock-debug-shell")
        expect(debugger.locator(".xterm-rows")).to_contain_text("(Pdb)", timeout=12000)
        debugger.locator(".xterm-helper-textarea").focus()
        page.keyboard.type("p 6 * 7")
        page.keyboard.press("Enter")
        expect(debugger.locator(".xterm-rows").get_by_text("42", exact=True)).to_have_count(1)
        page.locator("#dock-debug-stop").click()
        expect(debugger).to_be_hidden()
        page.locator('[data-dock-tab="terminal"]').click()
        expect(page.locator("#terminal-panes")).to_be_visible()
        expect(page.locator("#terminal-body")).to_contain_text("WARN")
        self.assertEqual(self.page_errors, [])

    def test_live_timeline_drills_into_severity_and_returns_to_latest(self):
        log = self.project / "worker.log"
        log.write_bytes(b"2026-11-08T10:00:00Z WARN queue busy\n"
                        b"2026-11-08T10:00:00Z ERROR request failed\n"
                        b"2026-11-08T10:00:00Z FATAL process stopped\n")
        self.open_project()
        page = self.page
        page.locator('#local-tree button[data-path="worker.log"]').click()
        expect(page.locator("#monitor")).to_be_visible()
        expect(page.locator("#editor")).to_be_hidden()
        chart = page.locator("#severity-chart")
        expect(chart.locator('[data-lane="all"]')).to_have_text("3")
        critical = chart.locator('[data-lane="CRITICAL"]')
        expect(critical).to_have_text("1")
        expect(critical).to_have_attribute("data-tone", "CRITICAL")
        critical.press("Enter")
        expect(critical).to_be_focused()
        expect(critical).to_have_attribute("aria-pressed", "true")
        expect(page.locator("#activity-detail")).to_contain_text("WARN 1 · ERROR 1 · CRITICAL 1")
        terminal = page.locator("#terminal-body")
        expect(terminal).to_contain_text("FATAL process stopped")
        expect(terminal).not_to_contain_text("queue busy")
        page.locator('[data-activity-mode="volume"]').click()
        expect(chart.locator(".heatmap")).to_have_attribute("data-mode", "volume")
        page.locator('[data-panel="results"]').click()
        expect(page.locator("#result-list button")).to_have_count(1)
        with log.open("ab") as stream:
            stream.write(b"2026-11-08T10:00:10Z ERROR new event after selection\n")
        expect(terminal).not_to_contain_text("new event after selection")
        page.locator('[data-panel="activity"]').click()
        page.locator("#activity-live").click()
        expect(terminal).to_contain_text("new event after selection", timeout=7000)
        expect(terminal).to_contain_text("queue busy")
        self.assertEqual(self.page_errors, [])

    def test_traceback_opens_exact_line_and_two_real_runs_compare(self):
        self.open_project()
        page = self.page
        scripts = {
            "run_a.py": "from pathlib import Path\nimport os\nPath(os.environ['H_LOGSEN_METRICS_CSV']).write_text('epoch,train_loss\\n1,0.5\\n2,0.4\\n')\n",
            "run_b.py": "from pathlib import Path\nimport os\nPath(os.environ['H_LOGSEN_METRICS_CSV']).write_text('epoch,train_loss\\n1,0.25\\n')\nraise RuntimeError('known location')\n",
        }
        for name, script in scripts.items():
            (self.project / name).write_text(script, encoding="utf-8")
        runs = []
        for name, outcome in (("run_a.py", "completed"), ("run_b.py", "failed")):
            page.locator(f'#local-tree button[data-path="{name}"]').click(timeout=10000)
            page.locator("#local-open-editor").click()
            with page.expect_response(lambda res: res.url.endswith("/runs") and res.request.method == "POST") as created:
                page.locator("#local-run-file").click()
            runs.append(created.value.json()["id"])
            expect(page.locator("#run-detail-meta")).to_contain_text(outcome, timeout=12000)
        source = page.locator("#run-source-links").get_by_role("button", name="Mở run_b.py:4")
        source.click()
        expect(page.locator("#local-editor-status")).to_contain_text("run_b.py · dòng 4")
        selected = page.locator("#local-code").evaluate("(el) => el.value.slice(el.selectionStart, el.selectionEnd)")
        self.assertEqual(selected, "raise RuntimeError('known location')")
        link = page.evaluate("() => window.WorkbenchSourceLinks.reference('tests/test_x.py:17: AssertionError', 'C:/project')")
        self.assertEqual((link["path"], link["line"]), ("tests/test_x.py", 17))
        self.assertIsNone(page.evaluate("() => window.WorkbenchSourceLinks.reference('File \"C:/other/test_x.py\", line 3', 'C:/project')"))
        page.get_by_role("link", name="Dự án", exact=True).click()
        panel = page.locator("#run-compare")
        top = page.locator(".monitor-top")
        scope = page.locator(".monitor-scope")
        before = top.bounding_box(), scope.bounding_box()
        page.locator("#run-compare-toggle").click()
        self.assertEqual(before, (top.bounding_box(), scope.bounding_box()))
        expect(page.locator("#run-compare-close")).to_be_focused()
        panel.locator('[name="left"]').select_option(runs[0], timeout=10000)
        panel.locator('[name="right"]').select_option(runs[1], timeout=10000)
        panel.get_by_role("button", name="So sánh", exact=True).click()
        row = page.locator("#run-compare-rows tr").filter(has_text="Train loss · epoch 1")
        expect(row).to_contain_text("0,5")
        expect(row).to_contain_text("0,25")
        expect(page.locator("#compare-train-loss svg")).to_be_visible()
        expect(page.locator("#run-compare-rows tr").filter(has_text="Đỉnh CPU")).to_contain_text("mẫu")
        expect(page.locator("#run-compare-rows tr").filter(has_text="SHA-256 mã chạy")).to_have_attribute("data-changed", "true")
        page.locator("#run-compare-close").press("Escape")
        expect(panel).to_be_hidden()
        expect(page.locator("#run-compare-toggle")).to_be_focused()
        self.assertEqual(self.page_errors, [])

    def test_terminal_reconnect_resumes_same_cursor_without_duplicate_output(self):
        self.open_project()
        page = self.page
        page.locator("#terminal-panes [data-pane-close]").click()
        disconnect = False
        transport = []
        terminal_ids = set()
        input_writes = []

        def intercept(route):
            request = route.request
            url = urlsplit(request.url)
            terminal_ids.add(url.path.rsplit("/", 1)[-1])
            if request.method != "GET":
                if request.method == "POST" and "text" in (request.post_data_json or {}):
                    input_writes.append(request.post_data_json["text"])
                return route.continue_()
            cursor = int(parse_qs(url.query)["offset"][0])
            transport.append((disconnect, cursor))
            if disconnect and len(transport) % 2:
                return route.fulfill(status=503, body="<html>temporary failure</html>")
            if disconnect:
                return route.abort("internetdisconnected")
            return route.continue_()

        page.route("**/api/local/v1/terminals/*", intercept)
        page.locator("#local-shell").select_option("CMD" if os.name == "nt" else "sh")
        with page.expect_response(lambda response: response.url.endswith("/terminals") and response.request.method == "POST") as created:
            page.locator('[data-terminal-action="new"]').click()
        session = created.value.json()["id"]
        pane = page.locator("#terminal-panes .live-shell")
        status = pane.locator(".terminal-connection")
        expect(status).to_have_text("")
        output = pane.locator(".xterm-rows")
        console = pane.locator(".xterm-helper-textarea")
        console.focus()
        command = (f'"{sys.executable}" -u -c "import time; print(347629); time.sleep(2); '
                   'print(347630); time.sleep(0.4); print(347631)"')
        # The echoed shell command contains the digits. Match the full output row.
        page.keyboard.insert_text(command)
        page.keyboard.press("Enter")
        expect(output.get_by_text("347629", exact=True)).to_have_count(1, timeout=10000)
        disconnect = True
        expect(status).to_contain_text("Mất kết nối")
        written = len(input_writes)
        console.focus()
        page.keyboard.insert_text("must-not-send")
        page.wait_for_timeout(2700)
        self.assertEqual(len(input_writes), written)
        self.assertFalse(output.get_by_text("347630", exact=True).count())
        offline = [cursor for failed, cursor in transport if failed]
        self.assertGreaterEqual(len(offline), 2)
        self.assertGreater(offline[0], 0)
        self.assertEqual(set(offline), {offline[0]})
        disconnect = False
        expect(status).to_have_text("Đã kết nối lại cùng phiên.", timeout=10000)
        for number in ("347629", "347630", "347631"):
            expect(output.get_by_text(number, exact=True)).to_have_count(1)
        self.assertEqual(terminal_ids, {session})
        self.assertIn((False, offline[0]), transport[transport.index((True, offline[0])):])
        pane.locator("xpath=..").locator("button[aria-label^='Phóng to']").click()
        console.focus()
        command = (f'"{sys.executable}" -u -c "from pathlib import Path; '
                   "print(str(Path('train.py').resolve()) + ':3:1')\"")
        page.keyboard.insert_text(command)
        page.keyboard.press("Enter")
        reference = output.get_by_text(str(self.project / "train.py") + ":3:1", exact=True)
        expect(reference).to_have_count(1)
        target = reference.bounding_box()
        self.assertIsNotNone(target)
        x, y = target["x"] + 5, target["y"] + target["height"] / 2
        page.mouse.move(x, y)
        page.mouse.click(x, y)
        expect(page.locator("#local-editor-status")).to_contain_text("train.py · dòng 3")
        self.local["terminals"].close(session)
        expect(status).to_have_text("Phiên shell không còn trên máy chủ.")
        requests = len(transport)
        page.wait_for_timeout(600)
        self.assertEqual(len(transport), requests)
        self.assertEqual(self.page_errors, [])

    def test_shells_use_project_python_and_can_interrupt(self):
        self.project = self.project.rename(self.project.with_name("test code"))
        venv = self.project / ".venv"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=30)
        (self.project / "code.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "Path('used-python.txt').write_text(sys.prefix, encoding='utf-8')\n"
            "print('PYTHON_FROM_PROJECT')\n", encoding="utf-8")
        (self.project / "wait.py").write_text(
            "import os, time\nfrom pathlib import Path\n"
            "Path('wait-pid.txt').write_text(str(os.getpid()), encoding='utf-8')\n"
            "print('PTY_WAIT_STARTED', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
        self.open_project()
        page = self.page
        page.get_by_role("link", name="Code", exact=True).click()
        choice = page.locator("#code-interpreter")
        expect(choice).to_have_value(".venv")
        page.locator("#terminal-panes [data-pane-close]").click()
        for shell in (("PowerShell", "CMD") if os.name == "nt" else ("sh",)):
            with self.subTest(shell=shell):
                marker = self.project / "used-python.txt"
                marker.unlink(missing_ok=True)
                page.locator("#local-shell").select_option(shell)
                page.locator('[data-terminal-action="new"]').click()
                pane = page.locator("#terminal-panes .live-shell").last
                expect(pane.locator(".terminal-connection")).to_have_text("")
                expect(pane).to_have_attribute("title", re.compile(r"Python: .*\.venv"))
                pane.locator(".xterm-helper-textarea").focus()
                output = pane.locator(".xterm-rows")
                page.keyboard.type("python code.py", delay=8)
                page.keyboard.press("Enter")
                expect(output.get_by_text("PYTHON_FROM_PROJECT", exact=True)).to_have_count(1, timeout=12000)
                self.assertEqual(Path(marker.read_text(encoding="utf-8")).resolve(), venv.resolve())
                page.keyboard.insert_text("python wait.py")
                page.keyboard.press("Enter")
                expect(output.get_by_text("PTY_WAIT_STARTED", exact=True)).to_have_count(1)
                child = psutil.Process(int((self.project / "wait-pid.txt").read_text(encoding="utf-8")))
                page.keyboard.press("Control+c")
                child.wait(timeout=7)
                prompt = re.escape(str(self.project)) + r">\s*$" if os.name == "nt" else r"[$#]\s*$"
                expect(output).to_have_text(re.compile(prompt), use_inner_text=True)
                page.keyboard.insert_text("python -c \"print(546389)\"")
                page.keyboard.press("Enter")
                expect(output.get_by_text("546389", exact=True)).to_have_count(1, timeout=10000)
                pane.locator("xpath=..").locator("[data-pane-close]").click()
        choice.select_option("app")
        expect(page.locator("#local-status")).to_contain_text("Mở phiên terminal mới")
        expect(choice).to_have_value("app")
        self.assertEqual(self.page_errors, [])

    def test_split_shells_have_independent_working_directories_and_input(self):
        (self.project / "split folder").mkdir()
        self.open_project()
        page = self.page
        profile = page.locator("#local-shell")
        selection = page.locator("#terminal-sessions")
        shells = page.locator("#terminal-panes .live-shell")
        windows = os.name == "nt"

        page.locator("#terminal-panes [data-pane-close]").click()
        profile.select_option("PowerShell" if windows else "sh")
        page.locator('[data-terminal-action="new"]').click()
        first = shells.nth(0)
        expect(first.locator(".xterm-helper-textarea")).to_be_focused()

        profile.select_option("CMD" if windows else "sh")
        page.locator("#terminal-split-menu").select_option("right")
        second = shells.nth(1)
        expect(second.locator(".xterm-helper-textarea")).to_be_focused()

        def select_shell(shell):
            shell.locator(".xterm-screen").click()
            pane = shell.locator("xpath=..")
            expect(selection).to_have_value(pane.get_attribute("data-pane"))
            expect(shell.locator(".xterm-helper-textarea")).to_be_focused()

        def command(text):
            page.keyboard.insert_text(text)
            page.keyboard.press("Enter")

        select_shell(first)
        command("cd 'split folder'")
        command("(Get-Item .).Name" if windows else 'printf "%s\\n" "${PWD##*/}"')
        expect(first.locator(".xterm-rows").get_by_text("split folder", exact=True)).to_have_count(1)
        command("$env:HLOGSEN_SPLIT_TEST = 'first'" if windows else "export HLOGSEN_SPLIT_TEST=first")

        select_shell(second)
        command("for %I in (.) do @echo %~nxI" if windows else 'printf "%s\\n" "${PWD##*/}"')
        expect(second.locator(".xterm-rows").get_by_text(self.project.name, exact=True)).to_have_count(1)
        command("if not defined HLOGSEN_SPLIT_TEST echo SPLIT_ISOLATED" if windows else
                "test -z \"$HLOGSEN_SPLIT_TEST\" && echo SPLIT_ISOLATED")
        expect(second.locator(".xterm-rows").get_by_text("SPLIT_ISOLATED", exact=True)).to_have_count(1)
        second.locator("xpath=..").locator("[data-pane-close]").click()

        expect(first.locator(".xterm-helper-textarea")).to_be_focused()
        command("Write-Output $env:HLOGSEN_SPLIT_TEST" if windows else "echo \"$HLOGSEN_SPLIT_TEST\"")
        expect(first.locator(".xterm-rows").get_by_text("first", exact=True)).to_have_count(1)
        self.assertEqual(self.page_errors, [])

    @unittest.skipUnless(os.environ.get("HLOGSEN_QA_TOOLS"), "requires a fixture with Ruff, Pyright and Prettier")
    def test_real_project_tools_check_jump_format_and_run(self):
        fixture = Path(os.environ["HLOGSEN_QA_TOOLS"])
        shutil.copytree(fixture / ".venv", self.project / ".venv")
        shutil.copytree(fixture / "node_modules", self.project / "node_modules", symlinks=True)
        python_file = self.project / "train.py"
        original = 'import os\nvalue: int = "text"\nprint(  42  )\n'
        python_file.write_text(original, encoding="utf-8")
        (self.project / "report.js").write_text("console.log(   43   );\n", encoding="utf-8")
        page = self.page
        page.get_by_role("link", name="Code", exact=True).click()
        self.open_project()
        page.locator('#local-tree button[data-path="train.py"]').click()
        expect(page.locator("#code-interpreter")).to_have_value(".venv")
        editor = page.locator("#local-code")
        page.locator("#local-check-code").click()
        rows = page.locator("#dock-code-problem-rows")
        expect(rows).to_contain_text("Ruff F401", timeout=20000)
        expect(rows).to_contain_text("Pyright reportAssignmentType", timeout=20000)
        rows.get_by_role("button", name="Mở train.py:2").click()
        expect(page.locator("#local-editor-status")).to_contain_text("train.py · dòng 2")
        position = editor.evaluate("(el) => el.selectionStart")
        self.assertTrue(original.index("value") <= position < original.index("print"))

        page.locator("#local-format-code").click()
        formatted = 'import os\n\nvalue: int = "text"\nprint(42)\n'
        expect(editor).to_have_value(formatted)
        self.assertEqual(python_file.read_text(encoding="utf-8"), original)
        expect(rows).to_be_empty()
        page.locator("#local-run-code").click()
        expect(page.locator("#local-status")).to_have_text("Lưu tệp trước khi chạy.")
        editor.press("Control+s")
        expect(page.locator("#local-status")).to_have_text("Đã lưu train.py.")
        page.locator("#local-run-code").click()
        terminal = page.locator(".terminal-pane").filter(has=page.get_by_role("button", name=re.compile(r"^\d+ · train\.py$")))
        expect(terminal.locator(".xterm-rows")).to_contain_text("42", timeout=12000)

        page.locator('#local-tree button[data-path="report.js"]').click()
        page.locator("#local-format-code").click()
        expect(editor).to_have_value("console.log(43);\n")
        editor.press("Control+s")
        expect(page.locator("#local-status")).to_have_text("Đã lưu report.js.")
        page.locator("#local-run-code").click()
        terminal = page.locator(".terminal-pane").filter(has=page.get_by_role("button", name=re.compile(r"^\d+ · report\.js$")))
        expect(terminal.locator(".xterm-rows")).to_contain_text("43", timeout=12000)
        self.assertEqual(self.page_errors, [])

    def test_code_highlights_off_thread_and_keeps_composing_text(self):
        self.open_project()
        page = self.page
        page.locator('#local-tree button[data-path="train.py"]').click()
        page.locator("#local-open-editor").click()
        editor = page.locator("#local-code")
        layer = page.locator("#code-left .local-editor-layer")
        expect(layer).to_have_attribute("data-highlight", "true")
        self.assertFalse(page.evaluate("() => Boolean(window.hljs)"))
        editor.focus()
        editor.press("Control+End")
        editor.dispatch_event("compositionstart")
        editor.press("Enter")
        page.keyboard.insert_text("# tiếng Việt thử")
        expect(editor).to_be_focused()
        expect(layer).to_have_attribute("data-highlight", "false")
        expect(page.locator("#local-save")).to_be_enabled()
        editor.dispatch_event("compositionend")
        expect(layer).to_have_attribute("data-highlight", "true")
        expect(layer.locator("code")).to_contain_text("# tiếng Việt thử")
        with page.expect_response(lambda response: response.url.endswith("/file") and response.request.method == "PUT") as saved:
            editor.press("Control+s")
        self.assertTrue(saved.value.ok)
        expect(page.locator("#local-status")).to_contain_text("Đã lưu train.py")
        expect(page.locator("#local-save")).to_be_disabled()
        self.assertIn("# tiếng Việt thử", (self.project / "train.py").read_text(encoding="utf-8"))
        self.assertEqual(self.page_errors, [])

    def test_default_shell_starts_at_home_and_log_opens_on_demand(self):
        page = self.page
        pane = page.locator("#terminal-panes .live-shell")
        expect(pane).to_have_count(1)
        expect(pane.locator(".xterm-helper-textarea")).to_be_focused()
        expect(page.locator("#terminal-body")).to_be_hidden()
        if os.name == "nt":
            expect(page.locator("#local-shell")).to_have_value("CMD")
            expect(pane.locator(".xterm-rows").get_by_text(str(Path.home()) + ">", exact=True)).to_be_visible()
        command = "echo HLOGSEN_HOME_SHELL" if os.name == "nt" else "printf '%s%s\\n' HLOGSEN_HOME_ SHELL"
        page.keyboard.insert_text(command)
        page.keyboard.press("Enter")
        expect(pane.locator(".xterm-rows").get_by_text("HLOGSEN_HOME_SHELL", exact=True)).to_have_count(1)
        expect(pane).to_have_attribute("title", re.compile(re.escape("Thư mục khi mở phiên: " + str(Path.home())) + r"\nPython: .+"))
        log = page.locator('[data-terminal-action="log"]')
        log.click()
        log.click()
        expect(page.locator("#terminal-body")).to_be_visible()
        expect(page.locator("#terminal-panes .terminal-pane")).to_have_count(2)
        expect(pane.locator(".xterm-rows").get_by_text("HLOGSEN_HOME_SHELL", exact=True)).to_have_count(1)
        page.locator("#terminal-log-content").locator("xpath=..").locator("[data-pane-close]").click()
        expect(page.locator("#terminal-body")).to_be_hidden()
        expect(pane.locator(".xterm-helper-textarea")).to_be_focused()
        self.assertEqual(self.page_errors, [])


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    unittest.main(verbosity=2)
