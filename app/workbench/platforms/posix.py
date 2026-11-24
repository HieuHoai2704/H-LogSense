"""POSIX terminal backend shared by macOS, Linux and other Unix systems."""

import codecs
import os
from pathlib import Path
import signal
import subprocess
import sys

SHELL_DIRECTORIES = ("/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin")


def shell_profiles():
    """Shell name -> argv. $SHELL comes first when it is an executable regular file."""
    import os

    profiles = {}
    preferred = os.environ.get("SHELL", "")
    if preferred and os.path.isabs(preferred) and os.access(preferred, os.X_OK) and Path(preferred).is_file():
        profiles[Path(preferred).name] = [preferred]
    for name in ("zsh", "bash", "fish", "sh"):
        if name in profiles:
            continue
        for directory in SHELL_DIRECTORIES:
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                profiles[name] = [str(candidate)]
                break
    return profiles


class PosixTerminal:
    def __init__(self, command, directory, environment):
        import pty

        self.fd, slave = pty.openpty()
        self.decoder = codecs.getincrementaldecoder("utf-8")("replace")
        launcher = (
            "import fcntl, os, sys, termios;"
            "fcntl.ioctl(0, termios.TIOCSCTTY, 0);"
            "os.execv(sys.argv[1], sys.argv[1:])"
        )
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-I", "-c", launcher, *command],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=directory,
                env=environment,
                start_new_session=True,
            )
            self.setwinsize(24, 80)
        except BaseException:
            os.close(self.fd)
            if hasattr(self, "process"):
                self.process.kill()
                self.process.wait()
            raise
        finally:
            os.close(slave)

    def read(self, size):
        data = os.read(self.fd, size)
        if not data:
            raise EOFError
        return self.decoder.decode(data)

    def write(self, value):
        remaining = memoryview(value.encode("utf-8"))
        while remaining:
            remaining = remaining[os.write(self.fd, remaining) :]

    def setwinsize(self, rows, cols):
        import fcntl
        import struct
        import termios

        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def close(self):
        try:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGHUP)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=2)
        finally:
            os.close(self.fd)


def open_terminal(command, directory, environment):
    return PosixTerminal(command, directory, environment)


def close_terminal(process):
    process.close()
