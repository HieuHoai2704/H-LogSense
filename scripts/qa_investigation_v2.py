"""Local Edge browser verification. Playwright is a QA utility, not app runtime.

Run from the project root: .venv/Scripts/python.exe scripts/qa_investigation_v2.py
The owned loopback server is shut down even when an assertion fails.
"""
import csv
import io
import json
import logging
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import request
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server
from app import create_app


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'docs/ui/implementation-v2'
    output.mkdir(parents=True, exist_ok=True)
    app = create_app()

    @app.before_request
    def slow_old_query():
        # Test-only delay makes the first request complete after its successor.
        if request.path == '/api/v1/investigation' and request.args.get('q') == 'kernel':
            time.sleep(.5)

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    passed = []
    errors = []
    requests = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda req: requests.append(req.url))

            def ready(count=None):
                expect(page.locator('#workspace-results')).to_have_attribute('aria-busy', 'false')
                if count is not None:
                    expect(page.locator('[data-row-id]')).to_have_count(count)

            def reset():
                page.goto(base, wait_until='networkidle')
                ready(6)

            def capture(name):
                page.evaluate('document.activeElement.blur(); window.scrollTo(0,0)')
                page.screenshot(path=str(output/name), full_page=True)

            reset()
            expect(page.locator('.overall-row [data-cell]')).to_have_count(12)
            expect(page.locator('.detector-group')).to_have_count(2)
            assert 'LogSense' not in page.locator('body').inner_text()
            assert 'DEMO' in page.locator('.demo-notice').inner_text()
            passed.append('Single workspace, Overall, four detectors and persistent DEMO')
            capture('workspace-1440.png')

            before = page.locator('[data-row-id]').evaluate_all('(rows)=>rows.map(r=>r.dataset.rowId)')
            page.get_by_role('button', name='Volume', exact=True).click()
            expect(page.locator('.timeline-panel')).to_have_class('panel timeline-panel mode-volume')
            expect(page.locator('#volume-legend')).to_be_visible()
            assert before == page.locator('[data-row-id]').evaluate_all('(rows)=>rows.map(r=>r.dataset.rowId)')
            page.get_by_role('button', name='Severity', exact=True).click()
            passed.append('Severity/Volume switch changes encoding without result membership')

            cell = page.locator('[data-cell][data-detector="error-burst"][data-count="1"]')
            cell.hover()
            expect(page.locator('#bin-inspector')).to_contain_text('C 1')
            cell.click()
            ready(1)
            expect(page.locator('.selected-cell')).to_have_count(1)
            assert page.locator('[data-row-id]').get_attribute('data-row-id') == 'LS-1042'
            capture('workspace-selection.png')
            passed.append('Cell inspection, precise selection and linked result')

            with page.expect_download() as download:
                page.locator('#export-button').click()
            csv_path = output/'selected-scope.csv'
            download.value.save_as(str(csv_path))
            rows = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8'))))
            assert [r['id'] for r in rows] == ['LS-1042']
            assert rows[0]['synthetic'] == 'True'
            passed.append('Server CSV matches selected scope and labels synthetic rows')

            page.get_by_role('button', name='Inspect LS-1042', exact=True).click()
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-actual')).to_have_text('42 errors / min')
            expect(page.locator('#detail-raw')).to_contain_text('[DEMO]')
            expect(page.locator('#detail-panel')).to_have_attribute('aria-modal', 'true')
            assert page.locator('.app-shell').evaluate('(e)=>e.inert')
            capture('workspace-evidence.png')
            page.locator('#export-evidence').focus()
            page.keyboard.press('Tab')
            expect(page.locator('#close-detail')).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.locator('#detail-panel')).to_be_hidden()
            expect(page.get_by_role('button', name='Inspect LS-1042', exact=True)).to_be_focused()
            expect(page.locator('.selected-cell')).to_have_count(1)
            passed.append('Evidence from API, modal focus loop and close preserves selection/focus')

            page.get_by_role('link', name='Clear timeline selection', exact=True).click()
            ready(6)
            page.locator('#picker-host summary').click()
            page.locator('[name="host"][value="storage-02"]').check()
            page.locator('[name="host"][value="gateway-01"]').check()
            page.locator('#picker-host .apply-picker').click()
            ready(4)
            page.locator('#picker-severity summary').click()
            page.locator('[name="severity"][value="High"]').check()
            page.locator('#picker-severity .apply-picker').click()
            ready(2)
            assert page.locator('.filter-chip').count() == 3
            assert page.url.count('host=') == 2
            page.get_by_role('link', name='Remove Host: storage-02', exact=True).click()
            ready(1)
            assert 'LS-1040' == page.locator('[data-row-id]').get_attribute('data-row-id')
            passed.append('OR hosts, AND priority, truthful facets, removable chips and URL state')
            page.get_by_role('link', name='Clear filters', exact=True).click()
            ready(6)

            # Pointer brush is selection first, not an automatic pixel zoom.
            boxes = page.locator('.overall-row [data-cell]')
            a, b = boxes.nth(5).bounding_box(), boxes.nth(8).bounding_box()
            page.mouse.move(a['x']+a['width']/2, a['y']+a['height']/2)
            page.mouse.down()
            page.mouse.move(b['x']+b['width']/2, b['y']+b['height']/2, steps=8)
            page.mouse.up()
            ready(4)
            assert 'selection_detector=' not in page.url
            expect(page.locator('.overall-row .selected-cell')).to_have_count(4)
            old_start = page.evaluate('applied.start_time')
            page.get_by_role('button', name='Zoom to selection', exact=True).click()
            ready(4)
            assert page.evaluate('applied.start_time') != old_start
            expect(page.locator('.overall-row [data-cell]')).to_have_count(4)
            page.get_by_role('button', name='Reset zoom', exact=True).click()
            ready(6)
            expect(page.locator('.overall-row [data-cell]')).to_have_count(12)
            passed.append('Pointer brush, backend zoom recomputation and reset to initial range')

            page.locator('.overall-row [data-cell]').first.focus()
            for _ in range(6):
                page.keyboard.press('Shift+ArrowRight')
            page.keyboard.press('Enter')
            ready(4)
            expect(page.locator('.overall-row .selected-cell')).to_have_count(7)
            passed.append('Keyboard range selection matches pointer interval semantics')
            page.get_by_role('link', name='Clear timeline selection', exact=True).click()
            ready(6)

            page.get_by_label('Timezone', exact=True).select_option('America/New_York')
            ready(6)
            expect(page.locator('.time-caption')).to_contain_text('-0500')
            previous_range = page.evaluate('applied.range')
            previous_start = page.evaluate('applied.start_time')
            page.get_by_label('Time range', exact=True).select_option('30d')
            ready(6)
            assert page.evaluate('applied.range') == '30d'
            assert page.locator('.overall-row [data-cell]').count() <= 120
            assert 'Auto resolution: 1440 min' in page.locator('.timeline-toolbar').inner_text()
            page.go_back(wait_until='networkidle')
            page.wait_for_function('(expected) => applied.range === expected', arg=previous_range)
            ready(6)
            assert page.evaluate('applied.start_time') == previous_start
            page.reload(wait_until='networkidle')
            ready(6)
            assert page.locator('#timezone').input_value() == 'America/New_York'
            passed.append('Timezone labels, adaptive long-range resolution, browser back and reload')

            for source, text in [('empty', 'No data available'), ('unprocessed', 'No detection results'), ('partial', 'partial')]:
                page.get_by_label('Source', exact=True).select_option(source)
                ready(6 if source == 'partial' else 0)
                expect(page.locator('#coverage-details summary')).to_contain_text('partial' if source == 'partial' else 'no data' if source == 'empty' else 'unprocessed')
                if source != 'partial':
                    expect(page.locator('.empty-state')).to_contain_text(text)
            assert page.locator('.overall-row .coverage-missing').count() == 3
            capture('workspace-partial.png')
            passed.append('Distinct empty, unprocessed and partial/missing coverage fixtures')
            reset()

            # Backend failure keeps previously applied scope and disables export.
            page.route('**/api/v1/investigation*', lambda route: route.abort('failed'))
            page.get_by_label('Search demo events', exact=True).fill('timeout')
            page.get_by_role('button', name='Apply', exact=True).click()
            expect(page.locator('#request-error')).to_be_visible()
            ready(6)
            expect(page.locator('#export-button')).to_have_attribute('aria-disabled', 'true')
            page.unroute('**/api/v1/investigation*')
            page.get_by_role('button', name='Retry', exact=True).click()
            ready(1)
            passed.append('Query failure retains labelled old scope; Retry applies new scope')
            reset()

            page.get_by_label('Search demo events', exact=True).fill('kernel')
            page.get_by_role('button', name='Apply', exact=True).click()
            expect(page.locator('#workspace-results')).to_have_attribute('aria-busy', 'true')
            page.get_by_label('Search demo events', exact=True).fill('timeout')
            page.get_by_role('button', name='Apply', exact=True).click()
            ready(1)
            page.wait_for_timeout(650)  # Bounded observation of deliberately delayed old response.
            assert page.locator('[data-row-id]').get_attribute('data-row-id') == 'LS-1040'
            assert page.evaluate('applied.q') == 'timeout'
            passed.append('Rapid filters: aborted/delayed old response cannot overwrite latest results')

            reset()
            page.route('**/api/v1/anomalies/LS-1042/evidence**', lambda route: route.abort('failed'))
            page.get_by_role('button', name='Inspect LS-1042', exact=True).click()
            expect(page.locator('#retry-detail')).to_be_visible()
            expect(page.locator('#detail-content')).to_be_hidden()
            page.unroute('**/api/v1/anomalies/LS-1042/evidence**')
            page.locator('#retry-detail').click()
            expect(page.locator('#detail-content')).to_be_visible()
            page.keyboard.press('Escape')
            passed.append('Evidence error/retry does not invent or retain another record evidence')

            page.get_by_role('button', name='Inspect LS-1041', exact=True).click()
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-related')).to_contain_text('LS-1038')
            page.locator('[data-related-id="LS-1038"]').click()
            expect(page.locator('#detail-title')).to_have_text('LS-1038')
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-actual')).to_have_text('28 warnings / min')
            page.keyboard.press('Escape')
            ready(6)
            passed.append('Related evidence comes from the selected same-host fixture record')

            reset()
            # Exact UTC entry is an accessible alternative to pointer brushing.
            page.get_by_label('Time range', exact=True).select_option('custom')
            page.locator('#custom-start').fill('2026-11-03T06:50')
            page.locator('#custom-end').fill('2026-11-03T07:25')
            page.get_by_role('button', name='Use range', exact=True).click()
            ready(4)
            assert page.evaluate('applied.end_time') == '2026-11-03T07:25:00Z'
            page.get_by_role('button', name='Select range…', exact=True).click()
            page.locator('#selection-input-start').fill('2026-11-03T07:15')
            page.locator('#selection-input-end').fill('2026-11-03T07:25')
            page.get_by_role('button', name='Select interval', exact=True).click()
            ready(2)
            passed.append('Custom UTC query range and exact interval form work without dragging')

            page.goto(base+'/?limit=2', wait_until='networkidle')
            ready(2)
            page.get_by_role('link', name='Next', exact=True).click()
            ready(2)
            assert page.locator('[data-row-id]').first.get_attribute('data-row-id') == 'LS-1040'
            assert page.evaluate('applied.page') == 2
            passed.append('Results pagination preserves global scope')

            reset()
            previous = sum('/api/v1/investigation' in url for url in requests)
            page.get_by_label('Search demo events', exact=True).fill('kernel')
            page.get_by_role('button', name='Apply', exact=True).click()
            page.get_by_role('button', name='Apply', exact=True).click()
            ready(2)
            assert sum('/api/v1/investigation' in url for url in requests)-previous == 1
            passed.append('Duplicate submissions reuse one pending query')

            reset()
            page.get_by_label('Search demo events', exact=True).fill('kernel')
            page.get_by_role('button', name='Apply', exact=True).click()
            page.get_by_label('Search demo events', exact=True).fill('timeout')
            ready(2)
            expect(page.get_by_label('Search demo events', exact=True)).to_have_value('timeout')
            expect(page.locator('#export-button')).to_have_attribute('aria-disabled', 'true')
            page.get_by_role('button', name='Apply', exact=True).click()
            ready(1)
            passed.append('Unsubmitted edits survive an older pending query commit')
            reset()

            held = []
            page.clock.install()
            page.route('**/api/v1/investigation*', lambda route: held.append(route))
            page.get_by_label('Search demo events', exact=True).fill('timeout')
            page.get_by_role('button', name='Apply', exact=True).click()
            expect(page.locator('#workspace-results')).to_have_attribute('aria-busy', 'true')
            page.clock.fast_forward(15001)
            expect(page.locator('#error-message')).to_contain_text('timed out')
            ready(6)
            for route in held:
                route.abort('aborted')
            page.unroute('**/api/v1/investigation*')
            page.clock.resume()
            page.get_by_role('button', name='Revert filters', exact=True).click()
            ready(6)
            passed.append('Slow/hung query timeout retains old results and supports revert')
            reset()

            for width in [1920, 1440, 1366, 1024, 390]:
                page.set_viewport_size({'width': width, 'height': 900})
                page.wait_for_timeout(350)
                ready(6)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                if width in [1440, 1366, 1024]:
                    capture(f'workspace-{width}.png')
            passed.append('1920/1440/1366/1024/390 layouts: no document-level horizontal overflow')
            page.set_viewport_size({'width': 1366, 'height': 900})
            page.wait_for_timeout(350)
            page.locator('#picker-detector summary').click()
            page.get_by_label('Find detector', exact=True).fill('Isolation')
            assert page.locator('#picker-detector .facet-option:visible').count() == 1
            page.keyboard.press('Escape')
            expect(page.locator('#picker-detector summary')).to_be_focused()
            page.locator('.detector-group summary').first.click()
            assert page.locator('.detector-group').first.get_attribute('open') is None
            page.locator('.detector-group summary').first.click()
            passed.append('Detector search, group collapse and picker Escape focus')

            assert not errors, errors
            browser.close()
        report = dict(passed=passed, count=len(passed), page_errors=errors, api_request_count=sum('/api/' in url for url in requests),
                      scope='Synthetic six-anomaly fixture only; not a large-data, SQL, or assistive-technology certification.')
        (output/'browser-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
