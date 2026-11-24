# packaging/ — what users receive in a download

These files are placed at the **root** of each download ZIP by
`python -m scripts.release.package_workbench`, next to the H-logsen wheel. This is the only place where files are
split by operating system; the application in `app/` is shared by all of them.

| Folder | ZIP | Contents | Line endings |
| --- | --- | --- | --- |
| `windows/` | `H-logsen-<version>-Windows.zip` | `Install-H-logsen.cmd`, `Open-H-logsen.cmd`, `CAI_DAT_WINDOWS.txt` | CRLF (cmd.exe needs it for labels) |
| `posix/` | `…-macOS.zip`, `…-Linux.zip` | `Install-H-logsen.sh`, `Open-H-logsen.sh`, `CAI_DAT_MAC_LINUX.txt` | LF; macOS also gets `.command` copies, all executable |

`.gitattributes` enforces the line endings on checkout, and the packager enforces them again inside the ZIP.

The scripts also work from a source checkout: run them from this folder and they switch to the repository root
(`../..`) when no wheel is next to them, creating `.venv` there.

```text
sh packaging/posix/Install-H-logsen.sh        # macOS / Linux, from a source checkout
packaging\windows\Install-H-logsen.cmd        # Windows, from a source checkout
```

Platform-specific runtime code (ConPTY, DWM glass, WKWebView, WebKitGTK, the Linux menu launcher) lives in
`app/workbench/`, not here.
