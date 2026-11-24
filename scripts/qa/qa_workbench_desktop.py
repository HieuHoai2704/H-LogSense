"""Exercise the installed desktop launcher and authenticated UI on a native renderer."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import webview

from app.workbench.__main__ import main
from app.workbench.desktop import RENDERERS


def verify_desktop_glass(window):
    reduced = window.evaluate_js(
        "matchMedia('(prefers-reduced-transparency: reduce), (forced-colors: active)').matches"
    )
    native = window.native
    if sys.platform == "win32":
        from System import Boolean, Func

        supported = sys.getwindowsversion().build >= 22621 and not reduced

        def matches(expected):
            return native.Invoke(
                Func[Boolean](
                    lambda: (
                        native.Opacity == 1.0 and (native.webview.DefaultBackgroundColor.A == 0) == expected
                    )
                )
            )
    elif sys.platform == "darwin":
        from AppKit import NSWorkspace

        supported = (
            not reduced and not NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency()
        )

        def matches(expected):
            return window.transparent
    else:
        # GTK: an RGBA window without a system blur; the CSS tint provides the glass.
        supported = not reduced

        def matches(expected):
            return window.transparent

    palettes = (
        ("glass", supported),
        ("glass-forest", supported),
        ("glass-mint", supported),
        ("glass-blue", supported),
        ("graphite", False),
    )
    for palette, expected in palettes:
        window.evaluate_js(f"document.querySelector('input[name=appearance][value={palette}]').click()")
        if window.evaluate_js("document.documentElement.dataset.theme") != palette:
            raise RuntimeError(f"Could not select the {palette} palette.")
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            active = window.evaluate_js("document.documentElement.hasAttribute('data-native-glass')")
            if active == expected and matches(expected):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(f"Unexpected desktop glass backdrop or content opacity for {palette}.")
        if (
            palette == "glass"
            and expected
            and not window.evaluate_js("""
            (() => {
                const slider = document.getElementById('glass-transparency');
                if (slider.value !== '39' || getComputedStyle(slider.parentElement.parentElement).display === 'none') return false;
                slider.value = '100';
                slider.dispatchEvent(new Event('input'));
                slider.dispatchEvent(new Event('change'));
                const changed = getComputedStyle(document.documentElement).backgroundColor === 'rgba(8, 10, 11, 0)';
                const terminal = document.querySelector('#terminal-panes .xterm-scrollable-element');
                const clearTerminal = terminal && getComputedStyle(terminal).backgroundColor === 'rgba(0, 0, 0, 0)';
                document.getElementById('glass-reset').click();
                return changed && clearTerminal && slider.value === '39' &&
                    getComputedStyle(document.documentElement).backgroundColor === 'rgba(8, 10, 11, 0.61)';
            })()
        """)
        ):
            raise RuntimeError(
                "The frame transparency control did not update or reset the native glass tint."
            )
    print(f"Desktop backdrop and full foreground opacity passed (native glass supported: {supported}).")


def verify():
    start = webview.start
    create_window = webview.create_window
    checked = []

    def probe():
        window = webview.windows[0]
        try:
            if window.events.loaded.wait(15):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if window.evaluate_js("""
                        document.title === 'H-logsen' &&
                        document.documentElement.hasAttribute('data-workbench-desktop') &&
                        typeof window.pywebview?.api?.pick_project === 'function' &&
                        document.querySelector('#terminal-panes .live-shell')?.title &&
                        document.querySelector('#terminal-panes .terminal-connection')?.textContent === '' &&
                        !document.querySelector('#terminal-panes #terminal-log-content')
                    """):
                        if sys.platform == "win32":
                            if window.evaluate_js("document.getElementById('local-shell').value") != "CMD":
                                raise RuntimeError("Windows did not start with CMD selected.")
                        verify_desktop_glass(window)
                        checked.append(webview.renderer)
                        break
                    time.sleep(0.1)
        finally:
            window.destroy()

    def start_with_probe(**options):
        start(probe, **options)

    def create_for_test(*args, **options):
        return create_window(*args, hidden=sys.platform == "win32", **options)

    with TemporaryDirectory(prefix="h-logsen-desktop-") as state:
        arguments = ["h-logsen", "--desktop", "--state-dir", str(Path(state))]
        with (
            patch.object(webview, "start", start_with_probe),
            patch.object(webview, "create_window", create_for_test),
            patch.object(sys, "argv", arguments),
        ):
            main()
    expected = RENDERERS[sys.platform][1]
    if checked != [expected]:
        raise RuntimeError(f"Desktop UI did not initialize with {expected}.")
    print(f"Desktop workspace, native bridge and automatic shell connection passed on {expected}.")


if __name__ == "__main__":
    verify()
