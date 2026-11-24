"""Linux installer helpers: scoped dependency check and an application-menu launcher."""

import argparse
from importlib.metadata import PackageNotFoundError, distribution
import os
from pathlib import Path
import re
import subprocess
import sys

APP_ID = "h-logsen"
DESKTOP_MARKER = "X-H-logsen-Launcher=true"
ICON = Path(__file__).resolve().parents[1] / "static" / "h-logsen.png"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_closure(root="H-logsen"):
    """Return canonical names of the installed distribution and everything it requires."""
    pending, seen = [root], set()
    while pending:
        name = canonical(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        try:
            requirements = distribution(name).requires or ()
        except PackageNotFoundError:
            continue
        for requirement in requirements:
            match = _NAME.match(requirement)
            if match:
                pending.append(match.group())
    return seen


def dependency_problems(report, closure):
    """Keep only `pip check` lines about H-logsen or its own dependency tree."""
    problems = []
    for line in report.splitlines():
        match = _NAME.match(line.strip())
        if match and canonical(match.group()) in closure:
            problems.append(line.strip())
    return problems


def check_dependencies():
    # A venv created with --system-site-packages also sees distribution packages
    # (for example python-debian on Ubuntu). Their conflicts are not H-logsen's.
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    if result.returncode == 0:
        return []
    if not result.stdout.strip():
        # pip itself failed rather than reporting package conflicts.
        return [result.stderr.strip() or "pip check failed."]
    return dependency_problems(result.stdout, dependency_closure())


def _exec_argument(value):
    # Desktop Entry Specification: quote arguments and escape ", `, $ and \ inside them.
    escaped = re.sub(r'(["`$\\])', r"\\\1", str(value)).replace("%", "%%")
    return f'"{escaped}"'


def _string_value(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")


def desktop_entry(python, working_directory, icon=ICON):
    # Exec quoting is applied first, then the general string escape that doubles backslashes.
    command = _string_value(" ".join(_exec_argument(part)
                                     for part in (python, "-I", "-m", "app.workbench", "--desktop")))
    return "\n".join((
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        "Name=H-logsen",
        "GenericName=Log and training-run workbench",
        "Comment=Investigate logs, training runs and code in a local workspace",
        f"Exec={command}",
        f"Path={_string_value(working_directory)}",
        f"Icon={_string_value(icon)}",
        "Terminal=false",
        "Categories=Development;IDE;",
        "Keywords=log;training;terminal;analysis;",
        f"StartupWMClass={APP_ID}",
        "StartupNotify=true",
        DESKTOP_MARKER,
        "",
    ))


def applications_directory():
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home and Path(data_home).is_absolute() else Path.home() / ".local" / "share"
    return base / "applications"


def install_launcher(python=None, working_directory=None, directory=None):
    """Write the per-user menu entry. Never replace a file this installer did not create."""
    python = Path(python or sys.executable).absolute()
    working_directory = Path(working_directory or python.parents[2]).absolute()
    directory = Path(directory) if directory else applications_directory()
    if not python.is_file() or not ICON.is_file():
        raise RuntimeError("Install H-logsen before creating the launcher.")
    path = directory / f"{APP_ID}.desktop"
    if path.is_symlink() or (path.exists() and DESKTOP_MARKER not in path.read_text("utf-8", errors="replace")):
        print(f"Skipped existing launcher: {path}")
        return None
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(desktop_entry(python, working_directory), encoding="utf-8")
    temporary.chmod(0o644)
    os.replace(temporary, path)
    print(f"H-logsen launcher: {path}")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Fail when H-logsen's own dependencies are broken.")
    commands.add_parser("launcher", help="Add H-logsen to the desktop application menu.")
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = check_dependencies()
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1 if problems else 0
    install_launcher()
    return 0


if __name__ == "__main__":
    sys.exit(main())
