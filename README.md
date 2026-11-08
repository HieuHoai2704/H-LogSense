<div align="center">
  <img src="docs/showcase/h-logsen.png" alt="H-logsen pixel H icon" width="80" height="80">
  <h1>H-logsen</h1>
  <p><strong>A desktop workbench for investigating logs and machine learning runs.</strong></p>
  <p><a href="https://github.com/HieuHoai2704/H-LogSense/raw/refs/heads/download-v0.4.8/downloads/v0.4.8/H-logsen-0.4.8-Windows.zip"><strong>Download for Windows</strong></a> · <a href="https://github.com/HieuHoai2704/H-LogSense/raw/refs/heads/download-v0.4.8/downloads/v0.4.8/H-logsen-0.4.8-macOS.zip"><strong>Download for macOS</strong></a> · <a href="https://github.com/HieuHoai2704/H-LogSense/blob/download-v0.4.8/downloads/v0.4.8/SHA256.txt">SHA-256 checksums</a></p>
  <p>Desktop preview · v0.4.8</p>
</div>

H-logsen brings project files, raw logs, training metrics, and a local shell into one desktop workspace. Use it to inspect a run while it writes logs, compare runs, and read the source or supporting documents alongside the terminal.

## Desktop walkthrough

These four screenshots were captured from the installed Windows desktop app using WebView2. A separate example project ran a Python training loop for 12 epochs and wrote the log and metrics shown here. The app language was set to English. Some controls in v0.4.8 still display Vietnamese labels. Local folder paths were hidden for the captures.

### Project

Open a project folder and select a log in the file tree. H-logsen tails the file and updates the activity view as lines arrive. Select an interval to inspect the matching lines in the read-only log panel. Use the adjacent chart to review loss by epoch or switch to machine load. Run history and comparison are available when the project has recorded runs.

![Windows Project workspace with train.log, log activity, a loss chart and the log panel](docs/showcase/workspace.png)

### Analysis

Open an external dataset and inspect its schema, preview rows, and available summary statistics. Local profiling supports CSV, JSONL, and Parquet. The separate MySQL-backed investigation workflow requires a configured database and covers dataset ingestion, anomaly timelines, supporting evidence, and filtered CSV export.

![Windows Analysis workspace profiling the CSV produced by the training run](docs/showcase/analysis.png)

### Code

Open a source file or PDF from the tree. Split the editor to view two files together, save with **Ctrl+S** or **⌘S**, and run a saved Python or JavaScript file with the corresponding runtime. Python diagnostics and formatting use tools installed in the selected project environment. The terminal uses the local operating system shell.

![Windows Code workspace showing a Python training script and its completed terminal output](docs/showcase/code.png)

### Settings

Manage appearance, language, Python environments, and local capabilities here. To change the interface language, open **Settings → Language** and select a language from the list.

![Windows Settings workspace with English selected](docs/showcase/settings.png)

## Install the desktop preview

Download the ZIP for your operating system and extract it before running the installer. Use 64-bit Python 3.10–3.13. Python 3.12 is recommended. The installer creates a virtual environment inside the extracted directory and downloads Python dependencies.

| Platform | What you need | Verification for v0.4.8 |
| --- | --- | --- |
| Windows x64 | Python and Microsoft Edge WebView2 Runtime | Desktop startup verified. Previous Windows validation recorded 24 browser tests and 34 Python tests. The screenshots above were captured from the installed package. |
| macOS 14+ | Python, preferably from python.org | ZIP built and SHA-256 checked. Clean native installation remains to be verified. |
| Linux | Python for the source workflow | A desktop ZIP and clean native validation are pending. |

### Windows

Open Command Prompt in the extracted ZIP folder and run the two commands below. You can also double-click the scripts in File Explorer. The installer and launcher are in the same folder as the bundled wheel.

```bat
Install-H-logsen.cmd
Open-H-logsen.cmd
```

### macOS

Open Terminal in the extracted ZIP folder and run the installer, then the launcher.

```sh
sh Install-H-logsen.sh
sh Open-H-logsen.sh
```

Use the published [SHA-256 list](https://github.com/HieuHoai2704/H-LogSense/blob/download-v0.4.8/downloads/v0.4.8/SHA256.txt) to compare the downloaded ZIP. Run `Get-FileHash -Algorithm SHA256 .\H-logsen-0.4.8-Windows.zip` in PowerShell or `shasum -a 256 H-logsen-0.4.8-macOS.zip` on macOS.

## First project

1. Open **Project → Open folder** and choose the local project you want to inspect.
2. Select `train.log` in the tree to view its recent lines and log activity. For loss curves, place `metrics.csv` in the project with columns `epoch`, `train_loss`, and `val_loss`.
3. Select a log interval to inspect its lines. Switch to **Analysis** for file profiling or **Code** for editing and running a script.

## Architecture and scope

The desktop preview renders the Flask, Jinja, and JavaScript interface in an operating system web view. It uses WebView2 on Windows and WKWebView on macOS. The local Flask service listens on loopback. File access and terminal commands run under the signed-in OS account. Local file viewing, editing, terminal sessions, and profiling work without MySQL.

The MySQL-backed investigation pipeline is a separate workflow for imported log data. See the [original LogSense AI baseline](https://github.com/HieuHoai2704/H-LogSense/blob/675c718cdc0503fbcb9daf10fa7c76b3ffcf34dc/README.md) for its source setup and documentation.

## Source, downloads, and feedback

The `main` branch tracks the original LogSense AI investigation source and this showcase. The `download-v0.4.8` branch hosts the packaged desktop preview. Use the installer from the ZIP for the version shown above.

When filing an [issue](https://github.com/HieuHoai2704/H-LogSense/issues), include the app version, operating system, the workspace and action involved, and the smallest sample needed to reproduce the problem. Use sample logs or redact sensitive values before sharing.

A project-wide open-source license is pending. Desktop packages include third-party notices.
