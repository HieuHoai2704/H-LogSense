"""Native desktop window and authenticated folder selection."""

import os
from pathlib import Path
import secrets
import sys
from threading import Lock

from .files import WORKSPACES, WorkspaceError
from .platforms import current as platform_backend


class DesktopUnavailable(RuntimeError):
    """The native window cannot open here (no graphical session or no webview); browser mode can."""


RENDERERS = {
    "win32": ("edgechromium", "edgechromium"),
    "darwin": ("cocoa", "wkwebview"),
    "linux": ("gtk", "gtkwebkit2"),
}


class DesktopBridge:
    def __init__(self, token, store, folder_dialog):
        self._token = token
        self._store = store
        self._folder_dialog = folder_dialog
        self._lock = Lock()
        self._window = None

    def _attach(self, window):
        self._window = window

    def _authorized(self, token):
        return isinstance(token, str) and secrets.compare_digest(token.encode(), self._token.encode())

    def set_window_glass(self, token, enabled):
        if type(enabled) is not bool or not self._authorized(token):
            return False
        glass = getattr(platform_backend, "set_window_glass", None)
        return bool(glass and glass(self._window, enabled))

    def set_window_theme(self, token, dark, background, foreground):
        """Match native window chrome to the workspace palette where the platform needs it (Linux)."""
        if not self._authorized(token):
            return False
        theme = getattr(platform_backend, "set_window_theme", None)
        return bool(theme and theme(self._window, dark, background, foreground))

    def pick_project(self, token, workspace="project"):
        if not self._authorized(token):
            return None
        if not isinstance(workspace, str) or workspace not in WORKSPACES:
            return None
        if not self._lock.acquire(blocking=False):
            return None
        try:
            try:
                initial = str(self._store.workspace_root(workspace))
            except WorkspaceError:
                initial = str(Path.home())
            chosen = self._window.create_file_dialog(self._folder_dialog, directory=initial)
            return chosen[0] if chosen else None
        finally:
            self._lock.release()


def desktop_window(url, token, store):
    gui, expected_renderer = RENDERERS[sys.platform]
    if gui == "gtk" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise DesktopUnavailable("Desktop mode requires a graphical session.")
    try:
        import webview
    except ImportError:
        raise DesktopUnavailable(
            "The desktop window needs pywebview; install H-logsen with the platform installer."
        ) from None

    window_options, start_options = platform_backend.desktop_options()

    bridge = DesktopBridge(token, store, webview.FileDialog.FOLDER)
    window = webview.create_window(
        "H-logsen",
        url,
        width=1440,
        height=900,
        min_size=(900, 620),
        background_color="#191919",
        js_api=bridge,
        **window_options,
    )
    bridge._attach(window)
    attach = getattr(platform_backend, "attach_window", None)
    if attach:
        attach(window)
    window.events.initialized += lambda renderer: renderer == expected_renderer
    webview.start(
        gui=gui, private_mode=False, storage_path=str(store.directory / "desktop-webview"), **start_options
    )
    if webview.renderer != expected_renderer:
        raise RuntimeError(f"Desktop mode requires {expected_renderer}. See the platform installation guide.")
