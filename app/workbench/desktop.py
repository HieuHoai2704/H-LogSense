"""Native desktop window and authenticated folder selection."""

import os
from pathlib import Path
import secrets
import sys
from threading import Lock

from .files import WORKSPACES, WorkspaceError

RENDERERS = {"win32": ("edgechromium", "edgechromium"), "darwin": ("cocoa", "wkwebview"),
             "linux": ("gtk", "gtkwebkit2")}


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
        if sys.platform == "darwin":
            from AppKit import NSWorkspace

            return bool(self._window and self._window.transparent and enabled
                        and not NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency())
        if sys.platform == "linux":
            # GTK has no system blur, but an RGBA window lets the glass tint show the desktop.
            return bool(self._window and self._window.transparent and enabled)
        if sys.platform != "win32":
            return False
        from .windows import set_window_glass

        return set_window_glass(self._window, enabled)

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
        raise RuntimeError("Desktop mode requires a graphical session. Use --no-browser for a local server.")
    try:
        import webview
    except ImportError:
        raise RuntimeError("Install H-logsen with the platform installer to use desktop mode.") from None

    window_options = {}
    start_options = {}
    if gui == "edgechromium":
        from .windows import ICON, identify_process

        identify_process()
        start_options["icon"] = str(ICON)
    elif gui == "cocoa":
        window_options.update(transparent=True, vibrancy=True)
    elif gui == "gtk":
        from .linux import APP_ID, ICON

        try:
            from gi.repository import GLib

            # The Wayland app_id and X11 WM_CLASS come from the program name. Match the
            # installed h-logsen.desktop so the dock shows the H-logsen icon, not "python3".
            GLib.set_prgname(APP_ID)
            GLib.set_application_name("H-logsen")
        except ImportError:
            pass
        start_options["icon"] = str(ICON)
        window_options["transparent"] = True

    bridge = DesktopBridge(token, store, webview.FileDialog.FOLDER)
    window = webview.create_window("H-logsen", url, width=1440, height=900, min_size=(900, 620),
                                   background_color="#191919", js_api=bridge, **window_options)
    bridge._attach(window)
    window.events.initialized += lambda renderer: renderer == expected_renderer
    webview.start(gui=gui, private_mode=False, storage_path=str(store.directory / "desktop-webview"), **start_options)
    if webview.renderer != expected_renderer:
        raise RuntimeError(f"Desktop mode requires {expected_renderer}. See the platform installation guide.")
