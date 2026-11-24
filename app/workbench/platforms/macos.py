"""macOS desktop integration: WKWebView window with system vibrancy."""

from .posix import close_terminal, open_terminal, shell_profiles  # noqa: F401  (backend interface)


def desktop_options():
    """Return (create_window options, webview.start options)."""
    return {"transparent": True, "vibrancy": True}, {}


def set_window_glass(window, enabled):
    from AppKit import NSWorkspace

    return bool(window and window.transparent and enabled
                and not NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency())
