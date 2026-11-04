"""Evidence browser checks on synthetic fixtures; no real logs or credentials."""
import json
import logging
from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from app.demo import ANOMALIES
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server


def main():
    root = Path(__file__).resolve().parents[1]
    out = root/'docs/ui/evidence-drawer'
    out.mkdir(parents=True, exist_ok=True)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app = create_app()
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    passed, errors = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            # Test clipboard payload/feedback without modifying the user's OS clipboard.
            context.add_init_script("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.testClipboard=text}}})")
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))

            def ready(rows=None):
                expect(page.locator('#workspace-results')).to_have_attribute('aria-busy', 'false')
                if rows is not None:
                    expect(page.locator('[data-row-id]')).to_have_count(rows)

            def start(query=''):
                page.goto(base+'/'+query, wait_until='networkidle')
                ready()

            def open_record(identity):
                page.get_by_role('button', name=f'Inspect {identity}', exact=True).click()
                expect(page.locator('#detail-content')).to_be_visible()
                expect(page.locator('#detail-title')).to_have_text(identity)

            start('?limit=1')
            original = page.url
            open_record('LS-1042')
            page.locator('#next-anomaly').click()
            expect(page.locator('#detail-title')).to_have_text('LS-1041')
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-actual')).to_have_text('318 events / min')
            expect(page.locator('#detector-evidence')).to_contain_text('Feature schema')
            expect(page.locator('#explanation-status')).to_contain_text('Explanation unavailable')
            page.locator('#detection-heading').scroll_into_view_if_needed()
            page.screenshot(path=str(out/'evidence-ml-details.png'))
            page.locator('#next-anomaly').click()
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-title')).to_have_text('LS-1040')
            page.locator('#previous-anomaly').click()
            expect(page.locator('#detail-title')).to_have_text('LS-1041')
            expect(page.locator('#detail-content')).to_be_visible()
            assert page.url == original
            passed.append('Previous/next navigate entire result scope across table pages without global URL changes')

            expect(page.locator('#detail-related')).to_contain_text('LS-1038')
            expect(page.locator('#detail-related')).to_contain_text('Same host')
            page.locator('#related-heading').scroll_into_view_if_needed()
            page.screenshot(path=str(out/'evidence-related.png'))
            page.locator('#related-window').select_option('60')
            expect(page.locator('#detail-related')).to_contain_text('No related fixture records')
            page.locator('#related-window').select_option('1800')
            expect(page.locator('#detail-related')).to_contain_text('LS-1038')
            passed.append('Related relationship reasons and configurable bounded context update truthfully')

            page.locator('#related-window').select_option('3600')
            page.locator('#related-relation').select_option('before')
            page.locator('#related-limit').select_option('1')
            expect(page.locator('#detail-related [data-related-id]')).to_have_count(1)
            expect(page.locator('#related-next')).to_be_enabled()
            first = page.locator('#detail-related [data-related-id]').get_attribute('data-related-id')
            page.locator('#related-next').click()
            page.wait_for_function('(old) => document.querySelector("#detail-related [data-related-id]")?.dataset.relatedId !== old && document.querySelector("#detail-related [data-related-id]") !== null', arg=first)
            expect(page.locator('#related-previous')).to_be_enabled()
            page.locator('#related-previous').click()
            expect(page.locator('#detail-related [data-related-id]')).to_have_attribute('data-related-id', first)
            passed.append('Related cursor pagination and previous-page navigation')

            page.locator('#copy-evidence-reference').click()
            page.wait_for_function('Boolean(window.testClipboard)')
            copied = page.evaluate('window.testClipboard')
            assert 'anomaly_id=LS-1041' in copied
            page.keyboard.press('Escape')
            page.goto(copied, wait_until='networkidle')
            expect(page.locator('#detail-content')).to_be_visible()
            expect(page.locator('#detail-title')).to_have_text('LS-1041')
            passed.append('Copy reference produces a reloadable source/scoped anomaly deep link (clipboard adapter tested)')

            page.locator('#view-evidence-raw').click()
            expect(page.locator('#detail-raw')).to_be_focused()
            expect(page.locator('#raw-section')).to_have_attribute('open', '')
            page.locator('#copy-raw').click()
            assert '[DEMO]' in page.evaluate('window.testClipboard')
            page.locator('#wrap-raw').uncheck()
            expect(page.locator('#detail-raw')).to_have_class('no-wrap')
            page.locator('#wrap-raw').check()
            page.locator('#raw-section > summary').click()
            expect(page.locator('#detail-raw')).to_be_hidden()
            page.locator('#raw-section > summary').click()
            passed.append('View raw, copy visible chunk, wrapping and expand/collapse')

            with page.expect_download() as download:
                page.locator('#export-evidence').click()
            export = out/'evidence-page.json'
            download.value.save_as(str(export))
            payload = json.loads(export.read_text(encoding='utf-8'))
            assert payload['anomaly']['id'] == 'LS-1041'
            assert payload['export_scope']['type'] == 'current evidence page'
            assert payload['availability']['original_raw_log'] == 'unavailable'
            passed.append('Evidence JSON export identifies the anomaly, current page and missing original source')

            page.locator('#filter-evidence-host').click()
            expect(page.locator('#detail-panel')).to_be_hidden()
            ready(1)
            assert page.evaluate('applied.host') == ['storage-02']
            open_record('LS-1041')
            page.locator('#filter-evidence-service').click()
            ready(1)
            assert page.evaluate('applied.service') == ['storage']
            open_record('LS-1041')
            page.locator('#focus-evidence-range').click()
            expect(page.locator('#detail-panel')).to_be_hidden()
            ready(1)
            assert page.evaluate('applied.range') == 'custom'
            assert page.evaluate('applied.host') == ['storage-02']
            passed.append('Host/service/focus actions work and preserve unrelated global filters')

            start()
            page.locator('[data-cell][data-detector="error-burst"][data-count="1"]').click()
            ready(1)
            open_record('LS-1042')
            expect(page.locator('#evidence-scope')).to_contain_text('Timeline selection')
            page.locator('#detail-panel').evaluate('(e)=>e.scrollTop=0')
            page.screenshot(path=str(out/'evidence-selected-1440.png'))
            expect(page.locator('#next-anomaly')).to_be_disabled()
            page.locator('#export-evidence').focus()
            page.keyboard.press('Tab')
            expect(page.locator('#close-detail')).to_be_focused()
            page.keyboard.press('Shift+Tab')
            expect(page.locator('#export-evidence')).to_be_focused()
            page.keyboard.press('Escape')
            expect(page.locator('.selected-cell')).to_have_count(1)
            expect(page.get_by_role('button', name='Inspect LS-1042', exact=True)).to_be_focused()
            passed.append('Selection visible in drawer, modal focus loop, Escape and opener focus restoration')

            page.route('**/api/v1/anomalies/LS-1042/evidence?*', lambda route: route.abort('failed'))
            open_button = page.get_by_role('button', name='Inspect LS-1042', exact=True)
            open_button.click()
            expect(page.locator('#retry-detail')).to_be_visible()
            expect(page.locator('#detail-content')).to_be_hidden()
            page.unroute('**/api/v1/anomalies/LS-1042/evidence?*')
            page.locator('#retry-detail').click()
            expect(page.locator('#detail-content')).to_be_visible()
            passed.append('Main evidence loading/error/retry does not show stale supporting evidence')
            page.keyboard.press('Escape')

            for width in [1440, 1366, 1024, 390, 1920]:
                page.set_viewport_size({'width': width, 'height': 1000})
                start()
                open_record('LS-1042')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if width in [1440, 1366, 390]:
                    page.locator('#detail-panel').evaluate('(e)=>e.scrollTop=0')
                    page.screenshot(path=str(out/f'evidence-{width}.png'))
                if width == 1920:
                    expect(page.locator('#detail-panel')).to_have_attribute('role', 'region')
                    assert not page.locator('.app-shell').evaluate('(e)=>e.inert')
                else:
                    expect(page.locator('#detail-panel')).to_have_attribute('aria-modal', 'true')
                page.keyboard.press('Escape')
            passed.append('Right drawer at 1440/1366/1024, full-width mobile, nonmodal wide desktop and no document overflow')

            # Malformed and credential-bearing data are deliberate test fixtures only.
            message = 'Kernel <img src=x onerror=window.badLog=true> password=never-expose email=tester@example.com'
            long_raw = message+' '+('kernel '+('x'*200)+'\n')*35
            sample = dict(ANOMALIES[0], message=message, raw_log=long_raw)
            with patch('app.services.investigation.ANOMALIES', [sample]):
                page.set_viewport_size({'width': 1440, 'height': 1000})
                start('?q=Kernel')
                open_record('LS-1042')
                expect(page.locator('#detail-raw mark')).not_to_have_count(0)
                assert page.locator('#detail-raw img').count() == 0
                assert page.evaluate('window.badLog') is None
                assert 'never-expose' not in page.locator('#detail-panel').inner_text()
                assert 'tester@example.com' not in page.locator('#detail-panel').inner_text()
                expect(page.locator('#raw-next')).to_be_enabled()
                page.locator('#raw-next').click()
                expect(page.locator('#raw-previous')).to_be_enabled()
                page.locator('#raw-previous').click()
                expect(page.locator('#raw-previous')).to_be_disabled()
                page.locator('#view-evidence-raw').click()
                page.screenshot(path=str(out/'evidence-safe-raw.png'))
                passed.append('HTML stays text; matched terms marked safely, secrets/email redacted and long raw chunk paging')

                page.route('**/api/v1/anomalies/LS-1042/evidence/raw?*', lambda route: route.abort('failed'))
                page.locator('#raw-next').click()
                expect(page.locator('#raw-retry')).to_be_visible()
                page.unroute('**/api/v1/anomalies/LS-1042/evidence/raw?*')
                page.locator('#raw-retry').click()
                expect(page.locator('#raw-retry')).to_be_hidden()
                page.keyboard.press('Escape')
                passed.append('Independent raw-page error/retry')

            start()
            open_record('LS-1041')
            page.route('**/api/v1/anomalies/LS-1041/related?*', lambda route: route.abort('failed'))
            page.locator('#related-window').select_option('60')
            expect(page.locator('#related-retry')).to_be_visible()
            expect(page.locator('#detail-related [data-related-id]')).to_have_count(0)
            page.unroute('**/api/v1/anomalies/LS-1041/related?*')
            page.locator('#related-retry').click()
            expect(page.locator('#related-retry')).to_be_hidden()
            passed.append('Independent related-query error/retry clears mismatched old relationship rows')
            assert not errors, errors
            browser.close()
        report = dict(passed=passed, count=len(passed), page_errors=errors,
                      limits='Synthetic records only. Clipboard uses a browser test adapter. No real MySQL, raw ingestion, login provider or screen-reader certification.')
        (out/'browser-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
