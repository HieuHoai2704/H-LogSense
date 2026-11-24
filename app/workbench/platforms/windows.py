"""Windows terminals through ConPTY (pywinpty)."""

import os
from pathlib import Path

from ..files import WorkspaceError


def shell_profiles():
    # Environment names are case-insensitive on Windows.
    system = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
    return {
        "PowerShell": [str(system / "WindowsPowerShell/v1.0/powershell.exe"), "-NoLogo", "-NoProfile"],
        "CMD": [str(system / "cmd.exe"), "/D"],
    }


def open_terminal(command, directory, environment):
    try:
        from winpty import PtyProcess
    except ImportError:
        raise WorkspaceError("Install pywinpty to enable ConPTY.", 503) from None
    return PtyProcess.spawn(command, cwd=str(directory), env=environment)


def close_terminal(process):
    process.close(force=True)
