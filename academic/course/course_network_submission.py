"""Seven independent Chapter 8 exercises. Run with python -m academic.course.course_network_submission."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from scripts.run.logsense_client import ApiError
from academic.course.network_lab import download_images, text_to_csv, youtube_statistics

VIDEO_IDS = ("7cmvABXyUC0", "9eH-7x7swEM", "JndzGxbwvG0", "l0P5_E6J_g0")
PYTHON_URL = "http://python.org/"
ISS_URL = "http://api.open-notify.org/iss-pass.json?" + urlencode({"lat": 37.78, "lon": -122.41})
MAX_HTML_BYTES = 2_000_000


def response_details(response):
    body = response.read(MAX_HTML_BYTES + 1)
    if len(body) > MAX_HTML_BYTES:
        raise ValueError("HTML response exceeds exercise limit")
    return {
        "http": response.getcode(),
        "final_url": response.geturl(),
        "type": response.headers.get_content_type(),
        "bytes": len(body),
    }, body


def capture(operation):
    try:
        return {"status": "PASS", **operation()}
    except HTTPError as error:
        error.close()
        return {"status": "FAIL", "error": "HTTPError", "http": error.code}
    except URLError as error:
        return {"status": "FAIL", "error": "URLError", "reason": type(error.reason).__name__}
    except (ApiError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        result = {"status": "FAIL", "error": type(error).__name__}
        if isinstance(error, ApiError):
            result["message"] = str(error)
        return result


def response_probe(url):
    with urlopen(url, timeout=12) as response:
        details, _ = response_details(response)
    return details


def error_probe(url, expected, http_status=None):
    result = capture(lambda: response_probe(url))
    matched = result.get("error") == expected and result.get("http") == http_status
    return {**result, "status": "PASS" if matched else "FAIL", "expected_error": expected}


def save_google(output):
    with urlopen("https://www.google.com/", timeout=12) as response:
        details, body = response_details(response)
    (output / "01-google.html").write_bytes(body)
    return {**details, "file": "01-google.html"}


def read_python_twice(url):
    manual = urlopen(url, timeout=12)
    try:
        first, body_one = response_details(manual)
    finally:
        manual.close()
    with urlopen(url, timeout=12) as managed:
        second, body_two = response_details(managed)
    return {
        "manual": first,
        "context_manager": second,
        "both_closed": manual.closed and managed.closed,
        "identical_bytes": hashlib.sha256(body_one).digest() == hashlib.sha256(body_two).digest(),
    }


def first_duration(payload):
    duration = payload["response"][0]["duration"]
    if type(duration) is not int or duration < 0:
        raise ValueError("Expected a non-negative duration in seconds")
    return {"first_duration_seconds": duration}


def iss_live():
    with urlopen(ISS_URL, timeout=12) as response:
        return first_duration(json.loads(response.read(100_000)))


def mdn_images(output):
    images = download_images(
        "https://developer.mozilla.org/en-US/docs/Web/HTTP/Messages/",
        output,
        image_origins=("mdn.github.io",),
    )
    if not images:
        raise ValueError("The current MDN page returned no matching image files")
    return {"images": images}


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    key = os.environ.get("YOUTUBE_API_KEY")
    report = {
        "1": {
            "html": capture(lambda: save_google(output)),
            "http_error_probe": error_probe(
                "https://www.python.org/logsense-course-missing-404", "HTTPError", 404
            ),
            "url_error_probe": error_probe("http://127.0.0.1:0/", "URLError"),
        },
        "2": capture(lambda: response_probe("https://www.google.com/search?q=test")),
        "3": capture(lambda: read_python_twice(PYTHON_URL)),
        "4": capture(lambda: mdn_images(output)),
        "5": capture(
            lambda: {"rows": text_to_csv("http://sixty-north.com/c/t.txt", output / "05-story.csv")}
        ),
        "6": {
            "live": capture(iss_live),
            "course_sample": {
                "source": "PYTHONNANGCAO_NET_DOCTHEM.pdf p.17",
                **first_duration({"response": [{"duration": 630}]}),
            },
        },
        "7": capture(lambda: {"rows": youtube_statistics(VIDEO_IDS, key, output / "07-youtube.csv")})
        if key
        else {"status": "SKIP", "reason": "YOUTUBE_API_KEY is not configured"},
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)


if __name__ == "__main__":
    main()
