"""Linux installer helpers and Windows reserved-name checks that run on any OS."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.workbench.files import component, windows_reserved
from app.workbench.platforms import linux


class ReservedNameTest(unittest.TestCase):
    def test_matches_windows_device_names_without_pathlib(self):
        for name in ("CON", "con.txt", "Nul ", "COM1.log", "lpt9", "LPT¹", "aux.tar.gz", "CONIN$"):
            self.assertTrue(windows_reserved(name), name)
            self.assertFalse(component(name), name)
        for name in ("console", "COM0", "COM10", "x.con", "contract.md"):
            self.assertFalse(windows_reserved(name), name)


class DependencyCheckTest(unittest.TestCase):
    def test_ignores_system_packages_outside_the_dependency_tree(self):
        report = "\n".join(
            (
                "python-debian 1.0.1+ubuntu2 requires charset-normalizer, which is not installed.",
                "Flask-WTF 1.2.2 requires WTForms, which is not installed.",
                "scikit_learn 1.7.2 has requirement numpy>=1.22, but you have numpy 1.0.",
            )
        )
        closure = {"h-logsen", "flask-wtf", "scikit-learn", "numpy"}
        self.assertEqual(
            linux.dependency_problems(report, closure),
            [
                "Flask-WTF 1.2.2 requires WTForms, which is not installed.",
                "scikit_learn 1.7.2 has requirement numpy>=1.22, but you have numpy 1.0.",
            ],
        )

    def test_pip_failure_without_a_report_is_a_problem(self):
        class Result:
            returncode, stdout, stderr = 1, "", "No module named pip"

        with patch.object(linux.subprocess, "run", return_value=Result()):
            self.assertEqual(linux.check_dependencies(), ["No module named pip"])

    def test_closure_follows_installed_requirements(self):
        requirements = {
            "h-logsen": ["Flask<3.2,>=3.1", 'pywebview==6.2.1; extra == "desktop"'],
            "flask": ["Werkzeug>=3.1"],
            "werkzeug": None,
        }

        class Distribution:
            def __init__(self, name):
                if name not in requirements:
                    raise linux.PackageNotFoundError(name)
                self.requires = requirements[name]

        with patch.object(linux, "distribution", Distribution):
            self.assertEqual(linux.dependency_closure(), {"h-logsen", "flask", "werkzeug", "pywebview"})


class LauncherTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.install = self.folder / "H-logsen 0.4 (test)$"
        self.python = self.install / ".venv" / "bin" / "python"
        self.python.parent.mkdir(parents=True)
        self.python.write_text("", encoding="utf-8")
        self.applications = self.folder / "applications"

    @staticmethod
    def exec_arguments(value):
        """Decode an Exec value: string escapes first, then the quoting rules of the specification."""
        value = value.replace("\\\\", "\0").replace("\\s", " ").replace("\0", "\\")
        arguments, current, quoted, index = [], "", False, 0
        while index < len(value):
            char = value[index]
            if quoted and char == "\\" and value[index + 1] in '"`$\\':
                current += value[index + 1]
                index += 1
            elif char == '"':
                quoted = not quoted
            elif char == " " and not quoted:
                arguments.append(current)
                current = ""
            else:
                current += char
            index += 1
        return arguments + [current]

    def entry(self, path):
        fields = {}
        for line in path.read_text("utf-8").splitlines()[1:]:
            key, _, value = line.partition("=")
            fields[key] = value
        return fields

    def test_writes_quoted_entry_that_starts_the_installed_environment(self):
        path = linux.install_launcher(self.python, directory=self.applications)
        fields = self.entry(path)
        self.assertEqual(path.name, "h-logsen.desktop")
        self.assertEqual(fields["Type"], "Application")
        self.assertEqual(fields["StartupWMClass"], linux.APP_ID)
        self.assertEqual(fields["Path"], str(self.install))
        self.assertEqual(fields["Icon"], linux.APP_ID)  # themed name, independent of the install folder
        icon = self.folder / "icons" / "hicolor" / "256x256" / "apps" / "h-logsen.png"
        from PIL import Image

        with Image.open(icon) as image:
            self.assertEqual(image.size, (256, 256))
        # A literal $ is \$ for Exec quoting and \\$ after the string escape in the file.
        self.assertEqual(
            self.exec_arguments(fields["Exec"]), [str(self.python), "-I", "-m", "app.workbench", "--desktop"]
        )
        self.assertIn(r"\\$", fields["Exec"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_replaces_own_entry_but_not_a_foreign_one(self):
        first = linux.install_launcher(self.python, directory=self.applications)
        self.assertEqual(linux.install_launcher(self.python, directory=self.applications), first)
        first.write_text("[Desktop Entry]\nName=Other\n", encoding="utf-8")
        self.assertIsNone(linux.install_launcher(self.python, directory=self.applications))
        self.assertIn("Name=Other", first.read_text("utf-8"))

    def test_uses_absolute_xdg_data_home_only(self):
        with patch.dict(linux.os.environ, {"XDG_DATA_HOME": str(self.folder / "data")}):
            self.assertEqual(linux.applications_directory(), self.folder / "data" / "applications")
        with patch.dict(linux.os.environ, {"XDG_DATA_HOME": "relative"}):
            self.assertEqual(
                linux.applications_directory(), Path.home() / ".local" / "share" / "applications"
            )

    def test_percent_is_escaped_for_field_codes(self):
        self.assertEqual(linux._exec_argument("50%"), '"50%%"')


class TitleBarThemeTest(unittest.TestCase):
    def test_css_uses_only_validated_hex_colours(self):
        css = linux.title_bar_css("#1c1c1c", "#ededeb")
        self.assertIn("background: #1c1c1c", css)
        self.assertIn("color: #ededeb", css)
        for bad in ("red", "#fff", "#1c1c1c; } * { color: red", "rgb(0,0,0)"):
            with self.assertRaises(ValueError):
                linux.title_bar_css(bad, "#ededeb")

    def test_invalid_requests_are_refused_without_touching_gtk(self):
        self.assertFalse(linux.set_window_theme(None, "yes", "#000000", "#ffffff"))
        self.assertFalse(linux.set_window_theme(None, True, "#000", "#ffffff"))
        self.assertFalse(linux.set_window_theme(None, True, None, "#ffffff"))

    def test_valid_request_works_in_a_fresh_process_with_gtk3(self):
        # Without pinning Gdk 3, a new interpreter loads Gdk 4 first and the theme silently fails.
        import subprocess
        import sys

        probe = "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk"
        if subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode:
            self.skipTest("GTK 3 bindings are not available")
        code = (
            "from app.workbench.platforms import linux; "
            "print(linux.set_window_theme(None, True, '#000000', '#ffffff'))"
        )
        result = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), "True", result.stderr)

    def test_bridge_requires_the_launch_token(self):
        from app.workbench.desktop import DesktopBridge

        bridge = DesktopBridge("secret", store=None, folder_dialog=None)
        with patch("app.workbench.desktop.platform_backend") as backend:
            self.assertFalse(bridge.set_window_theme("wrong", True, "#000000", "#ffffff"))
            backend.set_window_theme.assert_not_called()
            backend.set_window_theme.return_value = True
            self.assertTrue(bridge.set_window_theme("secret", True, "#000000", "#ffffff"))


class AppIconTest(unittest.TestCase):
    def test_every_platform_uses_the_shared_h_artwork(self):
        from PIL import Image

        from app.workbench.platforms import ICON_ICO, ICON_PNG

        self.assertIs(linux.ICON, ICON_PNG)
        with Image.open(ICON_PNG) as png:
            self.assertEqual(png.size[0], png.size[1])
            self.assertGreaterEqual(png.size[0], 512)  # sharp in the macOS Dock and GNOME
        with Image.open(ICON_ICO) as ico:
            self.assertTrue({(16, 16), (32, 32), (256, 256)} <= ico.info["sizes"])  # Windows taskbar sizes


if __name__ == "__main__":
    unittest.main()
