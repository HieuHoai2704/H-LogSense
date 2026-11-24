"""Operating-system specific terminal backends for the workbench.

`current` is the backend for this interpreter. Every backend provides
shell_profiles(), open_terminal(command, directory, environment) and close_terminal(process):
ConPTY on Windows, a POSIX pseudo-terminal everywhere else. H-logsen runs as a local web
application in the browser, so nothing else here depends on the operating system.
"""

import importlib
import sys


def backend_name():
    return "windows" if sys.platform == "win32" else "posix"


def __getattr__(name):
    # Loaded on first use, so `python -m app.workbench.platforms.<os>` does not import itself twice.
    if name == "current":
        return importlib.import_module(f"{__name__}.{backend_name()}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
