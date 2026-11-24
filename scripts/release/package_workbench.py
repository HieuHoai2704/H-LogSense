"""Build source and platform download ZIPs from the same app snapshot."""

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
# Download ZIP root name -> repository source. macOS and Linux share the POSIX installers.
WINDOWS_FILES = {name: f"packaging/windows/{name}" for name in
                 ("Install-H-logsen.cmd", "Open-H-logsen.cmd", "CAI_DAT_WINDOWS.txt")}
POSIX_FILES = {name: f"packaging/posix/{name}" for name in
               ("Install-H-logsen.sh", "Open-H-logsen.sh", "CAI_DAT_MAC_LINUX.txt")}
PLATFORM_FILES = {"Windows": WINDOWS_FILES, "macOS": POSIX_FILES, "Linux": POSIX_FILES}
# cmd.exe can lose GOTO labels in LF-only batch files; POSIX shells reject CR.
CRLF_NAMES = {".cmd", ".bat", *WINDOWS_FILES}
EXECUTABLE_SUFFIXES = {".sh", ".command"}
ROOT_FILES = (".env.example", ".gitattributes", ".gitignore", "README.md", "config.py", "pyproject.toml",
              "requirements.txt", "requirements-workbench.txt", "requirements-workbench-extra.txt",
              "THIRD_PARTY_NOTICES.md", ".github/workflows/workbench-ci.yml", "packaging/README.md",
              "docs/README.md", "scripts/README.md",
              *WINDOWS_FILES.values(), *POSIX_FILES.values())
SOURCE_TREES = {
    "app": {".py", ".js", ".css", ".html", ".json", ".ico", ".png", ".svg"},
    "scripts": {".py"},
    "tests": {".py"},
    "migrations": {".py", ".ini", ".mako"},
    "docs/architecture": {".md"},
    "docs/database": {".md"},
    "docs/ml": {".md"},
    "docs/releases": {".md"},
}


def source_files(root):
    paths = {root / name for name in (*ROOT_FILES, "migrations/README", "data/raw/LOGHUB_LICENSE.txt",
                                     "docs/releases/measurements/university-mvp-v1/e2e.json")}
    for directory, suffixes in SOURCE_TREES.items():
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if directory == "app" and path.suffix == ".json" and path.parent != root / "app/locales":
                continue
            if path.is_file() and (path.suffix in suffixes or (directory == "app" and path.name == "LICENSE")):
                paths.add(path)
    result = []
    for path in sorted(paths):
        relative = path.relative_to(root)
        # Refuse links and junctions even when their target happens to be within the project.
        for part in (path, *path.parents[:len(relative.parts) - 1]):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ValueError(f"Refusing to package a link: {relative}")
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError(f"Source file exceeds 2 MiB: {relative}")
        result.append(relative)
    return result


def line_endings(data, crlf):
    data = data.replace(b"\r\n", b"\n")
    return data.replace(b"\n", b"\r\n") if crlf else data


def archive_file(archive, path, name):
    """Write one entry; installer scripts get platform line endings whatever the build checkout used."""
    entry = Path(name)
    if entry.suffix in EXECUTABLE_SUFFIXES:
        info = ZipInfo.from_file(path, name)
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(info, line_endings(path.read_bytes(), crlf=False), compress_type=ZIP_DEFLATED)
    elif entry.suffix in CRLF_NAMES or entry.name in CRLF_NAMES:
        info = ZipInfo.from_file(path, name)
        archive.writestr(info, line_endings(path.read_bytes(), crlf=True), compress_type=ZIP_DEFLATED)
    else:
        archive.write(path, name)


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    files = source_files(ROOT)
    with TemporaryDirectory(prefix="h-logsen-package-") as temporary:
        work = Path(temporary)
        source = work / "source"
        for relative in files:
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        wheels = work / "wheels"
        subprocess.run([sys.executable, "-m", "pip", "--isolated", "wheel", "--no-deps",
                        "--wheel-dir", str(wheels), str(source)], cwd=work, check=True)
        (wheel,) = wheels.glob("h_logsen-*-py3-none-any.whl")
        version = wheel.name.split("-")[1]
        stem = "H-logsen-" + version
        source_zip = output / f"{stem}-source.zip"
        downloads = {platform: output / f"{stem}-{platform}.zip" for platform in PLATFORM_FILES}
        packages = (source_zip, *downloads.values())
        checksum = output / f"{stem}-SHA256.txt"
        for path in (*packages, checksum):
            if path.exists():
                raise FileExistsError(f"Choose an empty output directory: {path}")
        with ZipFile(source_zip, "x", compression=ZIP_DEFLATED) as archive:
            for relative in files:
                archive_file(archive, source / relative, f"{stem}-source/{relative.as_posix()}")
        for platform, download in downloads.items():
            with ZipFile(download, "x", compression=ZIP_DEFLATED) as archive:
                prefix = f"{stem}-{platform}/"
                entries = {**PLATFORM_FILES[platform], "THIRD_PARTY_NOTICES.md": "THIRD_PARTY_NOTICES.md"}
                for name, relative in entries.items():
                    archive_file(archive, source / relative, prefix + name)
                    if platform == "macOS" and name.endswith(".sh"):
                        archive_file(archive, source / relative, prefix + Path(name).stem + ".command")
                archive.write(wheel, prefix + wheel.name)
        checksum.write_text("".join(f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                                    for path in packages), encoding="ascii")
    return (*packages, checksum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Directory for platform ZIPs and SHA-256 file.")
    args = parser.parse_args()
    for result in build(args.output.resolve()):
        print(result)


if __name__ == "__main__":
    main()
