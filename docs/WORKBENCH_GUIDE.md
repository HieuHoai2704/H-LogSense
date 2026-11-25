# Workbench guide

The project workbench in detail: starting H-logsen, and every panel of the Project, Code, Analysis and
Settings views. Start with the [README](../README.md).

## Start H-logsen

H-logsen is a web application. One command starts a local server bound to `127.0.0.1` and opens it in
your default browser; running the command again while the server runs just opens the browser on it.

```text
python -m pip install -r requirements.txt
python -m app.workbench
```

With Docker running, `python -m scripts.run.demo` also starts MySQL, creates the demo accounts and data,
and opens the browser. Add `--no-browser` to `app.workbench` to print the private URL instead.

The launcher creates a temporary capability. **Project → Open folder** accepts an absolute project
path. In the tree,
open a log or a source file. **Code** supports saving, native undo and
running a Python file with the interpreter selected in **Settings**.
The terminal starts with CMD on Windows and an available local shell on
macOS/Linux. It uses the restored workspace folder or your home directory.
Use **Open log pane** in the terminal toolbar to open the read-only log pane.
Project history and run outputs are stored under `~/.h-logsen` by default.
The regular Flask entry point has no local filesystem or terminal API.

- On desktop-sized windows, Project keeps the controls at the top and shares
  the remaining height between the charts and terminal.
- The Explorer search finds filenames and folders in unopened branches.
  Its results show relative paths and indicate when the scan is limited.
  It scans at most 12,000 entries and returns up to 80 matches.
- The workspace follows a root-level `train.log` when no other log or run
  has been selected. Text files open in the editor. Select **Follow as log**
  in **Manage files** to explicitly follow a text or JSONL file. The activity
  badge distinguishes waiting for a source, waiting for lines and observed
  warning or error records.

- In Project, select a .log to follow it in place. Open source files explicitly
  with **Open in editor**. The timeline groups observed WARN, ERROR and CRITICAL
  lines, and selecting a cell pins the related log lines in the terminal.
  **Return to latest log** resumes the moving view. Analysis lets you select
  a local file for profiling. Project,
  Analysis, and Code remember their folders, expanded branches and open files independently.
  For an existing installation, the last project folder supplies the initial
  folder for each tab.
- Two windows sharing a profile merge settings and view changes. For the same
  project, tab and setting, the most recent save is used. After another window
  changes that tab's folder, refresh or reselect your folder before working.
- In **Code**, split into two panes and click a pane header to choose where
  the next file opens. Save the active pane using Ctrl+S on Windows/Linux or
  Command+S on macOS. PDFs are rendered one
  page at a time, up to 32 MiB per file. The dock contains Terminal,
  log-derived Problems, Output, local TCP Ports and an interactive Python
  Debug console using pdb. Choose the interpreter in the Code toolbar. New
  local shells put that Python first on their PATH. The default prefers the
  project's `.venv` or `venv`, then H-logsen's Python. On Windows run
  `python code.py` or `python -m pip` in the new session. Syntax highlighting
  runs in a worker for eligible text files and refreshes after a short pause.
- **Check Python** checks the saved active Python file with Ruff from the
  selected interpreter and Pyright from the Code folder's `node_modules`.
  Results appear in **Problems** with links to the line and column. A tool that
  is missing or fails is reported separately. **Format** uses Ruff for
  Python and project-local Prettier for JS, TS, JSON, CSS, HTML, Markdown and
  YAML. Review the changes in the editor, then save. **Run file** opens a
  terminal pane for the saved `.py` or `.js` file with the Code folder as its
  working directory. **Track run** retains the Python training
  history and metrics workflow.
- To enable the editor tools, open a fresh terminal in **Code** with the
  desired Python interpreter selected. In the project folder, run
  `python -m pip install ruff` and, with Node.js/npm available,
  `npm install -D pyright prettier`. H-logsen runs the installed tools on
  demand and uses project configuration. Use these commands in folders you
  trust and where you want to add these dependencies.
- In **Machine load**, hover to inspect a sample or pin it by clicking the
  plot or using the arrow keys. Pinning aligns the terminal log context
  and training chart with the selected timestamp, when their time ranges
  overlap. GPU and VRAM share a device selector backed by NVIDIA telemetry.
- Project logs update from the last 64 KiB. Run output and history come from
  the background supervisor. To plot loss, write UTF-8 CSV with
  `epoch,train_loss,val_loss` into `metrics.csv` at the project root or
  into the path given to a training script by `H_LOGSEN_METRICS_CSV`.
  Select a run from **Run history** to inspect its UTC timeline, machine
  samples, checkpoint log messages and raw log context. Add an optional
  ISO 8601 `timestamp` column with an offset to synchronize loss with time.
  Legacy CSV can align to an unambiguous timestamped `epoch=N` log message.
  **Run profile** records the Git branch, commit and whether the selected
  project had uncommitted changes, the Python executable and version, and
  the script and configuration fingerprints before launch. In
  **Settings → Python and packages**, enter up to eight project-relative
  configuration paths, one per line. This registers their fingerprints in
  the profile. Pass any configuration path the script needs via its normal
  arguments. Common dependency manifests at the root are included
  automatically. The profile stores SHA-256 for files up to 1 MiB
  and a short allowlist of numeric flags such as `--epochs` and `--batch-size`.
  It omits file contents, environment values and other argument values.
  A fingerprint identifies a file at capture time. Keep the actual code and
  configuration separately if the run must be reproduced.
- To observe a process that is already running, open its project and choose
  **Attach run**. Enter its PID and the project-relative log and metrics
  paths that it writes. The process must run under your OS account with its
  working directory inside the project. H-logsen reads the supplied files and
  samples CPU and resident RAM for that PID while the run is being viewed.
  GPU and VRAM for attached PIDs are unavailable. To select by an external
  `run_id`, register a manifest first from the project directory:

  ```text
  python -m app.workbench.attached experiment-01 --pid 12345 --log train.log --metrics metrics.csv
  ```

  Replace the example PID with the real process ID. The registration records
  the process start time to reject PID reuse. Attached runs are read-only.
- To associate checkpoints, reports or other output files with this run, write
  them under `Path(os.environ["H_LOGSEN_ARTIFACTS_DIR"])` in the training script.
  The profile lists metadata for at most 100 results, plus the log, machine
  samples and loss CSV. It opens none of the result files. Existing runs retain
  their logs and metrics, with historical environment metadata shown as unavailable.
- Optional project `machine.jsonl` records take an ISO 8601 timestamp with
  an offset and numeric fields such as `cpu_percent`, `ram_percent`,
  `gpu_percent`, `vram_used_mib` and `vram_total_mib`. Live measurements
  use psutil, plus NVIDIA GPU/VRAM if `nvidia-smi` is available.
- Windows uses ConPTY for CMD and PowerShell. macOS/Linux use the native
  POSIX PTY and shells found under `/bin`. **Settings → Remote machines** opens
  an outbound SSH terminal using OpenSSH and a pre-verified known host key.
  **+ New session** focuses the live shell when it is ready. Local shells can start
  in the user's home directory before a project is selected. New shells
  start in the active project when one is selected. Terminals support split panes
  and detached popups.
  Keep the workbench on loopback. The session executes as the OS user.
  If the browser briefly loses connectivity, the open terminal resumes from
  its last output cursor while the same shell is still running. Output older
  than the server buffer is marked as skipped. Input is never replayed.
- **Settings → Language** controls Analysis and the primary workbench
  labels; every label is available in all 15 interface languages. The color
  palette applies across all workbench tabs. **Extensions** manages
  built-in capabilities. **Python and packages** selects the interpreter and
  lists installed packages. Use the terminal for package installation.
- **Analysis** has a function menu on the left instead of a folder tree:
  Log Explorer, anomaly investigation, alerts, datasets and the Loghub
  catalog. Entries marked *Coming soon* (overview, data quality, pipeline
  and jobs, schedules) are planned pages.
- **Project → Analyze data files** profiles CSV, JSONL and Parquet files
  within the open project: select a data file in the tree, or choose
  **Analyze file** under it. It displays a schema, up to 20 valid sample rows,
  missing values, duplicate rows after the first occurrence and distributions.
  Text inputs are limited to 1 MiB. The profiler scans at most 5,000 records.
  Parquet reports the total from file metadata and inspects at most 24 MiB of
  decoded row groups from files up to 256 MiB. Sample counts describe only
  inspected records. HDFS, OpenStack, Log CSV and Log JSONL remain available
  as separate log parsers. The separate evaluation CSV expects
  `unit_id,label,prediction` and binary 0/1 values. Use HDFS block IDs,
  OpenStack VM IDs or event IDs as applicable. The preview does not train a
  detector or import into the MySQL BGL pipeline. The separate full HDFS_v1
  CLI evaluates two baselines on complete block sessions. See
  [HDFS block baseline](../academic/notes/HDFS_BLOCK_BASELINE_VI.md).
- For local tracebacks and test failures, select a source reference in a
  run's log or in the monitored log pane to open the file in **Code**.
  A pytest summary without a line number opens the file only. Live local
  shell links require an absolute path within the currently open project.
- **Project → Compare two runs** compares runs within one project.
  It overlays train and validation loss by epoch and reports paired values at
  the latest shared epoch, along with code/configuration fingerprints and
  peak machine measurements from the recorded samples. Missing values are
  shown explicitly. Direct loss comparisons require matching datasets and
  definitions.
- Terminal assets are vendored from `@xterm/xterm@6.0.0`,
  `@xterm/addon-fit@0.11.0` and `@highlightjs/cdn-assets@11.11.1`.
  Their licenses are in `app/static/vendor/`.

If using MySQL through the operator runtime, start the launcher under the
same database configuration:

```text
python -m scripts.run.mysql_runtime exec --role app -- -m scripts.run.workbench
```
