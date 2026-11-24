"""Source and anomaly identities shared by the API, services and the browser."""

import unittest

from app.contracts import (
    MAX_ID,
    QueryError,
    anomaly_id_of,
    anomaly_identity,
    dataset_id_of,
    dataset_source,
    is_dataset_source,
)
from app.services import investigation


class IdentityTest(unittest.TestCase):
    def test_dataset_sources_round_trip(self):
        for dataset_id in (1, 42, MAX_ID):
            source = dataset_source(dataset_id)
            self.assertTrue(is_dataset_source(source))
            self.assertEqual(dataset_id_of(source), dataset_id)
        self.assertFalse(is_dataset_source("demo"))

    def test_anomaly_identities_round_trip(self):
        for anomaly_id in (1, 7, MAX_ID):
            self.assertEqual(anomaly_id_of(anomaly_identity(anomaly_id)), anomaly_id)

    def test_malformed_identities_are_client_errors(self):
        # Signs, spaces, non-ASCII digits and out-of-range ids never reach an int() call or the database.
        for source in ("demo", "db-", "db-0", "db--1", "db-+1", "db- 1", "db-1x", "db-١", f"db-{MAX_ID + 1}"):
            with self.subTest(source=source), self.assertRaises(QueryError):
                dataset_id_of(source)
        for identity in ("LS-1042", "DB-", "DB-0", "db-1", "DB-1.5", f"DB-{MAX_ID + 1}"):
            with self.subTest(identity=identity), self.assertRaises(QueryError):
                anomaly_id_of(identity)

    def test_query_error_keeps_its_import_path(self):
        self.assertIs(investigation.QueryError, QueryError)


if __name__ == "__main__":
    unittest.main()
