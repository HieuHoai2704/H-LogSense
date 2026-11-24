"""The public Loghub dataset catalog, read from the Zenodo REST API with ``urllib``.

``GET https://zenodo.org/api/records/8196385`` returns the record's metadata and file list as JSON. The
response is validated field by field, kept for an hour, and compared with the archives already in
``data/raw`` so an operator can see which datasets are available locally. An optional ``ZENODO_TOKEN``
(a Zenodo personal access token) is sent as a bearer token for higher rate limits.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RECORD_ID = 8196385
API_URL = f"https://zenodo.org/api/records/{RECORD_ID}"
TIMEOUT = 10  # seconds
MAX_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 3600
MIN_REFRESH_SECONDS = 60
RAW_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "raw"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
CHECKSUM = re.compile(r"md5:[0-9a-f]{32}\Z")


class CatalogUnavailable(Exception):
    """The catalog could not be fetched or did not have the expected shape."""


@dataclass(frozen=True)
class CatalogFile:
    name: str
    size: int
    checksum: str
    url: str
    local_size: int | None

    @property
    def local_state(self):
        if self.local_size is None:
            return "missing"
        return "present" if self.local_size == self.size else "different size"


@dataclass(frozen=True)
class Catalog:
    title: str
    doi: str
    published: str
    downloads: int
    views: int
    files: tuple[CatalogFile, ...]
    fetched_at: datetime

    @property
    def total_size(self):
        return sum(item.size for item in self.files)


_cache: dict[str, object] = {}
_lock = threading.Lock()


def fetch_json(url=API_URL, opener=urlopen):
    headers = {"Accept": "application/json", "User-Agent": "H-logsen dataset catalog"}
    token = os.environ.get("ZENODO_TOKEN", "").strip()
    if token:
        if not re.fullmatch(r"[A-Za-z0-9._-]{8,200}", token):
            raise CatalogUnavailable("ZENODO_TOKEN has an invalid format.")
        headers["Authorization"] = "Bearer " + token
    try:
        with opener(Request(url, headers=headers), timeout=TIMEOUT) as response:
            if response.status != 200:
                raise CatalogUnavailable(f"Zenodo answered HTTP {response.status}.")
            body = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        raise CatalogUnavailable(f"Zenodo answered HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise CatalogUnavailable("Zenodo could not be reached. Check the network connection.") from None
    if len(body) > MAX_BYTES:
        raise CatalogUnavailable("The catalog response is too large.")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise CatalogUnavailable("The catalog response is not valid JSON.") from None


def local_size(name, directory):
    path = directory / name
    try:
        return path.stat().st_size if path.is_file() else None
    except OSError:
        return None


def parse(document, directory=RAW_DIRECTORY):
    """Validate the Zenodo record; nothing outside the expected shape reaches a template."""
    try:
        metadata = document["metadata"]
        title = metadata["title"]
        doi = document.get("doi") or ""
        published = metadata.get("publication_date") or ""
        stats = document.get("stats") or {}
        downloads, views = int(stats.get("downloads", 0)), int(stats.get("views", 0))
        entries = document["files"]
        if not isinstance(title, str) or not isinstance(entries, list) or len(entries) > 500:
            raise TypeError
        files = []
        for entry in entries:
            name, size, checksum = entry["key"], entry["size"], entry.get("checksum", "")
            if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
                continue  # never shown, never joined to a local path
            if not isinstance(size, int) or size < 0 or not isinstance(checksum, str):
                raise TypeError
            files.append(
                CatalogFile(
                    name=name,
                    size=size,
                    checksum=checksum if CHECKSUM.fullmatch(checksum) else "",
                    url=f"https://zenodo.org/records/{RECORD_ID}/files/{name}?download=1",
                    local_size=local_size(name, directory),
                )
            )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise CatalogUnavailable("The catalog response has an unexpected format.") from None
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", published):
        published = ""
    if not re.fullmatch(r"10\.[0-9]{4,9}/[A-Za-z0-9._/-]{1,100}", doi):
        doi = ""
    return Catalog(
        title=title[:300],
        doi=doi,
        published=published,
        downloads=max(downloads, 0),
        views=max(views, 0),
        files=tuple(sorted(files, key=lambda item: item.name.lower())),
        fetched_at=datetime.now(timezone.utc),
    )


def loghub_catalog(*, refresh=False, fetch=fetch_json, directory=RAW_DIRECTORY):
    """The cached catalog; ``refresh`` re-reads it at most once a minute."""
    with _lock:
        cached = _cache.get("catalog")
        age = time.monotonic() - float(_cache.get("at", 0.0))  # type: ignore[arg-type,unused-ignore]
        if cached is not None and (age < CACHE_SECONDS and not (refresh and age >= MIN_REFRESH_SECONDS)):
            return cached
        catalog = parse(fetch(), directory)
        _cache.update(catalog=catalog, at=time.monotonic())
        return catalog
