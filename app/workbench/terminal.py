"""Bounded, independent terminal sessions for the local workbench."""

import codecs
from collections import deque
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
from threading import Condition, Lock, Thread
import time

from .files import WorkspaceError

MAX_BUFFER = 256 * 1024
ENVIRONMENT = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP",
    "USERPROFILE", "USERNAME", "HOME", "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL",
    # Windows NVML uses these system paths even when nvidia-smi is in System32.
    "PROGRAMFILES", "PROGRAMW6432",
    "LOGNAME", "USER", "TERM", "SSH_AUTH_SOCK", "XDG_RUNTIME_DIR", "TZ",
}


def child_environment():
    return {key: value for key, value in os.environ.items() if key.upper() in ENVIRONMENT}


def terminal_environment(interpreter):
    environment = {**child_environment(), "TERM": "xterm-256color"}
    if interpreter is not None:
        directory = interpreter.parent
        path_key = next((key for key in environment if key.upper() == "PATH"), "PATH")
        inherited = environment.pop(path_key, "")
        environment["PATH"] = os.pathsep.join(part for part in (str(directory), inherited) if part)
        if (directory.parent / "pyvenv.cfg").is_file():
            environment["VIRTUAL_ENV"] = str(directory.parent)
    return environment


def profiles():
    if os.name == "nt":
        system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
        options = {"PowerShell": [str(system / "WindowsPowerShell/v1.0/powershell.exe"), "-NoLogo", "-NoProfile"],
                   "CMD": [str(system / "cmd.exe"), "/D"]}
    else:
        options = {name: [str(Path("/bin") / name)] for name in ("zsh", "bash", "sh")}
    return {name: command for name, command in options.items() if Path(command[0]).is_file()}


def ssh_command(host, user, port):
    if (not isinstance(host, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]{0,252}", host)
            or not isinstance(user, str) or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,63}", user)
            or type(port) is not int or not 1 <= port <= 65535):
        raise WorkspaceError("Check the SSH host, user and port.")
    executable = shutil.which("ssh")
    if not executable:
        raise WorkspaceError("OpenSSH client is not installed.", 503)
    return [executable, "-F", "none", "-o", "StrictHostKeyChecking=yes", "-o", "ClearAllForwardings=yes",
            "-o", "ForwardAgent=no", "-o", "ForwardX11=no", "-o", "ConnectTimeout=10",
            "-tt", "-p", str(port), "-l", user, "--", host]


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
                stdin=slave, stdout=slave, stderr=slave, cwd=directory,
                env=environment, start_new_session=True,
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
            remaining = remaining[os.write(self.fd, remaining):]

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


class Session:
    def __init__(self, command, root, interpreter=None):
        env = terminal_environment(interpreter)
        if os.name == "nt":
            try:
                from winpty import PtyProcess
            except ImportError:
                raise WorkspaceError("Install requirements-workbench.txt to enable ConPTY.", 503) from None
            self.process = PtyProcess.spawn(command, cwd=str(root), env=env)
        else:
            self.process = PosixTerminal(command, root, env)
        self.buffer = deque()
        self.length = 0
        self.offset = 0
        self.closed = False
        self.finished = False
        self.touched = time.monotonic()
        self.lock = Condition()
        self.input_lock = Lock()
        Thread(target=self.read_loop, daemon=True).start()

    def read_loop(self):
        try:
            while not self.closed:
                data = self.process.read(4096)
                if not data:
                    continue
                with self.lock:
                    self.buffer.append(data)
                    self.offset += len(data)
                    self.length += len(data)
                    while self.length > MAX_BUFFER:
                        self.length -= len(self.buffer.popleft())
                    self.lock.notify_all()
        except (EOFError, OSError, RuntimeError, ValueError):
            pass
        finally:
            with self.lock:
                self.finished = True
                self.lock.notify_all()

    def snapshot(self, offset, wait_ms=0):
        with self.lock:
            if wait_ms and offset == self.offset:
                self.lock.wait_for(lambda: self.offset != offset or self.finished or self.closed, wait_ms / 1000)
            if self.closed:
                raise WorkspaceError("The terminal session no longer exists.", 404)
            oldest = self.offset - self.length
            reset = offset < oldest or offset > self.offset
            start = oldest if reset else offset
            consumed = oldest
            chunks = []
            for chunk in self.buffer:
                if consumed + len(chunk) > start:
                    chunks.append(chunk[max(0, start - consumed):])
                consumed += len(chunk)
            return {"text": "".join(chunks), "start_offset": start, "offset": self.offset,
                    "reset": reset, "finished": self.finished}

    def write(self, value):
        with self.input_lock:
            if self.finished or self.closed:
                raise WorkspaceError("The terminal session has ended.", 409)
            try:
                self.process.write(value)
            except (EOFError, OSError, RuntimeError, ValueError):
                raise WorkspaceError("Could not send data to the terminal session.", 409) from None

    def resize(self, rows, columns):
        with self.input_lock:
            if self.finished or self.closed:
                return
            try:
                self.process.setwinsize(rows, columns)
            except (OSError, RuntimeError, ValueError):
                raise WorkspaceError("Could not resize the terminal session.", 409) from None

    def close(self):
        with self.input_lock:
            with self.lock:
                if self.closed:
                    return
                self.closed = True
                self.lock.notify_all()
            if os.name == "nt":
                self.process.close(force=True)
            else:
                self.process.close()


class Terminals:
    def __init__(self):
        self.lock = Lock()
        self.sessions = {}

    def add(self, command, root, interpreter=None):
        with self.lock:
            expired = [key for key, session in self.sessions.items() if time.monotonic() - session.touched > 1800]
            for key in expired:
                self.sessions.pop(key).close()
            if len(self.sessions) >= 6:
                raise WorkspaceError("Close a session before opening another. Up to 6 sessions.", 429)
            session_id = secrets.token_hex(16)
            self.sessions[session_id] = Session(command, root, interpreter)
            return session_id

    def get(self, session_id):
        with self.lock:
            session = self.sessions.get(session_id)
            if not session:
                raise WorkspaceError("The terminal session no longer exists.", 404)
            session.touched = time.monotonic()
            return session

    def close(self, session_id):
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if session:
            session.close()

    def shutdown(self):
        with self.lock:
            keys = list(self.sessions)
        for key in keys:
            self.close(key)
