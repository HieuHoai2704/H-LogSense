"""Schedules on real MySQL: the page and its forms (CSRF), access, and the worker running due schedules."""

from datetime import timedelta
import io
import os
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
import test_mysql_integration as baseline
import test_platform_mysql as platform

from app.domain import JobSchedule
from app.models import LogEvent, ProcessingJob

GRANT_HOST = os.environ.get("MYSQL_GRANT_HOST", "localhost")


def csrf(page, name):
    match = re.search(rf'name="{re.escape(name)}" type="hidden" value="([^"]+)"', page)
    assert match, f"no {name} on the page"
    return match.group(1)


@unittest.skipUnless(
    os.environ.get("LOGSENSE_RUN_MYSQL_TESTS") == "1",
    "Schedules MySQL integration NOT RUN",
)
class ScheduleMySQLTests(unittest.TestCase):
    setUp = platform.PlatformMySQLTests.setUp
    tearDown = platform.PlatformMySQLTests.tearDown
    login = platform.PlatformMySQLTests.login
    event = platform.PlatformMySQLTests.event

    @classmethod
    def setUpClass(cls):
        platform.PlatformMySQLTests.setUpClass.__func__(cls)
        url = cls.engine.url
        if not re.fullmatch(r"logsense_test_[0-9a-f]{12}", url.database or "") or not re.fullmatch(
            r"[A-Za-z0-9_.%-]+", GRANT_HOST
        ):
            raise RuntimeError("Refusing privilege changes outside the owned test schema")
        # Deleting a schedule needs the table-level grant the demo and runtime tools give the app account.
        admin = create_engine(make_url(os.environ["MYSQL_ADMIN_URL"]), hide_parameters=True)
        try:
            with admin.begin() as connection:
                connection.execute(
                    text(
                        f"GRANT DELETE ON `{url.database}`.`job_schedules` TO '{url.username}'@'{GRANT_HOST}'"
                    )
                )
        finally:
            admin.dispose()
        cls.engine.dispose()

    def page(self, path=None):
        response = self.client.get(path or f"/analysis/schedules?dataset_id={self.dataset_id}")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def create(self, **fields):
        html = self.page()
        data = {
            "schedule-csrf_token": csrf(html, "schedule-csrf_token"),
            "schedule-name": "Hourly rules",
            "schedule-task": "rule",
            "schedule-interval_minutes": "60",
            "schedule-import_lines": "10000",
            "schedule-enabled": "y",
            **{"schedule-" + key: value for key, value in fields.items()},
        }
        return self.client.post(f"/analysis/schedules?dataset_id={self.dataset_id}", data=data)

    def schedule(self, name):
        with Session(self.engine) as session:
            return session.scalar(
                select(JobSchedule).where(JobSchedule.dataset_id == self.dataset_id, JobSchedule.name == name)
            )

    def act(self, schedule_id, verb):
        # Flask-WTF signs one session token; the create form's copy is valid for the action forms too.
        token = csrf(self.page(), "schedule-csrf_token")
        return self.client.post(f"/analysis/schedules/{schedule_id}/{verb}", data={"csrf_token": token})

    def fail_queued(self):
        # The schema is shared: another suite's worker takes the oldest queued job.
        with Session(self.engine) as session, session.begin():
            for job in session.scalars(
                select(ProcessingJob).where(ProcessingJob.dataset_id == self.dataset_id)
            ):
                if job.state == "queued":
                    job.state, job.error_code = "failed", "analysis_failed"

    def test_crud_and_worker_queues_a_due_detector_run(self):
        from app.services.schedules import run_due, utcnow

        self.addCleanup(self.fail_queued)
        self.login("staff")
        created = self.create()
        self.assertEqual(created.status_code, 303, created.get_data(as_text=True)[:500])
        schedule = self.schedule("Hourly rules")
        self.assertEqual(
            (schedule.task, schedule.interval_minutes, schedule.import_lines), ("rule", 60, None)
        )
        self.assertIn("Hourly rules", self.page())
        # The same name twice is refused with a message, not a server error.
        self.assertEqual(self.create().status_code, 400)
        # Without the form's CSRF token nothing changes.
        self.assertEqual(self.client.post(f"/analysis/schedules/{schedule.id}/toggle").status_code, 400)

        now = utcnow() + timedelta(seconds=1)
        self.assertEqual(run_due(self.engine, now), 1)
        after = self.schedule("Hourly rules")
        self.assertEqual(after.next_run_at, schedule.next_run_at + timedelta(hours=1))
        with Session(self.engine) as session:
            job = session.get(ProcessingJob, after.last_job_id)
            self.assertEqual((job.kind, job.state, job.dataset_id), ("analysis", "queued", self.dataset_id))
            self.assertEqual(job.configuration, {"detector": "rule", "window_seconds": 300, "seed": 42})
        self.assertEqual(run_due(self.engine, now), 0)  # not due again until the next hour

        self.assertEqual(self.act(schedule.id, "toggle").status_code, 303)
        self.assertFalse(self.schedule("Hourly rules").enabled)
        self.assertEqual(run_due(self.engine, now + timedelta(hours=2)), 0)  # paused
        self.assertEqual(self.act(schedule.id, "run").status_code, 303)
        resumed = self.schedule("Hourly rules")
        self.assertTrue(resumed.enabled)
        self.assertLessEqual(resumed.next_run_at, utcnow())

        edit = self.client.get(f"/analysis/schedules/{schedule.id}/edit")
        self.assertEqual(edit.status_code, 200)
        html = edit.get_data(as_text=True)
        saved = self.client.post(
            f"/analysis/schedules/{schedule.id}/edit",
            data={
                "schedule-csrf_token": csrf(html, "schedule-csrf_token"),
                "schedule-name": "Daily forest",
                "schedule-task": "isolation_forest",
                "schedule-interval_minutes": "1440",
                "schedule-enabled": "y",
            },
        )
        self.assertEqual(saved.status_code, 303)
        self.assertEqual(self.schedule("Daily forest").task, "isolation_forest")

        self.assertEqual(self.act(schedule.id, "delete").status_code, 303)
        self.assertIsNone(self.schedule("Daily forest"))

    def test_other_datasets_and_signed_out_requests_are_refused(self):
        with Session(self.engine) as session, session.begin():
            foreign = JobSchedule(dataset_id=self.other_id, name="Foreign", task="rule", interval_minutes=60)
            session.add(foreign)
            session.flush()
            foreign_id = foreign.id
        self.addCleanup(self.drop, foreign_id)
        self.assertEqual(self.client.get("/analysis/schedules").status_code, 302)  # sign-in first
        self.login("staff")
        self.assertEqual(self.client.get(f"/analysis/schedules/{foreign_id}/edit").status_code, 404)
        token = csrf(self.page(), "schedule-csrf_token")
        self.assertEqual(
            self.client.post(
                f"/analysis/schedules/{foreign_id}/delete", data={"csrf_token": token}
            ).status_code,
            404,
        )
        self.assertNotIn("Foreign", self.page())

    def drop(self, schedule_id):
        with Session(self.engine) as session, session.begin():
            schedule = session.get(JobSchedule, schedule_id)
            if schedule is not None:
                session.delete(schedule)

    def test_import_schedule_reads_the_next_lines_of_the_archive(self):
        from app.services.schedules import run_due, utcnow

        self.login("staff")
        lines = b"".join(baseline.LINE.replace(b"example", f"line {n}".encode()) for n in range(150))
        with TemporaryDirectory() as folder:
            archive = os.path.join(folder, "BGL.zip")
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as zipped:
                zipped.writestr("BGL.log", lines)
            with open(archive, "wb") as output:
                output.write(buffer.getvalue())
            self.assertEqual(self.create(name="Import", task="import", import_lines="100").status_code, 303)
            with patch.dict(os.environ, {"LOGSENSE_BGL_ARCHIVE": archive}):
                self.assertEqual(run_due(self.engine, utcnow() + timedelta(seconds=1)), 1)
                schedule = self.schedule("Import")
                self.assertIsNone(schedule.last_error)
                with Session(self.engine) as session:
                    count = session.scalar(select(func.count()).where(LogEvent.dataset_id == self.dataset_id))
                    self.assertEqual(count, 100)
                    self.assertEqual(session.get(ProcessingJob, schedule.last_job_id).kind, "ingestion")
                # The next run continues from the checkpoint.
                self.assertEqual(run_due(self.engine, utcnow() + timedelta(hours=1, seconds=2)), 1)
                with Session(self.engine) as session:
                    count = session.scalar(select(func.count()).where(LogEvent.dataset_id == self.dataset_id))
                    self.assertEqual(count, 150)
        # A dataset holding another source refuses import schedules.
        with Session(self.engine) as session, session.begin():
            self.event(session)  # adds an artifact with a random key
        refused = self.create(name="Import again", task="import", import_lines="100")
        self.assertEqual(refused.status_code, 400)


if __name__ == "__main__":
    unittest.main()
