"""Authenticated Python client for the existing LogSense JSON API."""

import argparse
import csv
from getpass import getpass
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import requests


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class LogSenseClient:
    def __init__(self, base_url):
        url = urlsplit(base_url.strip())
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or url.path not in {"", "/"}
            or url.query
            or url.fragment
        ):
            raise ApiError("Enter the server origin, for example http://127.0.0.1:5000.")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ApiError("Remote log servers require HTTPS.")
        self.base = url.geturl().rstrip("/")
        self.session = requests.Session()
        self.csrf = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.session.close()

    def request(self, method, path, **options):
        headers = {"Accept": "application/json"}
        if self.csrf and method != "GET":
            headers["X-CSRF-Token"] = self.csrf
        try:
            response = self.session.request(
                method,
                self.base + "/api/v1/" + path,
                headers=headers,
                timeout=(4, 45),
                allow_redirects=False,
                **options,
            )
        except requests.RequestException as error:
            raise ApiError(f"Network request failed ({type(error).__name__}).") from error
        with response:
            if response.status_code == 204:
                return None
            try:
                data = response.json()
            except ValueError:
                raise ApiError(
                    f"Expected a JSON response (HTTP {response.status_code}).", response.status_code
                ) from None
            if not 200 <= response.status_code < 300:
                detail = data.get("error", {}) if isinstance(data, dict) else {}
                if not isinstance(detail, dict):
                    detail = {}
                message = detail.get("message") or detail.get("code") or "Request rejected."
                raise ApiError(f"HTTP {response.status_code}: {message}", response.status_code)
            return data

    def login(self, username, password):
        self.session.cookies.clear()
        self.csrf = None
        result = self.request("POST", "auth/login", json={"username": username, "password": password})
        self.csrf = result["csrf_token"]
        return result["user"]

    def datasets(self):
        return self.request("GET", "datasets", params={"limit": 100})["items"]

    def dataset(self, dataset_id):
        return self.request("GET", f"datasets/{dataset_id}")["dataset"]

    def create_dataset(self, name, key, mode="unverified"):
        return self.request(
            "POST",
            "datasets",
            json={
                "name": name,
                "dataset_key": key,
                "data_mode": mode,
            },
        )["dataset"]

    def rename_dataset(self, dataset_id, name):
        return self.request("PATCH", f"datasets/{dataset_id}", json={"name": name})["dataset"]

    def delete_dataset(self, dataset_id):
        self.request("DELETE", f"datasets/{dataset_id}")

    def log_range(self, dataset_id):
        entries = self.request("GET", "logs/datasets")["datasets"]
        return next((row for row in entries if row["id"] == dataset_id), None)

    def logs(self, dataset_id, start, end, *, limit=25, sort="desc", q=""):
        return self.request(
            "GET",
            "logs",
            params={
                "dataset_id": dataset_id,
                "start_time": start,
                "end_time": end,
                "limit": limit,
                "sort": sort,
                "q": q,
            },
        )

    def upload(self, dataset_id, filename, reference=None):
        path = Path(filename)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ApiError("Select a file of at most 16 MiB.")
        token = self.request("GET", "forms/csrf")["csrf_token"]
        with path.open("rb") as handle:
            return self.request(
                "POST",
                "uploads",
                data={
                    "dataset_id": dataset_id,
                    "csrf_token": token,
                    "idempotency_key": reference or uuid4().hex,
                },
                files={"file": (path.name, handle)},
            )

    def upload_status(self, upload_id):
        return self.request("GET", f"uploads/{upload_id}")


def write_log_csv(destination, rows):
    fields = ("id", "timestamp", "host", "service", "severity", "message")
    with Path(destination).open("x", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = {}
            for key in fields:
                value = row.get(key)
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                values[key] = value
            writer.writerow(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--dataset", type=int)
    parser.add_argument("--csv", type=Path, help="Save up to 100 log rows in a new file.")
    args = parser.parse_args()
    if args.csv and args.dataset is None:
        parser.error("--csv requires --dataset")
    try:
        with LogSenseClient(args.url) as client:
            client.login(args.username, getpass("LogSense password: "))
            if args.dataset is None:
                print(json.dumps(client.datasets(), ensure_ascii=False, indent=2))
                return
            date_range = client.log_range(args.dataset)
            if not date_range or not date_range["start_time"]:
                raise ApiError("This dataset has no imported logs available.")
            page = client.logs(args.dataset, date_range["start_time"], date_range["end_time"], limit=100)
            if args.csv:
                write_log_csv(args.csv, page["items"])
            print(
                json.dumps(
                    {
                        "dataset": args.dataset,
                        "total_in_scope": page["count"],
                        "rows_fetched": len(page["items"]),
                        "csv": str(args.csv) if args.csv else None,
                    }
                )
            )
    except (ApiError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
