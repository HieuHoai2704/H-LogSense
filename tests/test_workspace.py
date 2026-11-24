"""The dashboard page and its JSON fragment share one filter state; user text is escaped."""

import unittest

from app import create_app


class WorkspaceTests(unittest.TestCase):
    def test_fragment_and_full_page_share_filter_state(self):
        with create_app().test_client() as client:
            url = "/?host=storage-02&severity=High"
            page = client.get(url)
            fragment = client.get(url, headers={"X-Workspace-Fragment": "1"})
            self.assertEqual(page.status_code, 200)
            self.assertEqual(fragment.status_code, 200)
            self.assertEqual([e["id"] for e in fragment.json["events"]], ["LS-1041"])
            self.assertEqual(page.get_data(as_text=True).count("data-row-id="), 1)

    def test_search_is_escaped(self):
        with create_app().test_client() as client:
            page = client.get("/?q=%3Cscript%3Ealert(1)%3C/script%3E")
            self.assertNotIn("<script>alert(1)</script>", page.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
