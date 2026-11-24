"""Bounded access to the operator-approved folder for each workspace."""

from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import stat
from tempfile import NamedTemporaryFile
import time
from threading import RLock

MAX_TEXT = 1024 * 1024
TAIL_BYTES = 64 * 1024
SEARCH_ENTRIES = 12_000
SEARCH_RESULTS = 80
SKIPPED = {"node_modules", "__pycache__", "venv", "dist", "build"}
FORBIDDEN_EXTENSIONS = {".pem", ".key", ".pfx", ".p12"}
PRIVATE_FILES = {"id_rsa", "id_ed25519", "credentials.json", "secrets.json"}
FEATURES = {"gpu", "ssh", "external_parsers"}
WORKSPACES = {"project", "analysis", "code"}
ACTIVE_ROOT = ContextVar("workbench_project_root", default=None)


class WorkspaceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


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
        name and name not in {".", ".."} and not name.startswith(".")
        and name.casefold() not in SKIPPED | PRIVATE_FILES
        and Path(name).suffix.casefold() not in FORBIDDEN_EXTENSIONS
        and not any(char in name for char in ':\\/<>"|?*' )
        and not any(ord(char) < 32 for char in name)
        and not name.endswith((" ", "."))
        and not PureWindowsPath(name).is_reserved()
    )


def project_path(root, name, *, missing=False):
    if not isinstance(name, str) or len(name) > 1024:
        raise WorkspaceError("Đường dẫn tệp không hợp lệ.")
    if name == "":
        return root
    path = root
    parts = name.split("/")
    for index, part in enumerate(parts):
        if not component(part):
            raise WorkspaceError("Đường dẫn này nằm ngoài phạm vi dự án.", 403)
        path /= part
        try:
            if linked(path):
                raise WorkspaceError("Không mở liên kết tệp hoặc thư mục.", 403)
        except FileNotFoundError:
            if missing and index == len(parts) - 1:
                return path
            raise WorkspaceError("Tệp hoặc thư mục đã thay đổi.", 404) from None
    return path


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
        state = {"root": None, "roots": {}, "recent": [], "workspace_recents": {}, "views": {},
                 "interpreters": {}, "features": dict.fromkeys(FEATURES, True)}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("Expected a profile object")
            state.update(saved)
        except FileNotFoundError:
            pass
        except (ValueError, TypeError):
            raise WorkspaceError("Cấu hình dự án không hợp lệ. Hãy kiểm tra projects.json.") from None
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
            atomic_write(self.path, json.dumps(state, ensure_ascii=False).encode("utf-8"))

    def select(self, value, workspace="project"):
        if workspace not in WORKSPACES:
            raise WorkspaceError("Không gian làm việc không hợp lệ.")
        if not isinstance(value, str) or not value or "\0" in value or len(value) > 2048:
            raise WorkspaceError("Nhập đường dẫn tuyệt đối của thư mục dự án.")
        candidate = Path(value).expanduser()
        if not candidate.is_absolute() or candidate.anchor.startswith("\\\\"):
            raise WorkspaceError("Chọn một thư mục cục bộ bằng đường dẫn tuyệt đối.")
        try:
            root = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            raise WorkspaceError("Thư mục không tồn tại hoặc không truy cập được.", 404) from None
        protected = {Path.home().resolve(), Path(root.anchor), self.directory}
        if os.name == "nt":
            protected.update(Path(os.environ[name]).resolve() for name in ("WINDIR", "PROGRAMFILES", "PROGRAMDATA") if name in os.environ)
        else:
            protected.update(map(Path, ("/etc", "/proc", "/sys", "/dev", "/usr", "/bin", "/sbin")))
        if not root.is_dir() or any(root == path or (path != Path(root.anchor) and path != Path.home().resolve()
                                                  and root.is_relative_to(path)) for path in protected):
            raise WorkspaceError("Chọn thư mục cụ thể của dự án.")
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
            if not isinstance(path, str) or len(path) > 1024 or (path and not all(map(component, path.split("/")))):
                raise WorkspaceError("Đường dẫn giao diện không hợp lệ.")
            return path

        cleaned = {}
        file_key = {"project": "log", "analysis": "analysis_file", "code": None}[workspace]
        for key, value in changes.items():
            if key == "expanded" and isinstance(value, list) and len(value) <= 32:
                cleaned[key] = list(dict.fromkeys(filter(None, map(relative, value))))
            elif key == "selected" or key == file_key:
                cleaned[key] = relative(value)
            elif key == "analysis_format" and workspace == "analysis" and value in (
                    "csv", "jsonl", "parquet", "hdfs", "openstack", "jsonl-log", "csv-log", "evaluation"):
                cleaned[key] = value
            elif key == "editor" and workspace == "code" and isinstance(value, dict):
                split, active, ratio = value.get("split"), value.get("active"), value.get("ratio")
                if type(split) is not bool or active not in ("left", "right") or type(ratio) is not int or not 25 <= ratio <= 75:
                    raise WorkspaceError("Bố cục Code không hợp lệ.")
                cleaned[key] = {"left": relative(value.get("left")), "right": relative(value.get("right")) if split else "",
                                "split": split, "active": active if split else "left", "ratio": ratio}
            else:
                raise WorkspaceError("Trạng thái giao diện không hợp lệ.")

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
            raise WorkspaceError("Không gian làm việc không hợp lệ.")
        state = self.state
        value = state["root"] if workspace == "project" else state["roots"].get(workspace)
        return self._checked_root(value)

    @staticmethod
    def _checked_root(value):
        if value:
            root = Path(value)
            if root.is_dir() and not linked(root) and root.resolve() == root:
                return root
        raise WorkspaceError("Chọn thư mục dự án trước.", 409)

    def resolve(self, name, *, missing=False, root=None):
        return project_path(root or self.root(), name, missing=missing)

    def listing(self, name, start=0):
        folder = self.resolve(name)
        if not folder.is_dir():
            raise WorkspaceError("Đường dẫn không phải thư mục.")
        rows = []
        with os.scandir(folder) as entries:
            for entry in entries:
                if not component(entry.name) or linked(Path(entry.path)):
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if is_dir or entry.is_file(follow_symlinks=False):
                    rows.append({"name": entry.name, "directory": is_dir})
                if len(rows) > 10_000:
                    raise WorkspaceError("Thư mục vượt giới hạn 10.000 mục. Chọn thư mục con.", 422)
        rows.sort(key=lambda item: (not item["directory"], item["name"].casefold(), item["name"]))
        return {"entries": rows[start:start + 300], "next": start + 300 if len(rows) > start + 300 else None}

    def search(self, query):
        needle = query.strip().replace("\\", "/").casefold()
        if not needle or len(needle) > 120 or any(ord(char) < 32 for char in needle):
            raise WorkspaceError("Nhập từ 1 đến 120 ký tự để tìm trong dự án.")
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
            raise WorkspaceError("Chọn một tệp văn bản.")
        with path.open("rb") as stream:
            data = stream.read(MAX_TEXT + 1)
        if len(data) > MAX_TEXT or b"\0" in data:
            raise WorkspaceError("Trình sửa chỉ mở tệp UTF-8 tối đa 1 MiB.", 422)
        try:
            return {"text": data.decode("utf-8-sig"), "revision": hashlib.sha256(data).hexdigest()}
        except UnicodeDecodeError:
            raise WorkspaceError("Tệp không dùng mã hóa UTF-8.", 422) from None

    def write(self, name, text, revision):
        if not isinstance(text, str) or not isinstance(revision, str) or "\0" in text:
            raise WorkspaceError("Nội dung hoặc phiên bản tệp không hợp lệ.")
        with self.profile_lock():
            path = self.resolve(name)
            current = self.read(name)
            if current["revision"] != revision:
                raise WorkspaceError("Tệp đã thay đổi trên đĩa. Mở lại trước khi lưu.", 409)
            with path.open("rb") as stream:
                prefix = stream.read(3)
            # The textarea uses LF. Keep the source's newline style and optional BOM.
            normalized = text.replace("\r\n", "\n")
            if "\r\n" in current["text"] and "\n" not in current["text"].replace("\r\n", ""):
                normalized = normalized.replace("\n", "\r\n")
            try:
                data = (b"\xef\xbb\xbf" if prefix == b"\xef\xbb\xbf" else b"") + normalized.encode("utf-8")
            except UnicodeEncodeError:
                raise WorkspaceError("Nội dung không dùng được với UTF-8.", 422) from None
            if len(data) > MAX_TEXT:
                raise WorkspaceError("Tệp vượt giới hạn 1 MiB.", 413)
            atomic_write(path, data, path.stat().st_mode)
            return {"revision": hashlib.sha256(data).hexdigest()}

    def manage(self, name, action, target=None):
        if not isinstance(name, str) or not name:
            raise WorkspaceError("Không thay đổi thư mục gốc từ cây tệp.")
        with self.profile_lock():
            if action == "directory":
                self.resolve(name, missing=True).mkdir()
            elif action == "file":
                with self.resolve(name, missing=True).open("xb"):
                    pass
            elif action == "rename":
                if not isinstance(target, str) or not target:
                    raise WorkspaceError("Đường dẫn đích không hợp lệ.")
                source = self.resolve(name)
                destination = self.resolve(target, missing=True)
                if destination.exists():
                    raise WorkspaceError("Tên đích đã tồn tại.", 409)
                source.rename(destination)
            else:
                raise WorkspaceError("Thao tác thư mục không hợp lệ.")


def tail(path, offset=None, stamp=None):
    """Bounded snapshots; client replaces the view on rotations or cursor loss."""
    if not path.is_file():
        raise WorkspaceError("Chọn tệp log.", 404)
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
    return {"changed": True, "text": data.decode("utf-8", "replace"),
            "offset": info.st_size, "stamp": f"{identity}:{info.st_mtime_ns}"}
