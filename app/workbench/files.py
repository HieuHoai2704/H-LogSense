"""Bounded access to the operator-approved folder for each workspace."""

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path, PurePath
import re
import stat
from tempfile import NamedTemporaryFile, gettempdir
from threading import RLock
import time

MAX_TEXT = 1024 * 1024
TAIL_BYTES = 64 * 1024
SEARCH_ENTRIES = 12_000
SEARCH_RESULTS = 80
SKIPPED = {"node_modules", "__pycache__", "venv", "dist", "build"}
FORBIDDEN_EXTENSIONS = {".pem", ".key", ".pfx", ".p12"}
# Never opened even inside a selected project (SSH keys, agent trust files, credential stores).
PRIVATE_FILES = {
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ecdsa_sk",
    "id_ed25519",
    "id_ed25519_sk",
    "authorized_keys",
    "known_hosts",
    "credentials",
    "credentials.json",
    "secrets.json",
}
FEATURES = {"gpu", "ssh", "external_parsers"}
WORKSPACES = {"project", "analysis", "code"}
ACTIVE_ROOT = ContextVar("workbench_project_root", default=None)


class WorkspaceError(Exception):
    """English catalog key plus values; translate with ``translated()`` at the HTTP boundary."""

    def __init__(self, message, status=400, values=()):
        self.message = message
        self.values = tuple(values)
        super().__init__(
            re.sub(
                r"\{(\d+)\}",
                lambda match: (
                    str(self.values[int(match[1])]) if int(match[1]) < len(self.values) else match[0]
                ),
                message,
            )
        )
        self.status = status

    def translated(self):
        from app.i18n import translate

        return translate(self.message, *self.values)


def atomic_write(path, data, mode=None):
    """Replace from the same directory and preserve existing POSIX mode when supplied."""
    with NamedTemporaryFile(dir=path.parent, prefix=".h-logsen-", delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        if mode is not None:
            temp.chmod(stat.S_IMODE(mode))
        for attempt in range(4):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.03 * (attempt + 1))
    finally:
        temp.unlink(missing_ok=True)


def linked(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def component(name):
    return (
        name
        and name not in {".", ".."}
        and not name.startswith(".")
        and name.casefold() not in SKIPPED | PRIVATE_FILES
        and PurePath(name).suffix.casefold() not in FORBIDDEN_EXTENSIONS  # pure: no filesystem flavor needed
        and not any(char in name for char in ':\\/<>"|?*')
        and not any(ord(char) < 32 for char in name)
        and not name.endswith((" ", "."))
        and not windows_reserved(name)
        # NTFS 8.3 aliases (SSH~1 for .ssh, CREDEN~1.JSO) would bypass the name rules on Windows.
        and not (os.name == "nt" and re.search(r"~\d", name))
    )


# Device names Windows reserves in every folder, with or without an extension.
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CONIN$",
    "CONOUT$",
    *(f"{device}{number}" for device in ("COM", "LPT") for number in "123456789¹²³"),
}


def windows_reserved(name):
    # Same rule as PurePath.is_reserved(), which is deprecated and removed in Python 3.15.
    return name.partition(".")[0].rstrip(" ").upper() in WINDOWS_RESERVED


def encodable(value):
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def project_path(root, name, *, missing=False):
    if not isinstance(name, str) or len(name) > 1024 or not encodable(name):
        raise WorkspaceError("Invalid file path.")
    if name == "":
        return root
    path = root
    parts = name.split("/")
    for index, part in enumerate(parts):
        if not component(part):
            raise WorkspaceError("This path is outside the project.", 403)
        path /= part
        try:
            if linked(path):
                raise WorkspaceError("File and folder links are not opened.", 403)
        except FileNotFoundError:
            if missing and index == len(parts) - 1:
                return path
            raise WorkspaceError("The file or folder has changed.", 404) from None
    return path


def _real(path):
    return Path(os.path.realpath(path))


def protected_roots(state_directory):
    """(trees, exact) folders a project root may never be: trees also cover everything beneath them."""
    home = _real(Path.home())
    trees = {_real(state_directory)}
    exact = {home}
    if os.name == "nt":
        trees.update(
            _real(os.environ[name])
            for name in (
                "WINDIR",
                "PROGRAMFILES",
                "PROGRAMFILES(X86)",
                "PROGRAMDATA",
                "APPDATA",
                "LOCALAPPDATA",
            )
            if os.environ.get(name)
        )
        exact.update({home.parent})
    else:
        # realpath maps macOS /etc to /private/etc, so the rule holds on every platform.
        trees.update(
            _real(name)
            for name in (
                "/etc",
                "/proc",
                "/sys",
                "/dev",
                "/usr",
                "/bin",
                "/sbin",
                "/lib",
                "/lib32",
                "/lib64",
                "/boot",
                "/root",
                "/var/lib",
                "/var/log",
                "/System",
                "/Library",
            )
        )
        trees.add(home / "Library")
        exact.update(
            _real(name)
            for name in (
                "/home",
                "/Users",
                "/Volumes",
                "/var",
                "/run",
                "/run/media",
                "/opt",
                "/srv",
                "/mnt",
                "/media",
                "/tmp",
                "/private",
                "/private/var",
                "/snap",
            )
        )
    return trees, exact


def root_allowed(root, state_directory):
    """True when ``root`` (absolute, resolved) is a specific, non-system, non-hidden project folder."""
    root = _real(root)
    if root == Path(root.anchor):
        return False
    trees, exact = protected_roots(state_directory)
    temp = _real(gettempdir())
    if root in exact or root == temp:
        return False
    for tree in trees:
        # Windows keeps %TEMP% inside AppData\Local: folders inside the temp directory stay allowed.
        inside_temp = root.is_relative_to(temp) and temp.is_relative_to(tree) and temp != tree
        if (root == tree or root.is_relative_to(tree)) and not inside_temp:
            return False
    # Never an ancestor of the profile store: the profile itself would become editable.
    if _real(state_directory).is_relative_to(root):
        return False
    # Hidden folders anywhere in the path (~/.ssh, ~/.config/..., <checkout>/.local) hold private state.
    return not any(part.startswith(".") for part in root.parts[1:])


class ProjectStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "projects.json"
        self.lock_path = self.directory / "projects.lock"
        self.lock = RLock()
        self._read_state()

    @property
    def state(self):
        return self._read_state()

    def _read_state(self):
        state = {
            "root": None,
            "roots": {},
            "recent": [],
            "workspace_recents": {},
            "views": {},
            "interpreters": {},
            "features": dict.fromkeys(FEATURES, True),
        }
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("Expected a profile object")
            state.update(saved)
        except FileNotFoundError:
            pass
        except (ValueError, TypeError):
            raise WorkspaceError("Invalid project configuration. Check projects.json.") from None
        if state["root"]:
            for workspace in ("analysis", "code"):
                state["roots"].setdefault(workspace, state["root"])
                state["workspace_recents"].setdefault(workspace, [state["roots"][workspace]])
        return state

    @contextmanager
    def profile_lock(self):
        """Lock a stable file so replacing projects.json cannot invalidate the lock."""
        with self.lock, self.lock_path.open("a+b") as stream:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    @contextmanager
    def edit_profile(self):
        with self.profile_lock():
            state = self._read_state()
            yield state
            try:
                payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
            except UnicodeEncodeError:  # lone surrogates from a client: reject, keep the old profile
                raise WorkspaceError("Invalid text value.") from None
            atomic_write(self.path, payload)

    def select(self, value, workspace="project"):
        if workspace not in WORKSPACES:
            raise WorkspaceError("Invalid workspace.")
        if (
            not isinstance(value, str)
            or not value
            or "\0" in value
            or len(value) > 2048
            or not encodable(value)
        ):
            raise WorkspaceError("Enter the absolute path of the project folder.")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() or candidate.anchor.startswith("\\\\"):
            raise WorkspaceError("Choose a local folder by its absolute path.")
        try:
            root = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise WorkspaceError("The folder does not exist or cannot be accessed.", 404) from None
        if not root.is_dir() or not root_allowed(root, self.directory):
            raise WorkspaceError("Choose a specific project folder.")
        with self.edit_profile() as state:
            roots = state["roots"]
            recents = state["workspace_recents"]
            history = state["recent"] if workspace == "project" else recents.get(workspace, [])
            recent = [str(root)] + [item for item in history if item != str(root)]
            if workspace == "project":
                state["root"] = str(root)
                state["recent"] = recent[:12]
                for tab in ("analysis", "code"):
                    roots.setdefault(tab, str(root))
                    recents.setdefault(tab, [roots[tab]])
            else:
                roots[workspace] = str(root)
                recents[workspace] = recent[:12]
        return root

    def workspace_recent(self, workspace):
        state = self.state
        return state["recent"] if workspace == "project" else state["workspace_recents"].get(workspace, [])

    def workspace_view(self, workspace, project):
        return self.state["views"].get(workspace, {}).get(project, {})

    def save_workspace_view(self, workspace, project, changes):
        def relative(path):
            if (
                not isinstance(path, str)
                or len(path) > 1024
                or (path and not all(map(component, path.split("/"))))
            ):
                raise WorkspaceError("Invalid view path.")
            return path

        cleaned = {}
        file_key = {"project": "log", "analysis": "analysis_file", "code": None}[workspace]
        for key, value in changes.items():
            if key == "expanded" and isinstance(value, list) and len(value) <= 32:
                cleaned[key] = list(dict.fromkeys(filter(None, map(relative, value))))
            elif key == "selected" or key == file_key:
                cleaned[key] = relative(value)
            elif (
                key == "analysis_format"
                and workspace == "analysis"
                and value
                in ("csv", "jsonl", "parquet", "hdfs", "openstack", "jsonl-log", "csv-log", "evaluation")
            ):
                cleaned[key] = value
            elif key == "editor" and workspace == "code" and isinstance(value, dict):
                split, active, ratio = value.get("split"), value.get("active"), value.get("ratio")
                if (
                    type(split) is not bool
                    or active not in ("left", "right")
                    or type(ratio) is not int
                    or not 25 <= ratio <= 75
                ):
                    raise WorkspaceError("Invalid Code layout.")
                cleaned[key] = {
                    "left": relative(value.get("left")),
                    "right": relative(value.get("right")) if split else "",
                    "split": split,
                    "active": active if split else "left",
                    "ratio": ratio,
                }
            else:
                raise WorkspaceError("Invalid view state.")

        with self.edit_profile() as state:
            views = state["views"]
            entries = views.get(workspace, {})
            updated = {**entries.pop(project, {}), **cleaned}
            entries[project] = updated
            views[workspace] = dict(list(entries.items())[-24:])
        return updated

    def root(self):
        value = ACTIVE_ROOT.get()
        return self._checked_root(value) if value else self.workspace_root("project")

    def workspace_root(self, workspace):
        if workspace not in WORKSPACES:
            raise WorkspaceError("Invalid workspace.")
        state = self.state
        value = state["root"] if workspace == "project" else state["roots"].get(workspace)
        return self._checked_root(value)

    def _checked_root(self, value):
        # Re-apply the selection rules: projects.json is a plain file and may have been edited.
        if isinstance(value, str) and value:
            root = Path(value)
            if (
                root.is_absolute()
                and root.is_dir()
                and not linked(root)
                and root.resolve() == root
                and root_allowed(root, self.directory)
            ):
                return root
        raise WorkspaceError("Choose a project folder first.", 409)

    def resolve(self, name, *, missing=False, root=None):
        return project_path(root or self.root(), name, missing=missing)

    def listing(self, name, start=0):
        folder = self.resolve(name)
        if not folder.is_dir():
            raise WorkspaceError("The path is not a folder.")
        rows = []
        with os.scandir(folder) as entries:
            for entry in entries:
                if not component(entry.name) or linked(Path(entry.path)):
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if is_dir or entry.is_file(follow_symlinks=False):
                    rows.append({"name": entry.name, "directory": is_dir})
                if len(rows) > 10_000:
                    raise WorkspaceError(
                        "The folder exceeds the 10,000-entry limit. Choose a subfolder.", 422
                    )
        rows.sort(key=lambda item: (not item["directory"], item["name"].casefold(), item["name"]))
        return {
            "entries": rows[start : start + 300],
            "next": start + 300 if len(rows) > start + 300 else None,
        }

    def search(self, query):
        needle = query.strip().replace("\\", "/").casefold()
        if not needle or len(needle) > 120 or any(ord(char) < 32 for char in needle):
            raise WorkspaceError("Enter 1 to 120 characters to search the project.")
        root = self.root()
        folders = deque([root])
        matches = []
        scanned = 0
        partial = False
        match_path = "/" in needle
        while folders and scanned < SEARCH_ENTRIES and len(matches) <= SEARCH_RESULTS:
            folder = folders.popleft()
            try:
                if linked(folder) or folder.resolve(strict=True) != folder:
                    continue
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if scanned >= SEARCH_ENTRIES or len(matches) > SEARCH_RESULTS:
                            partial = True
                            break
                        scanned += 1
                        if not component(entry.name):
                            continue
                        path = Path(entry.path)
                        try:
                            if linked(path):
                                continue
                            directory = entry.is_dir(follow_symlinks=False)
                            if not directory and not entry.is_file(follow_symlinks=False):
                                continue
                        except FileNotFoundError:
                            continue
                        except OSError:
                            partial = True
                            continue
                        if directory:
                            folders.append(path)
                        relative = path.relative_to(root).as_posix()
                        if needle in (relative if match_path else entry.name).casefold():
                            matches.append({"name": entry.name, "path": relative, "directory": directory})
            except OSError:
                partial = True
        partial = partial or bool(folders) or len(matches) > SEARCH_RESULTS
        matches = matches[:SEARCH_RESULTS]
        matches.sort(key=lambda item: (not item["directory"], item["path"].casefold(), item["path"]))
        return {"entries": matches, "partial": partial, "scanned": scanned}

    def read(self, name):
        path = self.resolve(name)
        if not path.is_file():
            raise WorkspaceError("Choose a text file.")
        with path.open("rb") as stream:
            data = stream.read(MAX_TEXT + 1)
        if len(data) > MAX_TEXT or b"\0" in data:
            raise WorkspaceError("The editor only opens UTF-8 files up to 1 MiB.", 422)
        try:
            return {"text": data.decode("utf-8-sig"), "revision": hashlib.sha256(data).hexdigest()}
        except UnicodeDecodeError:
            raise WorkspaceError("The file is not UTF-8 encoded.", 422) from None

    def write(self, name, text, revision):
        if not isinstance(text, str) or not isinstance(revision, str) or "\0" in text:
            raise WorkspaceError("Invalid file content or revision.")
        with self.profile_lock():
            path = self.resolve(name)
            current = self.read(name)
            if current["revision"] != revision:
                raise WorkspaceError("The file changed on disk. Reopen it before saving.", 409)
            with path.open("rb") as stream:
                prefix = stream.read(3)
            # The textarea uses LF. Keep the source's newline style and optional BOM.
            normalized = text.replace("\r\n", "\n")
            if "\r\n" in current["text"] and "\n" not in current["text"].replace("\r\n", ""):
                normalized = normalized.replace("\n", "\r\n")
            try:
                data = (b"\xef\xbb\xbf" if prefix == b"\xef\xbb\xbf" else b"") + normalized.encode("utf-8")
            except UnicodeEncodeError:
                raise WorkspaceError("The content cannot be encoded as UTF-8.", 422) from None
            if len(data) > MAX_TEXT:
                raise WorkspaceError("The file exceeds the 1 MiB limit.", 413)
            atomic_write(path, data, path.stat().st_mode)
            return {"revision": hashlib.sha256(data).hexdigest()}

    def manage(self, name, action, target=None):
        if not isinstance(name, str) or not name:
            raise WorkspaceError("The root folder cannot be changed from the file tree.")
        with self.profile_lock():
            if action == "directory":
                self.resolve(name, missing=True).mkdir()
            elif action == "file":
                with self.resolve(name, missing=True).open("xb"):
                    pass
            elif action == "rename":
                if not isinstance(target, str) or not target:
                    raise WorkspaceError("Invalid target path.")
                source = self.resolve(name)
                destination = self.resolve(target, missing=True)
                if destination.exists():
                    raise WorkspaceError("The target name already exists.", 409)
                source.rename(destination)
            else:
                raise WorkspaceError("Invalid folder action.")


def tail(path, offset=None, stamp=None):
    """Bounded snapshots; client replaces the view on rotations or cursor loss."""
    if not path.is_file():
        raise WorkspaceError("Choose a log file.", 404)
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        identity = f"{info.st_dev}:{info.st_ino}"
        if offset == info.st_size and stamp == f"{identity}:{info.st_mtime_ns}":
            return {"changed": False, "offset": offset, "stamp": stamp}
        if not info.st_size:
            data = b""
        else:
            start = max(0, info.st_size - TAIL_BYTES)
            stream.seek(start)
            data = stream.read(info.st_size - start)
            if start and b"\n" in data:
                data = data.split(b"\n", 1)[1]
    return {
        "changed": True,
        "text": data.decode("utf-8", "replace"),
        "offset": info.st_size,
        "stamp": f"{identity}:{info.st_mtime_ns}",
    }
