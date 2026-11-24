"""macOS desktop integration: WKWebView window with system vibrancy."""

from . import ICON_PNG
from .posix import close_terminal, open_terminal, shell_profiles  # noqa: F401  (backend interface)


def show_fatal_error(message):
    """Alert dialog for Finder/Dock launches; the text is passed as an argument, never as script."""
    import subprocess

    script = [
        "-e",
        "on run argv",
        "-e",
        'display alert "H-logsen" message (item 1 of argv) as critical',
        "-e",
        "end run",
    ]
    try:
        subprocess.run(
            ["osascript", *script, "--", str(message)], timeout=300, check=False, stdin=subprocess.DEVNULL
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def set_dock_icon():
    """A Python-launched app shows the Python rocket in the Dock; use the H-logsen artwork instead."""
    try:
        from AppKit import NSApplication, NSImage
    except ImportError:
        return False
    image = NSImage.alloc().initWithContentsOfFile_(str(ICON_PNG))
    if image is None:
        return False
    NSApplication.sharedApplication().setApplicationIconImage_(image)
    return True


def desktop_options():
    """Return (create_window options, webview.start options). Runs on the main thread before start."""
    set_dock_icon()
    return {"transparent": True, "vibrancy": True}, {}


def set_window_glass(window, enabled):
    from AppKit import NSWorkspace

    return bool(
        window
        and window.transparent
        and enabled
        and not NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency()
    )
