"""Linux desktop integration (WebKitGTK window, menu launcher) and installer helpers."""

import argparse
from importlib.metadata import PackageNotFoundError, distribution
import os
from pathlib import Path
import re
import subprocess
import sys

from . import ICON_PNG
from .posix import close_terminal, open_terminal, shell_profiles  # noqa: F401  (backend interface)

APP_ID = "h-logsen"
DESKTOP_MARKER = "X-H-logsen-Launcher=true"
ICON = ICON_PNG
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def show_fatal_error(message):
    """Show a desktop dialog (zenity, kdialog) or notification; a menu launch has no terminal."""
    import shutil

    text = str(message)
    for command in (
        ["zenity", "--error", "--no-markup", "--title=H-logsen", "--text", text],
        ["kdialog", "--title", "H-logsen", "--error", text],
        ["notify-send", "--app-name=H-logsen", "H-logsen", text],
    ):
        if shutil.which(command[0]):
            try:
                subprocess.run(command, timeout=300, check=False, stdin=subprocess.DEVNULL)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


def desktop_options():
    """Return (create_window options, webview.start options)."""
    try:
        from gi.repository import GLib

        # The Wayland app_id and X11 WM_CLASS come from the program name. Match the
        # installed h-logsen.desktop so the dock shows the H-logsen icon, not "python3".
        GLib.set_prgname(APP_ID)
        GLib.set_application_name("H-logsen")
    except ImportError:
        pass
    # GTK has no system blur, but an RGBA window lets the glass tint show the desktop.
    return {"transparent": True}, {"icon": str(ICON)}


def compositing_available(timeout=2.0):
    """Ask GTK on its main loop whether the screen composites; without it an RGBA window is black."""
    import threading

    try:
        import gi

        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GLib
    except (ImportError, ValueError):
        return True
    result, done = {}, threading.Event()

    def check():
        screen = Gdk.Screen.get_default()
        result["value"] = screen is None or bool(screen.is_composited())
        done.set()
        return False

    GLib.idle_add(check)
    return result["value"] if done.wait(timeout) else True


def set_window_glass(window, enabled):
    return bool(window and window.transparent and enabled and compositing_available())


HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
DEFAULT_TITLE_BAR = (True, "#1c1c1c", "#ededeb")  # Graphite, the default palette
_title_bar_css = []


def title_bar_css(background, foreground):
    if not (HEX_COLOR.fullmatch(background) and HEX_COLOR.fullmatch(foreground)):
        raise ValueError("Title bar colours must be #rrggbb.")
    return f"""
headerbar, .titlebar, headerbar:backdrop, .titlebar:backdrop {{
    background: {background}; background-image: none; color: {foreground};
    border-color: {background}; box-shadow: none;
}}
headerbar .title, .titlebar .title, headerbar button, .titlebar button.titlebutton {{ color: {foreground}; }}
headerbar:backdrop .title, .titlebar:backdrop .title {{ color: alpha({foreground}, 0.6); }}
"""


def set_window_theme(window, dark, background, foreground):
    """Paint the GTK client-side title bar with the workspace palette (GTK3 ignores GNOME's dark style)."""
    if type(dark) is not bool or not isinstance(background, str) or not isinstance(foreground, str):
        return False
    try:
        css = title_bar_css(background, foreground).encode()
        import gi

        gi.require_version("Gdk", "3.0")  # pin before import; Gdk 4 would otherwise be loaded first
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk, GLib, Gtk
    except (ImportError, ValueError):
        return False

    def apply():
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", dark)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            if not _title_bar_css:
                provider = Gtk.CssProvider()
                Gtk.StyleContext.add_provider_for_screen(
                    screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                _title_bar_css.append(provider)
            _title_bar_css[0].load_from_data(css)
        return False

    GLib.idle_add(apply)  # GTK may only be touched from its main loop
    return True


def attach_window(window):
    """Use the default palette before the page loads, so the title bar never flashes white."""
    window.events.before_show += lambda: set_window_theme(window, *DEFAULT_TITLE_BAR)


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
    command = _string_value(
        " ".join(_exec_argument(part) for part in (python, "-I", "-m", "app.workbench", "--desktop"))
    )
    return "\n".join(
        (
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
        )
    )


def applications_directory():
    data_home = os.environ.get("XDG_DATA_HOME")
    base = (
        Path(data_home) if data_home and Path(data_home).is_absolute() else Path.home() / ".local" / "share"
    )
    return base / "applications"


def install_icon(data_home):
    """Copy the H artwork into the user's hicolor theme so the menu and dock keep it even if the
    install folder moves or sits on an unmounted drive. Returns the icon name, or None."""
    target = data_home / "icons" / "hicolor" / "256x256" / "apps" / f"{APP_ID}.png"
    try:
        from PIL import Image

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        with Image.open(ICON) as image:
            image.convert("RGBA").resize((256, 256), Image.LANCZOS).save(temporary, "PNG")
        temporary.chmod(0o644)
        os.replace(temporary, target)
    except (ImportError, OSError):
        return None
    return APP_ID


def install_launcher(python=None, working_directory=None, directory=None):
    """Write the per-user menu entry. Never replace a file this installer did not create."""
    python = Path(python or sys.executable).absolute()
    working_directory = Path(working_directory or python.parents[2]).absolute()
    directory = Path(directory) if directory else applications_directory()
    if not python.is_file() or not ICON.is_file():
        raise RuntimeError("Install H-logsen before creating the launcher.")
    path = directory / f"{APP_ID}.desktop"
    if path.is_symlink() or (
        path.exists() and DESKTOP_MARKER not in path.read_text("utf-8", errors="replace")
    ):
        print(f"Skipped existing launcher: {path}")
        return None
    directory.mkdir(parents=True, exist_ok=True)
    icon = install_icon(directory.parent) or ICON
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(desktop_entry(python, working_directory, icon), encoding="utf-8")
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
