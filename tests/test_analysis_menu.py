"""The Analysis function menu replaces the folder tree on every Analysis page."""

from html.parser import HTMLParser
import unittest

from app import create_app


class MenuEntries(HTMLParser):
    """Collect the menu's links and planned (not yet built) entries."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.links = {}
        self.planned = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "aside" and attrs.get("id") == "analysis-menu":
            self.depth = 1
        elif self.depth:
            self.depth += tag not in {"path", "rect", "circle", "ellipse"}
            key = attrs.get("data-menu-item")
            if key and tag == "a":
                self.links[key] = attrs["href"]
                if attrs.get("aria-current") == "page":
                    self.current.append(key)
            elif key:
                self.planned.append(key)

    def handle_endtag(self, tag):
        if self.depth and tag not in {"path", "rect", "circle", "ellipse"}:
            self.depth -= 1


def menu(html: bytes) -> MenuEntries:
    parser = MenuEntries()
    parser.feed(html.decode())
    return parser


class AnalysisMenuTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def test_investigation_page_shows_the_menu_instead_of_the_folder_tree(self):
        page = self.client.get("/?source=demo")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'id="local-tree"', page.data)
        self.assertNotIn(b'id="external-preview"', page.data)
        entries = menu(page.data)
        self.assertEqual(
            list(entries.links),
            ["overview", "logs", "investigation", "alerts", "quality", "pipeline", "datasets", "catalog"],
        )
        self.assertEqual(entries.planned, ["schedule"])
        self.assertEqual(entries.current, ["investigation"])
        # Without a database the investigation entry opens the synthetic workspace.
        self.assertEqual(entries.links["investigation"], "/?source=demo")
        self.assertEqual(entries.links["logs"], "/?workspace=logs")
        self.assertEqual(entries.links["alerts"], "/?workspace=logs#incident-workspace")
        self.assertEqual(entries.links["overview"], "/analysis/overview")
        self.assertEqual(entries.links["quality"], "/analysis/quality")
        self.assertEqual(entries.links["pipeline"], "/analysis/pipeline")
        self.assertEqual(entries.links["datasets"], "/manage/datasets")
        self.assertEqual(entries.links["catalog"], "/manage/datasets/catalog")

    def test_log_explorer_marks_its_entry_and_keeps_no_folder_tree(self):
        page = self.client.get("/?workspace=logs")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(menu(page.data).current, ["logs"])
        self.assertNotIn(b'id="local-tree"', page.data)
        self.assertIn(b'id="incident-workspace"', page.data)

    def test_menu_is_translated(self):
        self.client.post("/preferences/language", data={"language": "vi", "next": "/"})
        page = self.client.get("/?source=demo").get_data(as_text=True)
        for text in (
            "Chức năng phân tích",
            "Điều tra bất thường",
            "Chất lượng dữ liệu",
            "Pipeline &amp; job",
            "Sắp có",
        ):
            self.assertIn(text, page)

    def test_project_page_keeps_the_folder_tree(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'id="analysis-menu"', page.data)


if __name__ == "__main__":
    unittest.main()
