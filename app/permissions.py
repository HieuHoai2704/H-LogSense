"""Owner-only files and folders for credentials, uploads and backups, verified after creation.

chmod is a silent no-op on filesystems without POSIX modes (NTFS, exFAT or FAT mounted on Linux or
macOS), so every helper reads the mode back. By default an exposed location produces one warning;
with ``LOGSENSE_STRICT_PERMISSIONS=1`` it raises ``InsecurePermissions`` instead. Windows relies on
ACLs (uploads apply them with icacls), so mode bits are not checked there.
"""

import os
from pathlib import Path
from typing import BinaryIO
import warnings


class InsecurePermissions(PermissionError):
    """A private path is readable or writable by other accounts."""


_warned: set[str] = set()


def strict() -> bool:
    return os.environ.get("LOGSENSE_STRICT_PERMISSIONS") == "1"


def check_private(path: str | os.PathLike[str]) -> bool:
    """Return True when only the owner can access ``path``; warn once per folder (or raise in strict mode)."""
    path = Path(path)
    if os.name == "nt" or not path.stat().st_mode & 0o077:
        return True
    message = (
        f"{path} is accessible to other accounts because its filesystem ignores POSIX permissions. "
        "Keep private data on an owner-only filesystem or set LOGSENSE_LOCAL_DIR to a folder in your "
        "home directory."
    )
    if strict():
        raise InsecurePermissions(message)
    folder = str(path if path.is_dir() else path.parent)
    if folder not in _warned:
        _warned.add(folder)
        warnings.warn(message, RuntimeWarning, stacklevel=2)
    return False


def make_private_dir(path: str | os.PathLike[str], *, exist_ok: bool = True) -> Path:
    """Create (or tighten) an owner-only directory and verify the result."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=exist_ok, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    check_private(path)
    return path


def write_private(path: str | os.PathLike[str], data: str | bytes) -> Path:
    """Atomically replace ``path`` with owner-only content (text is written as UTF-8)."""
    path = Path(path)
    payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    check_private(path)
    return path


def open_private(path: str | os.PathLike[str]) -> BinaryIO:
    """Create a new owner-only file for streaming output; refuses to overwrite an existing file."""
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    stream = os.fdopen(descriptor, "wb")
    try:
        check_private(path)
    except BaseException:
        stream.close()
        path.unlink(missing_ok=True)
        raise
    return stream
