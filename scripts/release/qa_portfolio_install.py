"""Verify the platform ZIP and archived source in a fresh environment."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
import venv
from zipfile import ZipFile

SMOKE = """
from importlib.metadata import version
from pathlib import Path
import sys

from app import create_app
from app.workbench.api import mount

import app.workbench
assert Path(app.workbench.__file__).is_relative_to(sys.prefix)
root = Path.cwd() / 'training-project'
root.mkdir()
(root / 'train.log').write_text('INFO epoch=1', encoding='utf-8')
app = create_app({'TESTING': True})
local = mount(app, 'clean-install-test', root.parent / 'profile')
client = app.test_client()
base = 'http://127.0.0.1'
headers = {'Authorization': 'Bearer clean-install-test'}
assert client.get('/', base_url=base).status_code == 200
assert client.get('/api/local/v1/session', base_url=base).status_code == 403
selected = client.post('/api/local/v1/project', base_url=base, headers=headers, json={'path': str(root)})
assert selected.status_code == 200, selected.json
headers['X-Project'] = selected.json['project']
tree = client.get('/api/local/v1/tree', base_url=base, headers=headers)
assert tree.status_code == 200 and 'train.log' in tree.get_data(as_text=True)
vendor = Path(app.static_folder) / 'vendor'
assert all((vendor / item / 'LICENSE').is_file() for item in ('xterm', 'xterm-fit', 'moment', 'highlight'))
local['terminals'].shutdown()
print(version('H-logsen'))
"""


def verify(directory, desktop=False):
    (source_zip,) = directory.glob("H-logsen-*-source.zip")
    checksum_file = directory / source_zip.name.replace("-source.zip", "-SHA256.txt")
    digests = dict(reversed(line.split(maxsplit=1)) for line in checksum_file.read_text("ascii").splitlines())
    platform_name = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}[sys.platform]
    install_zip = directory / source_zip.name.replace("-source.zip", f"-{platform_name}.zip")
    for archive_path in (source_zip, install_zip):
        if sha256(archive_path.read_bytes()).hexdigest() != digests[archive_path.name]:
            raise ValueError(f"Checksum mismatch: {archive_path.name}")
    with TemporaryDirectory(prefix="h-logsen-clean-") as temporary:
        work = Path(temporary)
        source = work / source_zip.stem
        with ZipFile(source_zip) as archive:
            archive.extractall(work)
        install = work / install_zip.stem
        with ZipFile(install_zip) as archive:
            if sys.platform == "darwin":
                for name in ("Install-H-logsen.command", "Open-H-logsen.command"):
                    script = archive.getinfo(f"{install.name}/{name}")
                    if not (script.create_system == 3 and script.external_attr >> 16 & 0o111):
                        raise ValueError(f"Missing execute permission: {name}")
            archive.extractall(work)
        binary = install / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        if os.name == "nt":
            venv.create(binary.parent, with_pip=True)
            (wheel,) = install.glob("h_logsen-*.whl")
            subprocess.run([python, "-I", "-m", "pip", "--isolated", "install", wheel], cwd=work, check=True)
        else:
            # Keep the Linux application-menu launcher inside the temporary directory.
            installer_env = {
                **os.environ,
                "H_LOGSEN_PYTHON": sys.executable,
                "XDG_DATA_HOME": str(work / "xdg-data"),
            }
            subprocess.run(["sh", install / "Install-H-logsen.sh"], cwd=work, env=installer_env, check=True)
            subprocess.run(["sh", install / "Open-H-logsen.sh", "--help"], cwd=work, check=True)
            if sys.platform == "linux":
                launcher = work / "xdg-data" / "applications" / "h-logsen.desktop"
                if str(python.absolute()) not in launcher.read_text("utf-8"):
                    raise ValueError("The Linux launcher does not start the installed environment.")
        if sys.platform == "linux":
            # The Linux venv uses --system-site-packages; distribution packages are out of scope.
            subprocess.run(
                [python, "-I", "-m", "app.workbench.platforms.linux", "check"], cwd=work, check=True
            )
        else:
            subprocess.run([python, "-I", "-m", "pip", "check"], cwd=work, check=True)
        subprocess.run([python, "-I", "-m", "app.workbench", "--help"], cwd=work, check=True)
        version = subprocess.check_output([python, "-I", "-c", SMOKE], cwd=work, text=True).strip()
        subprocess.run([python, "-m", "unittest", "discover", "-s", "tests"], cwd=source, check=True)
        if desktop:
            subprocess.run(
                [python, "-I", source / "scripts/qa/qa_workbench_desktop.py"],
                cwd=work,
                check=True,
                timeout=45,
            )
        packages = subprocess.check_output(
            [python, "-I", "-m", "pip", "list", "--format=json"], cwd=work, text=True
        )
        return {
            "os": platform.platform(),
            "python": platform.python_version(),
            "app": version,
            "source_archive": source_zip.name,
            "source_sha256": digests[source_zip.name],
            "install_archive": install_zip.name,
            "install_sha256": digests[install_zip.name],
            "desktop_smoke": "PASS" if desktop else "NOT RUN",
            "packages": json.loads(packages),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--desktop", action="store_true", help="Open and verify a native desktop window.")
    args = parser.parse_args()
    report = json.dumps(verify(args.directory.resolve(), desktop=args.desktop), indent=2)
    if args.report:
        args.report.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
