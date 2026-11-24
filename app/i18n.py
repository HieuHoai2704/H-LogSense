"""Local interface catalogs and a browser language preference."""

from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, has_request_context, redirect, request, url_for


LANGUAGES = {
    "en": "English",
    "vi": "Tiếng Việt",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ru": "Русский",
    "ja": "日本語",
    "ko": "한국어",
    "zh-Hans": "简体中文",
    "id": "Bahasa Indonesia",
    "th": "ไทย",
    "tr": "Türkçe",
}
COOKIE = "logsense_language"
locale_pages = Blueprint("locale_pages", __name__)


def current_language():
    if not has_request_context():
        return "en"
    default = current_app.config.get("DEFAULT_INTERFACE_LANGUAGE", "en")
    language = request.cookies.get(COOKIE, default)
    return language if language in LANGUAGES else default


@lru_cache(maxsize=len(LANGUAGES))
def catalog(language):
    if language == "en":
        return {}
    path = Path(__file__).with_name("locales")
    messages = json.loads((path / f"{language}.json").read_text(encoding="utf-8"))
    workspace = workspace_labels()
    return {**messages, **dict(zip(workspace["en"], workspace[language], strict=True))}


@lru_cache(maxsize=1)
def workspace_labels():
    return json.loads(
        Path(__file__).with_name("locales").joinpath("workspace.json").read_text(encoding="utf-8")
    )


def translate(message, *values):
    result = catalog(current_language()).get(message, message)
    if not values:
        return result
    return re.sub(
        r"\{(\d+)\}",
        lambda match: str(values[int(match[1])]) if int(match[1]) < len(values) else match[0],
        result,
    )


@locale_pages.post("/preferences/language")
def select_language():
    # Only this site may change the preference (the form posts same-origin; no token needed).
    site = request.headers.get("Sec-Fetch-Site")
    origin = request.headers.get("Origin")
    if site not in (None, "same-origin", "none") or (origin and origin != request.host_url.rstrip("/")):
        abort(403)
    language = request.form.get("language", "")
    if language not in LANGUAGES:
        abort(400)
    target = request.form.get("next", "")
    if (
        not target.startswith("/")
        or target.startswith("//")
        or "\\" in target
        or any(ord(char) < 32 or ord(char) == 127 for char in target)
    ):
        target = url_for("dashboard", workspace="logs")
    else:
        try:
            parsed = urlsplit(target)
        except ValueError:
            parsed = None
        if parsed is None or parsed.scheme or parsed.netloc:
            target = url_for("dashboard", workspace="logs")
    response = redirect(target, code=303)
    response.set_cookie(
        COOKIE,
        language,
        max_age=365 * 24 * 60 * 60,
        secure=bool(current_app.config["SESSION_COOKIE_SECURE"]),
        httponly=True,
        samesite="Lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def initialize_i18n(app):
    app.register_blueprint(locale_pages)

    @app.context_processor
    def interface_language():
        language = current_language()
        return {
            "tr": translate,
            "interface_language": language,
            "languages": LANGUAGES,
            "interface_catalog": catalog(language),
        }

    @app.after_request
    def language_headers(response):
        if response.mimetype == "text/html" or request.endpoint == "anomalies.investigation":
            response.headers["Content-Language"] = current_language()
            response.vary.add("Cookie")
        return response
