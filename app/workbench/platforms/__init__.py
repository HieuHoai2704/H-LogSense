"""Operating-system specific code for the desktop workbench.

`current` is the backend for this interpreter. Every backend provides:

- shell_profiles(), open_terminal(command, directory, environment), close_terminal(process)
- desktop_options() -> (create_window options, webview.start options)   [windows, macos, linux]
- set_window_glass(window, enabled) -> bool                            [windows, macos, linux]

Everything else in app/workbench is shared by all platforms. One-line portability checks
(file locking, virtual-environment layout, process flags) stay next to the code they guard.
"""

import importlib
import sys

_BACKENDS = {"win32": "windows", "darwin": "macos"}


def backend_name():
    if sys.platform in _BACKENDS:
        return _BACKENDS[sys.platform]
    # Other Unix systems get terminals only; desktop mode is not offered there.
    return "linux" if sys.platform.startswith("linux") else "posix"


def __getattr__(name):
    # Loaded on first use, so `python -m app.workbench.platforms.<os>` does not import itself twice.
    if name == "current":
        return importlib.import_module(f"{__name__}.{backend_name()}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
