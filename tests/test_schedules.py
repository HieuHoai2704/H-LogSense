"""Schedules without a database: the next slot after a missed run, the form rules and the page guard."""

from datetime import datetime, timedelta, timezone
import unittest

from app import create_app
from app.services.schedules import next_after

DUE = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)


class ScheduleTests(unittest.TestCase):
    def test_next_slot_stays_on_the_grid_without_a_burst_of_catch_up_runs(self):
        self.assertEqual(next_after(DUE, 60, DUE), DUE + timedelta(hours=1))
        self.assertEqual(next_after(DUE, 60, DUE + timedelta(minutes=5)), DUE + timedelta(hours=1))
        # A worker stopped for 5.5 hours runs once, then continues on the hour grid.
        self.assertEqual(next_after(DUE, 60, DUE + timedelta(hours=5, minutes=30)), DUE + timedelta(hours=6))
        self.assertEqual(next_after(DUE + timedelta(hours=1), 15, DUE), DUE + timedelta(hours=1))

    def test_form_requires_lines_only_for_imports(self):
        from app.forms import ScheduleForm

        app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
        with app.test_request_context(
            method="POST",
            data={"name": "Import", "task": "import", "interval_minutes": "60", "import_lines": ""},
        ):
            form = ScheduleForm(meta={"csrf": False})
            self.assertFalse(form.validate())
            self.assertIn("import_lines", form.errors)
        with app.test_request_context(
            method="POST",
            data={"name": "Import", "task": "import", "interval_minutes": "60", "import_lines": "50"},
        ):
            self.assertFalse(ScheduleForm(meta={"csrf": False}).validate())  # below 100 lines
        with app.test_request_context(
            method="POST", data={"name": "Rules", "task": "rule", "interval_minutes": "60"}
        ):
            self.assertTrue(ScheduleForm(meta={"csrf": False}).validate())
        with app.test_request_context(
            method="POST", data={"name": "Odd", "task": "rule", "interval_minutes": "7"}
        ):
            self.assertFalse(ScheduleForm(meta={"csrf": False}).validate())

    def test_page_needs_the_database(self):
        client = create_app({"TESTING": True}).test_client()
        page = client.get("/analysis/schedules")
        self.assertEqual(page.status_code, 503)
        self.assertIn(b"Schedules need the MySQL database.", page.data)


if __name__ == "__main__":
    unittest.main()
