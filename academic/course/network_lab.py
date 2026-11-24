"""Save evidence for the seven networking exercises using the live LogSense API."""

import argparse
import csv
from getpass import getpass
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import requests

from scripts.run.logsense_client import ApiError, LogSenseClient, write_log_csv


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == "img" and (source := dict(attrs).get("src")):
            self.urls.add(source)


def download_images(page_url, destination, *, image_origins=()):
    with urlopen(page_url, timeout=20) as response:
        document_url = response.geturl()
        page = response.read(2_000_000).decode("utf-8", errors="replace")
    parser = Images()
    parser.feed(page)
    document_origin = urlsplit(document_url)
    allowed_origins = {document_origin.netloc, *image_origins}
    allowed = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    saved = []
    for source in sorted(parser.urls)[:30]:
        target = urljoin(document_url, source)
        parsed = urlsplit(target)
        if parsed.scheme != "https" or parsed.netloc not in allowed_origins:
            continue
        with urlopen(target, timeout=20) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.netloc not in allowed_origins:
                continue
            extension = allowed.get(response.headers.get_content_type())
            body = response.read(2_000_001)
        if extension and len(body) <= 2_000_000:
            filename = f"04-image-{len(saved) + 1:02d}{extension}"
            (destination / filename).write_bytes(body)
            saved.append({"source": target, "file": filename, "bytes": len(body)})
    return saved


def text_to_csv(url, destination):
    with urlopen(url, timeout=20) as response:
        lines = response.read(1_000_000).decode("utf-8", errors="replace").splitlines()
    with destination.open("x", newline="", encoding="utf-8-sig") as output:
        writer = csv.writer(output)
        writer.writerow(("line_number", "text"))
        for index, line in enumerate(lines, 1):
            if line.lstrip().startswith(("=", "+", "-", "@")):
                line = "'" + line
            writer.writerow((index, line))
    return len(lines)


def youtube_statistics(ids, api_key, destination):
    try:
        response = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            timeout=(5, 20),
            params={"part": "statistics", "id": ",".join(ids), "key": api_key},
        )
    except requests.RequestException as error:
        raise ApiError(f"YouTube request failed ({type(error).__name__}).") from None
    with response:
        if response.status_code != 200:
            raise ApiError(f"YouTube returned HTTP {response.status_code}.")
        items = response.json()["items"]
    fields = ("videoid", "viewCount", "likeCount", "dislikeCount", "favoriteCount", "commentCount")
    with destination.open("x", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {"videoid": item["id"], **{field: item["statistics"].get(field, "") for field in fields[1:]}}
            )
    return len(items)


def nasa_dates(destination):
    """The official public API key can read real APOD entries by date."""
    fields = ("date", "title", "media_type")
    try:
        response = requests.get(
            "https://api.nasa.gov/planetary/apod",
            timeout=(5, 20),
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-03",
                "api_key": os.environ.get("NASA_API_KEY") or "DEMO_KEY",
            },
        )
    except requests.RequestException as error:
        raise ApiError(f"NASA request failed ({type(error).__name__}).") from None
    with response:
        if response.status_code != 200:
            raise ApiError(f"NASA returned HTTP {response.status_code}.")
        items = response.json()
    if not isinstance(items, list) or not items:
        raise ApiError("NASA returned no dated entries.")
    with destination.open("x", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow({field: item[field] for field in fields})
    return len(items)


def run(client, dataset_id, output, *, image_url, text_url, youtube_ids):
    date_range = client.log_range(dataset_id)
    if not date_range or not date_range["start_time"]:
        raise ApiError("Choose an authorized dataset with imported logs.")
    output.mkdir(parents=True, exist_ok=False)
    report = {"dataset_id": dataset_id, "exercises": {}}
    results = report["exercises"]
    try:
        with urlopen(client.base + "/?workspace=logs", timeout=8) as response:
            (output / "01-log-explorer.html").write_bytes(response.read(1_000_000))
        errors = {}
        for label, url in (
            ("http", client.base + "/api/v1/course-path-missing"),
            ("network", "http://127.0.0.1:0/"),
        ):
            try:
                with urlopen(url, timeout=3):
                    pass
            except HTTPError as error:
                errors[label] = {"exception": "HTTPError", "status": error.code}
                error.close()
            except URLError as error:
                errors[label] = {"exception": "URLError", "reason": type(error.reason).__name__}
        results["1"] = {"html": "01-log-explorer.html", "errors": errors}

        # The requests client authenticates. urllib reuses only the session cookie
        # on the same origin to read the same real dataset.
        page = client.logs(dataset_id, date_range["start_time"], date_range["end_time"], limit=10)
        if not page["items"]:
            raise ApiError("No log records in this interval.")
        severity = page["items"][0]["severity"]
        filters = {
            "dataset_id": dataset_id,
            "start_time": date_range["start_time"],
            "end_time": date_range["end_time"],
            "limit": 10,
        }
        if severity:
            filters["severity"] = severity
        opener = build_opener(HTTPCookieProcessor(client.session.cookies))
        request = Request(
            client.base + "/api/v1/logs?" + urlencode(filters), headers={"Accept": "application/json"}
        )
        opened = opener.open(request, timeout=8)
        try:
            first = json.load(opened)
            results["2"] = {
                "status": opened.status,
                "content_type": opened.headers.get_content_type(),
                "severity": severity,
                "matches": first["count"],
            }
        finally:
            opened.close()
        pinned = Request(
            client.base
            + "/api/v1/logs?"
            + urlencode(
                {
                    **filters,
                    "scope_token": first["scope_token"],
                }
            ),
            headers={"Accept": "application/json"},
        )
        with opener.open(pinned, timeout=8) as response:
            second = json.load(response)
        results["3"] = {
            "same_ids": [r["id"] for r in first["items"]] == [r["id"] for r in second["items"]],
            "both_responses_closed": opened.closed and response.closed,
        }

        for exercise, operation in (
            ("4", lambda: {"images": download_images(image_url, output)}),
            ("5", lambda: {"rows": text_to_csv(text_url, output / "05-remote-text.csv"), "source": text_url}),
        ):
            try:
                results[exercise] = operation()
            except (URLError, OSError, ValueError) as error:
                results[exercise] = {"status": "failed", "error": type(error).__name__}

        results["6"] = {"first_timestamp": page["items"][0]["timestamp"], "nested_path": "items[0].timestamp"}
        write_log_csv(output / "06-real-log-rows.csv", page["items"])
        key = os.environ.get("YOUTUBE_API_KEY")
        if key:
            try:
                results["7"] = {
                    "rows": youtube_statistics(youtube_ids, key, output / "07-video-statistics.csv")
                }
            except ApiError as error:
                results["7"] = {"status": "failed", "error": str(error)}
        else:
            try:
                results["7"] = {
                    "provider": "NASA APOD",
                    "rows": nasa_dates(output / "07-nasa-apod.csv"),
                    "youtube": "not_run: YOUTUBE_API_KEY is required for the original video exercise",
                }
            except (ApiError, ValueError) as error:
                results["7"] = {"provider": "NASA APOD", "status": "failed", "error": str(error)}
    finally:
        (output / "results.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--username", required=True)
    parser.add_argument("--dataset", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--images-url", default="https://www.python.org/")
    parser.add_argument("--text-url", default="https://www.python.org/robots.txt")
    parser.add_argument(
        "--youtube-ids",
        nargs="+",
        default=[
            "7cmvABXyUC0",
            "9eH-7x7swEM",
            "JndzGxbwvG0",
            "l0P5_E6J_g0",
        ],
    )
    args = parser.parse_args()
    try:
        with LogSenseClient(args.url) as client:
            client.login(args.username, getpass("LogSense password: "))
            report = run(
                client,
                args.dataset,
                args.output,
                image_url=args.images_url,
                text_url=args.text_url,
                youtube_ids=args.youtube_ids,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (ApiError, URLError, OSError, ValueError) as error:
        parser.exit(1, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
