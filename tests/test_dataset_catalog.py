"""The Zenodo catalog client: request headers, failure handling, validation and caching. No network."""

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.services import dataset_catalog as catalog

RECORD = {
    "doi": "10.5281/zenodo.8196385",
    "metadata": {
        "title": "Loghub: A Large Collection of System Log Datasets",
        "publication_date": "2023-07-31",
    },
    "stats": {"downloads": 230260, "views": 80462},
    "files": [
        {"key": "BGL.zip", "size": 57489019, "checksum": "md5:4452953c470f2d95fcb32d5f6e733f7a"},
        {"key": "Apache.tar.gz", "size": 262905, "checksum": "md5:de9a42d12f9b60612631c67a5a9f8628"},
        {"key": "../escape.zip", "size": 1, "checksum": "md5:00000000000000000000000000000000"},
        {"key": "HDFS_v1.zip", "size": 10, "checksum": "sha1:not-md5"},
    ],
}


class FakeResponse(io.BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status = status


class CatalogTests(unittest.TestCase):
    def setUp(self):
        catalog._cache.clear()
        self.addCleanup(catalog._cache.clear)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.raw = Path(folder.name)
        (self.raw / "BGL.zip").write_bytes(b"x" * 10)

    def test_request_is_json_with_timeout_and_optional_token(self):
        seen = []

        def opener(request, timeout):
            seen.append((request.full_url, dict(request.header_items()), timeout))
            return FakeResponse(json.dumps(RECORD).encode())

        with patch.dict(os.environ, {"ZENODO_TOKEN": ""}):
            catalog.fetch_json(opener=opener)
        with patch.dict(os.environ, {"ZENODO_TOKEN": "synthetic-token-123"}):
            catalog.fetch_json(opener=opener)
        (url, plain, timeout), (_, signed, _) = seen
        self.assertEqual(url, "https://zenodo.org/api/records/8196385")
        self.assertEqual((plain["Accept"], timeout), ("application/json", 10))
        self.assertNotIn("Authorization", plain)
        self.assertEqual(signed["Authorization"], "Bearer synthetic-token-123")
        with (
            patch.dict(os.environ, {"ZENODO_TOKEN": "bad token\r\nX: y"}),
            self.assertRaises(catalog.CatalogUnavailable),
        ):
            catalog.fetch_json(opener=opener)

    def test_network_and_format_failures_become_catalog_unavailable(self):
        def raising(error):
            def opener(request, timeout):
                raise error

            return opener

        failures = [
            raising(HTTPError(catalog.API_URL, 429, "Too Many Requests", {}, None)),
            raising(URLError("offline")),
            raising(TimeoutError()),
            lambda request, timeout: FakeResponse(b"not json"),
            lambda request, timeout: FakeResponse(b"\xff\xfe"),
            lambda request, timeout: FakeResponse(b"[" * (catalog.MAX_BYTES + 2)),
        ]
        for opener in failures:
            with self.subTest(opener=opener), self.assertRaises(catalog.CatalogUnavailable):
                catalog.fetch_json(opener=opener)
        for document in (
            {},
            {"metadata": {"title": 3}, "files": []},
            {"metadata": {"title": "x"}, "files": [{"key": "a.zip", "size": "big"}]},
        ):
            with self.subTest(document=document), self.assertRaises(catalog.CatalogUnavailable):
                catalog.parse(document, self.raw)

    def test_parse_validates_and_compares_with_local_archives(self):
        record = catalog.parse(RECORD, self.raw)
        self.assertEqual([item.name for item in record.files], ["Apache.tar.gz", "BGL.zip", "HDFS_v1.zip"])
        by_name = {item.name: item for item in record.files}
        self.assertEqual(by_name["BGL.zip"].local_state, "different size")
        self.assertEqual(by_name["Apache.tar.gz"].local_state, "missing")
        self.assertEqual(by_name["HDFS_v1.zip"].checksum, "")
        self.assertEqual(
            by_name["BGL.zip"].url, "https://zenodo.org/records/8196385/files/BGL.zip?download=1"
        )
        self.assertEqual(
            (record.doi, record.published, record.downloads), ("10.5281/zenodo.8196385", "2023-07-31", 230260)
        )
        (self.raw / "BGL.zip").write_bytes(b"x" * 57489019)
        self.assertEqual(
            {i.name: i for i in catalog.parse(RECORD, self.raw).files}["BGL.zip"].local_state, "present"
        )

    def test_cache_serves_an_hour_and_refresh_is_throttled(self):
        calls = []

        def fetch():
            calls.append(1)
            return RECORD

        with patch.object(catalog.time, "monotonic", return_value=1000.0):
            first = catalog.loghub_catalog(fetch=fetch, directory=self.raw)
            self.assertIs(catalog.loghub_catalog(fetch=fetch, directory=self.raw, refresh=True), first)
        with patch.object(catalog.time, "monotonic", return_value=1100.0):
            catalog.loghub_catalog(fetch=fetch, directory=self.raw, refresh=True)
        with patch.object(catalog.time, "monotonic", return_value=1100.0 + catalog.CACHE_SECONDS):
            catalog.loghub_catalog(fetch=fetch, directory=self.raw)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
