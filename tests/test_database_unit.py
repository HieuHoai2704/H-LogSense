import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models import UTCDateTime


class DatabaseUnitTests(unittest.TestCase):
    def test_demo_database_optional(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app()
            self.assertEqual(app.test_client().get("/").status_code, 200)
            self.assertEqual(
                app.test_client().get("/api/v1/health/database").json,
                {"status": "not_configured"},
            )

    def test_testing_never_falls_back_to_development(self):
        with patch.dict(os.environ, {"DATABASE_URL": "invalid"}, clear=True):
            app = create_app({"TESTING": True})
            self.assertNotIn("sqlalchemy", app.extensions)

    def test_forbids_sqlite(self):
        with self.assertRaises(ValueError):
            create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    def test_invalid_url_error_redacted(self):
        with self.assertRaisesRegex(ValueError, "^A valid mysql"):
            create_app({"SQLALCHEMY_DATABASE_URI": "not-a-url:private-value"})

    def test_utc_type(self):
        kind = UTCDateTime()
        local = datetime(2026, 11, 4, 7, tzinfo=timezone(timedelta(hours=7)))
        self.assertEqual(kind.process_bind_param(local, None), datetime(2026, 11, 4))
        self.assertEqual(
            kind.process_result_value(datetime(2026, 11, 4), None).tzinfo, timezone.utc
        )
        with self.assertRaises(ValueError):
            kind.process_bind_param(datetime(2026, 11, 4), None)

    def test_constraint_names_unique_per_table(self):
        create_app({"TESTING": True})
        for table in db.metadata.tables.values():
            names = [c.name for c in table.constraints if c.name]
            self.assertEqual(len(names), len(set(names)), table.name)

    def test_private_api_disabled_without_token(self):
        app = create_app({"TESTING": True})
        self.assertEqual(
            app.test_client()
            .get("/api/v1/database/anomalies?dataset_id=1&run_id=1")
            .status_code,
            403,
        )

    def test_native_scores_finite_negative_allowed(self):
        from app.models import AnomalyOutput

        self.assertEqual(AnomalyOutput(score=-0.6).score, -0.6)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                AnomalyOutput(score=value)

    def test_authorized_operator_without_database_is_503(self):
        with patch.dict(os.environ, {}, clear=True):
            app = create_app(
                {
                    "DATABASE_READ_TOKEN": "synthetic-operator-token",
                    "DATABASE_ALLOWED_DATASETS": (1,),
                }
            )
            headers = {"Authorization": "Bearer synthetic-operator-token"}
            self.assertEqual(
                app.test_client()
                .get("/api/v1/logs/datasets", headers=headers)
                .status_code,
                503,
            )
            self.assertEqual(
                app.test_client().get("/?source=db-1", headers=headers).status_code, 503
            )

    def test_csv_formulas_and_native_negative_score(self):
        from app.services.csv_safety import safe_cell

        for text in (
            "=1+1",
            "+SUM(A1)",
            "-cmd",
            "@SUM(A1)",
            "  =1+1",
            "\ufeff=1+1",
            "\t=1+1",
        ):
            self.assertTrue(safe_cell(text).startswith("'"))
        self.assertEqual(safe_cell(-0.75), -0.75)
        self.assertEqual(safe_cell(None), "")
