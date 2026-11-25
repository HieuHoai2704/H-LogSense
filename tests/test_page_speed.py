"""Faster page changes: versioned static files cached by the browser, report caching, page transitions."""

import os
from pathlib import Path
import re
import unittest

from app import create_app
from app.services import report_cache

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


class StaticVersionTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def test_static_urls_carry_a_version_and_are_cached(self):
        page = self.client.get("/?source=demo").get_data(as_text=True)
        urls = re.findall(r'(?:href|src)="(/static/[^"]+)"', page)
        self.assertTrue(urls)
        self.assertTrue(all(re.search(r"\?v=[0-9a-f]+$", url) for url in urls), urls)
        versioned = self.client.get(urls[0])
        self.assertEqual(versioned.status_code, 200)
        self.assertEqual(versioned.headers["Cache-Control"], "public, max-age=31536000")
        # Without a version the browser keeps checking for a newer file.
        self.assertEqual(self.client.get(urls[0].split("?")[0]).headers["Cache-Control"], "no-cache")

    def test_editing_a_file_changes_its_url(self):
        app = create_app({"TESTING": True})
        with app.test_request_context():
            from flask import url_for

            first = url_for("static", filename="css/quality.css")
            path = STATIC / "css" / "quality.css"
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            try:
                self.assertNotEqual(url_for("static", filename="css/quality.css"), first)
            finally:
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    def test_pages_cross_fade_and_keep_the_bars_in_place(self):
        css = (STATIC / "workspace" / "navigation.css").read_text(encoding="utf-8")
        self.assertIn("@view-transition { navigation: auto; }", css)
        self.assertIn("view-transition-name: workspace-nav", css)
        self.assertIn("view-transition-name: analysis-menu", css)
        self.assertRegex(
            css, r"prefers-reduced-motion: reduce\)\s*\{\s*@view-transition \{ navigation: none; \}"
        )
        # The popup terminal finds the stylesheets although their URLs now end in ?v=.
        terminal = (STATIC / "workspace" / "terminal.js").read_text(encoding="utf-8")
        self.assertNotIn('link[href$="', terminal)


class ReportCacheTests(unittest.TestCase):
    def setUp(self):
        report_cache.clear()
        self.addCleanup(report_cache.clear)

    def test_computes_once_per_key_and_hands_out_copies(self):
        calls = []

        def compute():
            calls.append(1)
            return {"rows": [1, 2]}

        first = report_cache.cached(("quality", 1, 7), compute)
        first["rows"].append(3)  # a caller changing its copy never edits the cache
        self.assertEqual(report_cache.cached(("quality", 1, 7), compute), {"rows": [1, 2]})
        self.assertEqual(len(calls), 1)
        report_cache.cached(("quality", 1, 8), compute)  # a new data version recomputes
        self.assertEqual(len(calls), 2)

    def test_least_recently_used_entries_are_dropped(self):
        for number in range(report_cache.SIZE + 5):
            report_cache.cached(("k", number), lambda number=number: number)
        calls = []
        report_cache.cached(("k", 0), lambda: calls.append(1) or 0)
        self.assertEqual(calls, [1])  # the oldest entry was evicted
        report_cache.cached(("k", report_cache.SIZE + 4), lambda: calls.append(1))
        self.assertEqual(calls, [1])  # the newest is still cached


if __name__ == "__main__":
    unittest.main()
