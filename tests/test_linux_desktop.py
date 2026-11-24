"""Linux installer helpers and Windows reserved-name checks that run on any OS."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.workbench import linux
from app.workbench.files import component, windows_reserved


class ReservedNameTest(unittest.TestCase):
    def test_matches_windows_device_names_without_pathlib(self):
        for name in ("CON", "con.txt", "Nul ", "COM1.log", "lpt9", "LPT¹", "aux.tar.gz", "CONIN$"):
            self.assertTrue(windows_reserved(name), name)
            self.assertFalse(component(name), name)
        for name in ("console", "COM0", "COM10", "x.con", "contract.md"):
            self.assertFalse(windows_reserved(name), name)


class DependencyCheckTest(unittest.TestCase):
    def test_ignores_system_packages_outside_the_dependency_tree(self):
        report = "\n".join((
            "python-debian 1.0.1+ubuntu2 requires charset-normalizer, which is not installed.",
            "Flask-WTF 1.2.2 requires WTForms, which is not installed.",
            "scikit_learn 1.7.2 has requirement numpy>=1.22, but you have numpy 1.0.",
        ))
        closure = {"h-logsen", "flask-wtf", "scikit-learn", "numpy"}
        self.assertEqual(linux.dependency_problems(report, closure), [
            "Flask-WTF 1.2.2 requires WTForms, which is not installed.",
            "scikit_learn 1.7.2 has requirement numpy>=1.22, but you have numpy 1.0.",
        ])

    def test_pip_failure_without_a_report_is_a_problem(self):
        class Result:
            returncode, stdout, stderr = 1, "", "No module named pip"

        with patch.object(linux.subprocess, "run", return_value=Result()):
            self.assertEqual(linux.check_dependencies(), ["No module named pip"])

    def test_closure_follows_installed_requirements(self):
        requirements = {"h-logsen": ["Flask<3.2,>=3.1", "pywebview==6.2.1; extra == \"desktop\""],
                        "flask": ["Werkzeug>=3.1"], "werkzeug": None}

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
        self.assertTrue(Path(fields["Icon"]).is_file())
        # A literal $ is \$ for Exec quoting and \\$ after the string escape in the file.
        self.assertEqual(self.exec_arguments(fields["Exec"]),
                         [str(self.python), "-I", "-m", "app.workbench", "--desktop"])
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
            self.assertEqual(linux.applications_directory(), Path.home() / ".local" / "share" / "applications")

    def test_percent_is_escaped_for_field_codes(self):
        self.assertEqual(linux._exec_argument("50%"), '"50%%"')


if __name__ == "__main__":
    unittest.main()
