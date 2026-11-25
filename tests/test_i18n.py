"""Locale switching preserves access scope and data across full and partial pages."""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

from app import create_app
from app.i18n import LANGUAGES, catalog


class LanguageOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_picker = False
        self.codes = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.in_picker = attrs.get("name") == "language"
        if tag == "option" and self.in_picker:
            self.codes.append(attrs["value"])

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_picker = False


class InterfaceLanguages(unittest.TestCase):
    def setUp(self):
        self.client = create_app({"TESTING": True}).test_client()

    def test_each_language_renders_the_login_and_investigation(self):
        self.assertEqual(len(LANGUAGES), 15)
        placeholders = re.compile(r"\{\d+\}")
        for language in LANGUAGES:
            with self.subTest(language=language):
                target = "/?workspace=logs&dataset_id=12"
                result = self.client.post(
                    "/preferences/language", data={"language": language, "next": target}
                )
                self.assertEqual(result.status_code, 303)
                self.assertEqual(result.location, target)
                response = self.client.get(result.location)
                self.assertEqual(response.headers["Content-Language"], language)
                html = response.get_data(as_text=True)
                self.assertIn(f'<html lang="{language}" data-workspace-theme>', html)
                messages = catalog(language)
                self.assertIn(messages.get("Sign in", "Sign in"), html)
                if language != "en":
                    self.assertNotEqual(messages["Sign in"], "Sign in")
                options = LanguageOptions()
                options.feed(html)
                self.assertEqual(options.codes, [])
                settings = self.client.get("/?view=settings")
                self.assertIn(
                    f'<html lang="{language}" data-workspace-theme>', settings.get_data(as_text=True)
                )
                self.assertIn(messages.get("Open project", "Open project"), settings.get_data(as_text=True))
                options.feed(settings.get_data(as_text=True))
                self.assertEqual(options.codes, list(LANGUAGES))
                self.assertEqual(self.client.get("/").status_code, 200)
                for source, value in messages.items():
                    for form in value.values() if isinstance(value, dict) else [value]:  # plural forms
                        self.assertEqual(
                            sorted(placeholders.findall(source)), sorted(placeholders.findall(form))
                        )

    def test_partial_render_keeps_data_and_translates_labels(self):
        path = "/api/v1/investigation?source=demo"
        english = self.client.get(path).get_json()
        self.client.post("/preferences/language", data={"language": "vi", "next": "/"})
        localized = self.client.get(path)
        self.assertEqual(localized.headers["Content-Language"], "vi")
        self.assertIn("Cookie", localized.headers["Vary"])
        data = localized.get_json()
        self.assertIn(catalog("vi")["Anomaly activity"], data["html"])
        self.assertEqual(data["state"], english["state"])
        self.assertEqual(data["events"], english["events"])
        self.assertEqual(data["revision"], english["revision"])

    def test_configured_database_links_log_explorer_from_workspace(self):
        client = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "mysql+pymysql://test@127.0.0.1:1/test",
            }
        ).test_client()
        home = client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b'id="open-project-file"', home.data)
        self.assertIn(b'href="/?workspace=logs"', home.data)
        logs = client.get("/?workspace=logs")
        self.assertIn(b'id="log-investigation-nav" hidden', logs.data)
        self.assertNotIn(b"Demo workspace", logs.data)
        self.assertIn(b"<strong>DEMO</strong>", client.get("/?source=demo").data)

    def test_preference_rejects_invalid_locale_and_external_redirect(self):
        result = self.client.post("/preferences/language", data={"language": "unsupported"})
        self.assertEqual(result.status_code, 400)
        self.assertNotIn("Set-Cookie", result.headers)
        for target in ("https://example.invalid", "//example.invalid", "/\\example.invalid"):
            result = self.client.post("/preferences/language", data={"language": "de", "next": target})
            self.assertEqual(result.location, "/?workspace=logs")
        self.assertEqual(self.client.get("/?workspace=logs").headers["Content-Language"], "de")


class ScriptLocaleTest(unittest.TestCase):
    def test_number_and_date_formats_follow_the_interface_language(self):
        # A literal locale ("vi") shows Vietnamese separators to every user; use document.documentElement.lang.
        static = Path(__file__).resolve().parents[1] / "app" / "static"
        pattern = re.compile(r"""(?:NumberFormat|DateTimeFormat|toLocale\w*String)\(\s*["']""")
        offenders = [
            f"{path.relative_to(static)}:{number}"
            for path in static.rglob("*.js")
            if "vendor" not in path.parts
            for number, line in enumerate(path.read_text("utf-8").splitlines(), 1)
            if pattern.search(line)
        ]
        self.assertEqual(offenders, [])


class CatalogShapeTest(unittest.TestCase):
    """Every catalog is whole messages with matching placeholders; plural forms use CLDR categories."""

    CATEGORIES = {"zero", "one", "two", "few", "many", "other"}

    def test_catalogs(self):
        from collections import Counter
        import json

        def placeholders(text):
            return Counter(re.findall(r"\{\d+\}", text))

        locales = Path(__file__).resolve().parents[1] / "app" / "locales"
        for path in sorted(locales.glob("*.json")):
            catalog = json.loads(path.read_text("utf-8"))
            for message, translation in catalog.items():
                with self.subTest(language=path.stem, message=message):
                    # A message that starts with a space or a separator was meant to be glued onto another.
                    self.assertFalse(message[:1].isspace() or message.startswith(("·", "—")))
                    forms = translation if isinstance(translation, dict) else {"other": translation}
                    self.assertIn("other", forms)
                    self.assertLessEqual(set(forms), self.CATEGORIES)
                    for text in forms.values():
                        self.assertEqual(placeholders(text), placeholders(message))
