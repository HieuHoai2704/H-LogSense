"use strict";

const $ = (id) => document.getElementById(id);
const tr = window.logsenseTranslate;
const bucketLimit = 12;
const demoInterval = 3000;
const fileLimit = 1024 * 1024;
const logExtensions = new Set(["log", "txt", "jsonl"]);
const projectExtensions = new Set(["py", "md", "txt", "log", "json", "jsonl", "csv", "yaml", "yml", "toml", "ini", "html", "css", "js", "ts", "sql", "sh", "ps1"]);
const skippedFolders = new Set(["node_modules", "__pycache__", "venv", "dist", "build"]);
const codeExamples = {
  "train.py": '"""' + tr("Example training run in the sample project.") + '"""\n\nimport logging\nfrom pathlib import Path\n\nLOG_DIR = Path("runs") / "vl-024"\n\ndef main() -> None:\n    LOG_DIR.mkdir(parents=True, exist_ok=True)\n    logging.basicConfig(\n        filename=LOG_DIR / "train.log",\n        level=logging.INFO,\n        format="%(asctime)s %(levelname)s %(message)s",\n    )\n    logging.info("Training started")\n\nif __name__ == "__main__":\n    main()\n',
  "config.yaml": "training:\n  epochs: 8\n  batch_size: 32\n  learning_rate: 0.001\n",
  "README.md": "# " + tr("Sample project") + "\n\n" + tr("Sample folder illustrating the log and training-metrics viewing flow.") + "\n",
};
const previewFiles = new Map();
let previewPath = null;
let previewRequest = 0;
const exampleProjects = new Map([["vision-lab", "vl-024"], ["text-lab", "tl-009"]]);
const locale = document.documentElement.lang;
const number = new Intl.NumberFormat(locale);
const clock = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
const minuteClock = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const exactClock = new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "long", hourCycle: "h23" });
const datedClock = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
const activityLanes = ["all", "WARN", "ERROR", "CRITICAL"];
const criticalLevels = new Set(["CRITICAL", "FATAL", "SEVERE"]);
const signalLevel = (entry) => entry.critical ? "CRITICAL" : entry.level;
const isSignal = (entry) => entry.critical || entry.level === "WARN" || entry.level === "ERROR";
let activityMode = "severity";
let selectedLane = "all";
const state = {
  source: tr("No log open"), demo: false, playing: false, buckets: [], terminalBuckets: [],
  selected: null, logSelection: null, follow: true, demoProject: "vision-lab", folder: null, activeFile: null
};
const terminalBody = $("terminal-body");
const terminalScope = $("terminal-scope");
const terminalFollow = $("follow");
const machineChart = window.createMachineChart({
  onPin(stamp) {
    state.machineTime = stamp;
    window.WorkbenchRunDetail?.selectTime(stamp);
    renderMetrics();
    renderTerminal();
    if (stamp !== null) document.dispatchEvent(new CustomEvent("workspace:show-log", { detail: { keepFocus: true } }));
  },
  onDevice(device) { window.WorkbenchRunDetail?.setDevice(device); },
});

function demoBucket(time) {
  const index = Math.floor(time / demoInterval);
  const count = 8 + Math.round(5 * Math.sin(index / 2) + 4 * Math.cos(index / 4));
  const warnings = 1 + index % 3;
  const errors = index % 5 === 0 ? 3 : index % 3 === 0 ? 1 : 0;
  const messages = [
    ["INFO", "worker-01  Loaded input shard"],
    ["INFO", "worker-01  Completed feature batch"],
    ["INFO", "api-01     Request completed"],
    ["WARN", "worker-01  Data loader waiting for I/O"],
    ["ERROR", "api-01     Upstream request timed out"],
  ];
  const entries = Array.from({ length: Math.max(count, warnings + errors + 2) }, (_, row) => {
    const [level, message] = messages[row < warnings ? 3 : row < warnings + errors ? 4 : row % 3];
    const observed = time + row * 70;
    return { time: observed, level, raw: new Date(observed).toISOString() + " " + level + " " + message };
  });
  return { time, end: time + demoInterval, label: clock.format(time), entries };
}

function resetDemo(project = "vision-lab") {
  const lastTime = Math.floor(Date.now() / demoInterval) * demoInterval;
  const demoGpu = [43, 70, 79, 86, 94, 90, 82, 70];
  state.demoMachine = [34, 52, 45, 65, 51, 59, 56, 44].map((cpu, index) => ({
    timestamp: new Date(lastTime - (7 - index) * demoInterval).toISOString(),
    cpu_percent: cpu,
    gpu_percent: demoGpu[index],
  }));
  state.source = tr("Demo stream");
  state.demo = true;
  state.demoProject = project;
  state.folder = null;
  state.activeFile = null;
  clearPreview();
  state.playing = true;
  state.selected = null;
  state.logSelection = null;
  state.follow = true;
  state.buckets = Array.from({ length: bucketLimit }, (_, index) =>
    demoBucket(lastTime - (bucketLimit - 1 - index) * demoInterval));
  state.terminalBuckets = state.buckets;
  renderProject();
  render();
}

function summarize(bucket) {
  const counts = { all: 0, WARN: 0, ERROR: 0, CRITICAL: 0 };
  for (const entry of bucket.entries) {
    if (isSignal(entry)) {
      counts[signalLevel(entry)] += 1;
      counts.all += 1;
    }
  }
  return counts;
}

function waitingChart(container, message) {
  const track = document.createElement("div");
  track.className = "chart-waiting-track";
  track.setAttribute("aria-hidden", "true");
  container.replaceChildren(message, track);
}

function chartStatus(id, message, tone = "") {
  const badge = $(id);
  const text = tr(message);
  if (badge.textContent !== text) badge.textContent = text;
  badge.dataset.tone = tone;
}

function renderActivityStatus() {
  if (state.demo) return chartStatus("activity-state", "Demo");
  if (state.logUnavailable) return chartStatus("activity-state", "Connection interrupted", "alert");
  if (!state.localSource && !state.activeFile) return chartStatus("activity-state", "Waiting for log");
  if (!state.buckets.length) return chartStatus("activity-state", "Waiting for log lines", state.localSource ? "live" : "");
  if (state.selected !== null) return chartStatus("activity-state", "Pinned log interval");
  const flagged = state.buckets.some((bucket, index) => (state.selected === null || state.selected === index) &&
    bucket.entries.some(isSignal));
  if (flagged) chartStatus("activity-state", "Warnings or errors in range", "alert");
  else chartStatus("activity-state", "No warnings or errors recorded", state.localSource ? "live" : "");
}

function activityDetail(index, counts) {
  const bucket = state.buckets[index];
  const period = bucket.time === undefined ? bucket.label :
    "[" + exactClock.format(bucket.time) + " – " + exactClock.format(bucket.end) + ")";
  return period + " · " +
    "WARN " + counts.WARN + " · ERROR " + counts.ERROR + " · CRITICAL " + counts.CRITICAL +
    " · " + number.format(bucket.entries.length) + " " + tr("Log lines");
}

function renderActivity(stats) {
  const chart = $("severity-chart");
  const detail = $("activity-detail");
  chart.toggleAttribute("data-empty", !stats.length);
  // An empty chart says why in one line instead of showing a grid of placeholders.
  chart.dataset.emptyText = stats.length ? "" : tr(state.localSource || state.activeFile ? "Waiting for log lines" : "No project open");
  $("activity-controls").hidden = !stats.length;
  detail.hidden = false;
  $("activity-live").hidden = state.selected === null;
  const heatmap = document.createElement("div");
  heatmap.className = "heatmap";
  heatmap.dataset.mode = activityMode;
  const hasData = stats.length > 0;
  const bins = hasData ? state.buckets : Array.from({ length: 8 }, () => ({ label: "—" }));
  heatmap.style.setProperty("--bins", bins.length);
  if (!hasData) heatmap.setAttribute("aria-hidden", "true");
  const axis = document.createElement("span");
  axis.textContent = tr("Log level");
  heatmap.append(axis);
  for (const bucket of bins) {
    const tick = document.createElement("span");
    tick.className = "time-tick";
    tick.title = bucket.label;
    tick.textContent = bucket.time !== undefined && bins.length >= 9 && bucket.end - bucket.time >= 60_000
      ? minuteClock.format(bucket.time)
      : bucket.label;
    heatmap.append(tick);
  }
  const max = Math.max(1, ...stats.map((counts) => counts.all));
  for (const lane of activityLanes) {
    const heading = document.createElement("span");
    const label = lane === "all" ? tr("Overall") : lane;
    heading.textContent = label;
    heatmap.append(heading);
    if (!hasData) {
      for (const _ of bins) {
        const cell = document.createElement("span");
        cell.className = "empty-bin";
        cell.textContent = "—";
        heatmap.append(cell);
      }
    }
    stats.forEach((counts, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.bin = index;
      button.dataset.lane = lane;
      if (counts[lane]) {
        button.dataset.tone = lane === "all" ? counts.CRITICAL ? "CRITICAL" : counts.ERROR ? "ERROR" : "WARN" : lane;
        button.style.setProperty("--density", (10 + Math.round(35 * counts[lane] / max)) + "%");
      }
      button.textContent = number.format(counts[lane]);
      button.setAttribute("aria-pressed", String(state.selected === index && selectedLane === lane));
      button.title = label + " · " + activityDetail(index, counts);
      button.setAttribute("aria-label", button.title);
      heatmap.append(button);
    });
  }
  if (!hasData) detail.textContent = tr(state.localSource ? "Waiting for log lines" : "Open a log file to see activity");
  else if (state.selected === null) detail.textContent = tr("Select an interval to inspect its log lines");
  else detail.textContent = activityDetail(state.selected, stats[state.selected]);
  chart.replaceChildren(heatmap);
}

function renderResults() {
  const entries = state.buckets.flatMap((bucket, index) =>
    state.selected === null || state.selected === index
      ? bucket.entries.filter((entry) => isSignal(entry) && (state.selected === null || selectedLane === "all" || signalLevel(entry) === selectedLane)).map((entry) => ({ entry, index }))
      : []);
  const rows = entries.slice(-25).reverse().map(({ entry, index }) => {
    const button = document.createElement("button");
    const time = document.createElement("small");
    const severity = document.createElement("strong");
    const raw = document.createElement("span");
    button.type = "button";
    button.className = "result-row";
    button.dataset.openLog = index;
    button.dataset.level = signalLevel(entry);
    severity.textContent = button.dataset.level;
    button.title = tr("Open log in terminal");
    time.textContent = entry.time === null ? tr("L{0}", entry.line) : clock.format(entry.time);
    raw.textContent = entry.raw;
    button.append(time, severity, raw);
    return button;
  });
  const resultList = $("result-list");
  resultList.toggleAttribute("data-empty", !rows.length);
  resultList.replaceChildren(...(rows.length ? rows : [tr("No WARN or ERROR in this range.")]));
  return entries.length;
}

function renderMeasured(container, rows, keys, labels, timeKey, inspectedEpoch = null) {
  container.replaceChildren();
  const hasData = rows.some((row) => keys.some((key) => Number.isFinite(row[key])));
  container.toggleAttribute("data-empty", !hasData);
  if (!hasData) {
    container.textContent = tr("No metrics available");
    return;
  }
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 500 140");
  if (container.classList.contains("chart-data")) svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", labels.join(", "));
  svg.classList.add("plot", "measured-plot");
  const values = rows.flatMap((row) => keys.map((key) => row[key])).filter(Number.isFinite);
  const minimum = Math.min(0, ...values);
  const maximum = timeKey === "timestamp" ? Math.max(100, ...values) : Math.max(.01, ...values);
  const scale = Math.max(Math.abs(minimum), maximum);
  const minScaled = minimum / scale;
  const ySpan = maximum / scale - minScaled;
  const xValues = rows.map((row) => timeKey === "timestamp" ? Date.parse(row[timeKey]) : row[timeKey]);
  const first = Math.min(...xValues);
  const span = Math.max(1, Math.max(...xValues) - first);
  function shape(tag, attributes) {
    const element = document.createElementNS(svg.namespaceURI, tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    svg.append(element);
    return element;
  }
  for (const fraction of [0, .25, .5, .75, 1]) {
    const y = 121 - fraction * 108;
    shape("line", { x1: 39, x2: 488, y1: y, y2: y, class: "guide" });
    const label = (1 - fraction) * minimum + fraction * maximum;
    shape("text", { x: 3, y: y + 4 }).textContent = number.format(Number(label.toFixed(2)));
  }
  if (inspectedEpoch !== null) {
    const x = 42 + 446 * (inspectedEpoch - first) / span;
    shape("line", { x1: x, x2: x, y1: 13, y2: 121, class: "machine-crosshair", "data-epoch": inspectedEpoch });
  }
  keys.forEach((key, series) => {
    let previous;
    rows.forEach((row, index) => {
      if (!Number.isFinite(row[key])) {
        previous = null;
        return;
      }
      const x = 42 + 446 * (xValues[index] - first) / span;
      const y = 121 - 108 * (row[key] / scale - minScaled) / ySpan;
      const style = "measurement series-" + series;
      if (previous) shape("line", { x1: previous.x, x2: x, y1: previous.y, y2: y, class: style });
      shape("circle", { cx: x, cy: y, r: 2.5, class: style });
      previous = { x, y };
    });
  });
  const range = document.createElement("p");
  const axis = timeKey === "timestamp" ? (value) => datedClock.format(value) : (value) => "Epoch " + value;
  range.className = "muted";
  range.textContent = axis(first) + " → " + axis(Math.max(...xValues)) + " · " + labels.join(" / ");
  container.append(svg, range);
}

function nearestWithin(points, stamp) {
  if (!points.length || stamp < points[0].time || stamp > points.at(-1).time) return null;
  return points.reduce((closest, point) =>
    Math.abs(point.time - stamp) < Math.abs(closest.time - stamp) ? point : closest);
}

function clearMachineTime() {
  if (state.machineTime == null) return;
  state.machineTime = null;
  machineChart.clearPin();
  window.WorkbenchRunDetail?.selectTime(null);
  renderMetrics();
}

function secondsApart(left, right) {
  return number.format(Number((Math.abs(left - right) / 1000).toFixed(3))) + " s";
}

function trainInspection(rows) {
  const stamp = state.machineTime;
  const note = $("training-sync");
  note.hidden = stamp == null;
  if (stamp == null) return null;
  const timed = ["run", "attached"].includes(state.machineSource) ? window.WorkbenchRunDetail?.timedLoss() || [] :
    rows.map((row) => ({ ...row, time: Date.parse(row.timestamp) })).filter((row) => Number.isFinite(row.time))
      .sort((a, b) => a.time - b.time);
  const nearest = nearestWithin(timed, stamp);
  const caption = tr("Machine sample") + " · " + datedClock.format(stamp);
  note.textContent = nearest ? caption + " · Epoch " + nearest.epoch + " · " +
    (nearest.time === stamp ? tr("Same timestamp") : tr("Time offset") + " " + secondsApart(nearest.time, stamp))
    : caption + " · " + tr("No matching timestamped training metrics");
  return nearest?.epoch ?? null;
}

function renderMetrics() {
  const machine = machineChart.update(state.demo ? state.demoMachine : state.machine || [], state.demo ? "demo" : state.machineSource,
    state.machineSource === "attached" && !state.demo ? state.machinePid : null);
  if (state.machineTime != null && machine.pinned === null) {
    state.machineTime = null;
    window.WorkbenchRunDetail?.selectTime(null);
    renderTerminal();
  }
  window.WorkbenchRunDetail?.setDevice(machine.device);
  const container = $("training-chart");
  const rows = state.training || [];
  const inspectedEpoch = trainInspection(rows);
  container.parentElement.querySelector(".data-kind").hidden = !state.demo;
  if (!state.demo) {
    renderMeasured(container, rows, ["train_loss", "val_loss"], ["Train loss", "Validation loss"], "epoch", inspectedEpoch);
    if (container.hasAttribute("data-empty")) waitingChart(container, tr("No metrics available"));
    if (state.runStatus && state.logUnavailable) chartStatus("training-state", "Connection interrupted", "alert");
    else if (["starting", "running"].includes(state.runStatus)) chartStatus("training-state", "Training in progress", "live");
    else chartStatus("training-state", container.hasAttribute("data-empty") ? "Ready" : "Data available");
  } else {
    container.removeAttribute("data-empty");
    const y = (loss) => 116 - loss * 54;
    const points = (series) => series.map((value, index) => 8 + index * 484 / (series.length - 1) + "," + y(value)).join(" ");
    const grid = [0, .5, 1, 1.5, 2].map((loss) =>
      '<line class="guide" x1="0" x2="500" y1="' + y(loss) + '" y2="' + y(loss) + '"></line>').join("");
    const ticks = [2, 1.5, 1, .5, 0].map((loss) => '<span>' + number.format(loss) + '</span>').join("");
    container.innerHTML = '<div class="metric-plot"><div class="metric-axis" aria-hidden="true">' + ticks +
      '</div><svg class="plot" viewBox="0 0 500 124" preserveAspectRatio="none" role="img" aria-label="' + tr("Simulated chart: Train loss, Validation loss") + '">' +
      grid + '<polyline class="lane reference" points="' + points([1.84, 1.42, 1.16, .88, .76, .63, .57, .49]) +
      '"></polyline><polyline class="lane secondary" points="' + points([1.91, 1.66, 1.32, 1.03, .94, .87, .83, .81]) +
      '"></polyline></svg></div><div class="axis-x metric-axis-x"><span>Epoch 1</span><span>Epoch 8</span></div>' +
      '<div class="chart-foot legend"><span class="reference-key">Train loss</span><span>Validation loss</span></div>';
    chartStatus("training-state", "Demo");
  }
  const { available } = machine;
  if (state.demo) chartStatus("machine-state", "Demo");
  else if (state.runStatus && state.logUnavailable) chartStatus("machine-state", "Connection interrupted", "alert");
  else chartStatus("machine-state", !available ? "Ready" : state.machineLive ? "Live samples" : "Data available",
    available && state.machineLive ? "live" : "");
}

function renderProject() {
  const projectName = state.localRoot?.split(/[\\/]/).at(-1) || state.folder?.name || (state.demo ? state.demoProject : state.activeFile?.name || tr("No project open"));
  $("workspace-source").textContent = projectName;
  $("editor-project").textContent = window.localWorkbench ? state.codeRoot?.split(/[\\/]/).at(-1) || tr("No folder selected") : projectName;
  $("run-label").textContent = state.demo ? "/ " + exampleProjects.get(state.demoProject) : "";
  $("tree-source").textContent = window.localWorkbench
    ? tr($("editor").hidden ? "Project folder scope" : "Code folder scope")
    : state.demo ? tr("Sample project") : state.folder || state.activeFile ? tr("Files selected on this computer") : tr("Select a folder or log file");

  const tree = $("project-files");
  const openFolders = new Map([...tree.querySelectorAll("details[data-folder-key]")].map((item) => [item.dataset.folderKey, item.open]));

  function folderNode(name, key, open, active = false) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const icon = document.createElement("span");
    const contents = document.createElement("div");
    const label = document.createElement("span");
    details.open = openFolders.get(key) ?? open;
    details.dataset.folderKey = key;
    if (active) details.dataset.active = "true";
    icon.className = "tree-folder";
    icon.setAttribute("aria-hidden", "true");
    label.className = "tree-label";
    label.textContent = name;
    summary.append(icon, label);
    summary.title = name;
    contents.className = "tree-children";
    details.append(summary, contents);
    return { details, contents };
  }

  function fileButton(kind, name, selected) {
    const button = document.createElement("button");
    const type = document.createElement("span");
    const label = document.createElement("span");
    button.type = "button";
    button.dataset.projectFile = kind;
    button.title = name;
    type.className = "tree-file-type";
    type.textContent = name.includes(".") ? name.split(".").at(-1).slice(0, 4).toUpperCase() : "TXT";
    type.setAttribute("aria-hidden", "true");
    label.className = "tree-label";
    label.textContent = name;
    button.append(type, label);
    button.setAttribute("aria-pressed", String(selected));
    return button;
  }

  tree.replaceChildren();
  if (state.demo) {
    for (const name of exampleProjects.keys()) {
      const folder = folderNode(name, "sample:" + name, name === state.demoProject, name === state.demoProject);
      const runs = folderNode("runs", "sample:" + name + "/runs", name === state.demoProject);
      folder.contents.append(runs.details);
      for (const [kind, file] of [["log", "train.log"], ["training", "metrics.csv"], ["machine", "machine.jsonl"],
        ["code", "train.py"], ["code", "config.yaml"], ["code", "README.md"]]) {
        const key = name + "/" + file;
        const selected = !$("editor").hidden ? previewPath === key : name === state.demoProject && kind === "log";
        const button = fileButton(kind, file, selected);
        button.dataset.demoProject = name;
        button.dataset.fileName = file;
        (kind === "code" ? folder.contents : runs.contents).append(button);
      }
      tree.append(folder.details);
    }
  } else if (state.folder || state.activeFile) {
    const rootKey = "local:" + projectName;
    const root = folderNode(projectName, rootKey, true, true);
    const folders = new Map([["", root.contents]]);
    const files = state.folder?.files || (state.activeFile ? [state.activeFile] : []);
    const ordered = files.map((file, index) => ({ file, index })).toSorted((a, b) =>
      (a.file.webkitRelativePath || a.file.name).localeCompare(b.file.webkitRelativePath || b.file.name));
    ordered.forEach(({ file, index }) => {
      const parts = (file.webkitRelativePath || file.name).split("/");
      const name = parts.pop();
      if (parts.length) parts.shift();
      let key = "";
      let parent = root.contents;
      for (const folderName of parts) {
        key += "/" + folderName;
        if (!folders.has(key)) {
          const child = folderNode(folderName, rootKey + key, parts.length === 1);
          parent.insertBefore(child.details, [...parent.children].find((item) => item.tagName === "BUTTON") || null);
          folders.set(key, child.contents);
        }
        parent = folders.get(key);
      }
      const kind = logExtensions.has(name.split(".").at(-1).toLowerCase()) ? "log" : "code";
      const selected = !$("editor").hidden ? previewPath === (file.webkitRelativePath || file.name) : file === state.activeFile;
      const button = fileButton(kind, name, selected);
      button.dataset.localFile = index;
      parent.append(button);
    });
    tree.append(root.details);
  }
  renderMetrics();
}

function clearPreview() {
  previewFiles.clear();
  previewPath = null;
  previewRequest++;
  renderEditor();
}

function renderEditor() {
  const doc = previewFiles.get(previewPath);
  const tabs = $("editor-tabs");
  tabs.replaceChildren(...[...previewFiles].map(([path, file]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = file.name;
    button.title = path;
    button.setAttribute("aria-pressed", String(path === previewPath));
    button.addEventListener("click", () => {
      previewPath = path;
      renderEditor();
      renderProject();
      const active = tabs.querySelector('[aria-pressed="true"]');
      active?.focus();
    });
    return button;
  }));
  $("editor-file-path").textContent = doc ? previewPath + (doc.truncated ? " · " + tr("Showing the first 2,000 lines") : "") : "";
  const target = $("editor-code");
  $("editor-preview").hidden = Boolean($("local-editor")) && !state.demo;
  if ($("local-editor")) $("local-editor").hidden = state.demo;
  if (!doc) {
    target.textContent = tr("Choose a text file from the project tree to view its contents.");
    return;
  }
  target.replaceChildren(...doc.lines.map((line, index) => {
    const row = document.createElement("span");
    row.className = "editor-line";
    row.dataset.line = index + 1;
    row.textContent = line || " ";
    return row;
  }));
}

async function openPreview(name, path, file) {
  const request = ++previewRequest;
  navigateProject("editor");
  try {
    if (!previewFiles.has(path)) {
      if (file?.size > fileLimit) throw new Error(tr("The preview opens text files up to 1 MiB."));
      const content = file ? await file.text() : codeExamples[name];
      if (request !== previewRequest) return;
      if (content.includes("\0")) throw new Error(tr("This file has binary content."));
      const lines = content.split(/\r\n|\n|\r/);
      if (previewFiles.size >= 8) previewFiles.delete(previewFiles.keys().next().value);
      previewFiles.set(path, { name, lines: lines.slice(0, 2000), truncated: lines.length > 2000 });
    }
    previewPath = path;
    renderEditor();
    renderProject();
    if (!$("editor").hidden) $("editor-code").focus({ preventScroll: true });
  } catch (error) {
    if (request === previewRequest) $("editor-file-path").textContent = error.message;
  }
}

function machineLogContext() {
  const stamp = state.machineTime;
  if (stamp == null) return null;
  const entries = state.terminalBuckets.flatMap((bucket) => bucket.entries);
  const timed = entries.filter((entry) => Number.isFinite(entry.time)).sort((a, b) => a.time - b.time);
  const nearest = nearestWithin(timed, stamp);
  const label = tr("Machine sample") + " · " + datedClock.format(stamp);
  if (!nearest) return { label: label + " · " + tr("No matching timestamped logs"), entries: [] };
  const index = entries.indexOf(nearest);
  return {
    label: label + " · " + (nearest.time === stamp ? tr("Log at the same time") : tr("Nearest log") + " · " +
      tr("Time offset") + " " + secondsApart(nearest.time, stamp)),
    entries: entries.slice(Math.max(0, index - 2), index + 3),
    anchor: nearest,
  };
}

function renderTerminal() {
  const panel = terminalBody;
  const oldScroll = panel.scrollTop;
  const machineContext = machineLogContext();
  const chosen = machineContext || state.logSelection;
  const visible = chosen ? chosen.entries : state.terminalBuckets.flatMap((bucket) => bucket.entries);
  const lines = visible.slice(-160);
  const fragment = document.createDocumentFragment();
  for (const item of lines) {
    const row = document.createElement("div");
    const time = document.createElement("time");
    const level = document.createElement("span");
    const message = document.createElement("code");
    row.className = "log-line";
    row.dataset.level = signalLevel(item);
    if (item === machineContext?.anchor) row.classList.add("machine-log-anchor");
    time.textContent = item.time !== null ? clock.format(item.time) : tr("L{0}", item.line);
    if (item.time !== null) time.dateTime = new Date(item.time).toISOString();
    level.className = "log-level";
    level.textContent = signalLevel(item);
    message.textContent = item.raw;
    if (!state.demo && state.localSource && window.WorkbenchSourceLinks) {
      const links = window.WorkbenchSourceLinks;
      const target = links.reference(item.raw, state.localRoot);
      if (target) message.append(links.button(target));
    }
    row.append(time, level, message);
    fragment.append(row);
  }
  if (!lines.length) fragment.append(tr("No logs in this range"));
  panel.replaceChildren(fragment);
  const scope = chosen?.label ?? tr("Full range");
  terminalScope.textContent = window.logsenseTranslatePlural(lines.length, "{0} · {1} line", "{0} · {1} lines", scope, number.format(lines.length) +
    (visible.length > lines.length ? "/" + number.format(visible.length) : ""));
  terminalFollow.setAttribute("aria-pressed", String(state.follow && !machineContext));
  panel.scrollTop = machineContext ? 0 : state.follow ? panel.scrollHeight : oldScroll;
}

function setMetric(id, value, label) {
  const strong = document.createElement("strong");
  strong.textContent = number.format(value);
  $(id).replaceChildren(strong, label);
}

function render() {
  const activeChart = document.activeElement?.closest("#severity-chart");
  const activeBin = document.activeElement?.dataset.bin;
  const activeLane = document.activeElement?.dataset.lane;
  $("source-state").textContent = state.demo ? (state.playing ? tr("Simulating") : tr("Simulation paused")) :
    state.localSource ? tr("Following local file") : state.activeFile ? tr("History from file") : tr("No log open");
  $("source-state").dataset.live = String(state.demo && state.playing);
  $("pause").hidden = !state.demo;
  $("pause").textContent = state.playing ? tr("Hold view") : tr("Resume following");
  $("source-name").textContent = state.source + (state.demo ? " · " + tr("Sample every 3 seconds") : state.localSource ? " · " + tr("Last 64 KiB at most") : state.activeFile ? " · " + tr("Read locally") : "");
  $("source-name").hidden = state.source === tr("No log open");

  const options = state.buckets.map((bucket, index) => new Option(bucket.label, index));
  $("bucket").replaceChildren(new Option(state.demo ? tr("All · latest point") : tr("All data"), "all"), ...options);
  $("bucket").value = state.selected ?? "all";

  const stats = state.buckets.map(summarize);
  const active = state.selected === null ? stats : [stats[state.selected]];
  setMetric("signal-metric", active.reduce((sum, item) => sum + item[state.selected === null ? "all" : selectedLane], 0), tr("warnings and errors"));
  renderActivity(stats);
  renderActivityStatus();
  setMetric("volume-metric", renderResults(), tr("lines to review"));
  renderTerminal();
  if (activeChart && activeBin !== undefined) {
    activeChart.querySelector('[data-bin="' + activeBin + '"][data-lane="' + activeLane + '"]')?.focus({ preventScroll: true });
  }
}

function chooseBucket(value, lane = "all") {
  clearMachineTime();
  const index = value === "all" ? null : Number(value);
  const bucket = index === null ? null : state.buckets[index];
  state.selected = bucket ? index : null;
  selectedLane = lane;
  if (bucket) {
    state.playing = false;
    state.follow = false;
    state.logSelection = lane === "all" ? bucket : {
      label: bucket.label + " · " + lane,
      entries: bucket.entries.filter((entry) => signalLevel(entry) === lane),
    };
    terminalBody.scrollTop = 0;
    document.dispatchEvent(new CustomEvent("workspace:show-log", { detail: { keepFocus: true } }));
  } else {
    state.logSelection = null;
    state.follow = true;
    state.buckets = state.terminalBuckets;
    if (state.demo) state.playing = true;
  }
  render();
}

function showView(view) {
  $("monitor").hidden = view !== "monitor";
  $("editor").hidden = view !== "editor";
  $("settings").hidden = view !== "settings";
  document.querySelector(".project-tree").hidden = view === "settings";
  $("settings-nav").hidden = view !== "settings";
  document.querySelector(".project-shell").dataset.view = view;
  const status = $("local-status");
  if (status) {
    const statusHost = view === "monitor" ? document.querySelector(".monitor-top") : $(view);
    if (status.parentElement !== statusHost) statusHost.prepend(status);
  }
  document.dispatchEvent(new CustomEvent("workbench:view", { detail: view }));
  projectLinks.forEach((button) => {
    if (button.dataset.projectView === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (view === "monitor" || view === "editor") {
    const host = $(view === "editor" ? "editor-terminal" : "monitor-terminal");
    if ($("terminal-dock").parentElement !== host) host.append($("terminal-dock"));
    renderTerminal();
    if (view === "editor" && !previewPath && state.demo) {
      const name = "train.py";
      const path = state.demoProject + "/" + name;
      previewFiles.set(path, { name, lines: codeExamples[name].split("\n"), truncated: false });
      previewPath = path;
      renderEditor();
    }
    renderProject();
  } else if (view === "settings") {
    const files = state.folder?.files || (state.activeFile ? [state.activeFile] : []);
    const kinds = new Set(files.map((file) => file.name.split(".").at(-1).toUpperCase()));
    $("settings-project").textContent = $("workspace-source").textContent;
    $("settings-file-count").textContent = state.demo ? tr("Demo tree") : state.localRoot ? tr("Counted per folder in the tree") : number.format(files.length);
    $("settings-file-types").textContent = kinds.size ? [...kinds].sort().join(", ") : tr("No real folder yet");
    $("settings-log-source").textContent = state.source;
  }
}

function parseEntry(raw, line, structured) {
  let value = null;
  if (structured) {
    try { value = JSON.parse(raw); } catch { throw new Error(tr("Invalid JSONL on line {0}.", line)); }
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(tr("JSONL needs an object on line {0}.", line));
    }
  }
  const iso = /\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})\b/i;
  const candidate = structured ? value.timestamp : raw.match(iso)?.[0];
  const match = typeof candidate === "string" ? candidate.trim().match(iso) : null;
  const parsedTime = match && match[0] === candidate.trim() ? Date.parse(match[0].replace(" ", "T")) : NaN;
  const levelName = structured ? value.level ?? value.severity :
    raw.match(/\b(INFO|DEBUG|TRACE|NOTICE|WARNING|WARN|ERROR|CRITICAL|FATAL|SEVERE|FAILURE)\b/i)?.[0];
  const upper = String(levelName ?? "").toUpperCase();
  const level = ["ERROR", "CRITICAL", "FATAL", "SEVERE", "FAILURE"].includes(upper) ? "ERROR" :
    ["WARN", "WARNING"].includes(upper) ? "WARN" :
    ["INFO", "DEBUG", "TRACE", "NOTICE"].includes(upper) ? upper : "—";
  return { time: Number.isFinite(parsedTime) ? parsedTime : null, level, critical: criticalLevels.has(upper), raw, line };
}

function groupEntries(entries) {
  if (entries.some((item) => item.time === null)) {
    const perBucket = Math.ceil(entries.length / bucketLimit);
    const buckets = [];
    for (let offset = 0; offset < entries.length; offset += perBucket) {
      const group = entries.slice(offset, offset + perBucket);
      buckets.push({ label: tr("L{0}–{1}", group[0].line, group.at(-1).line), entries: group });
    }
    return buckets;
  }
  const sorted = entries.toSorted((first, second) => first.time - second.time);
  const start = sorted[0].time;
  const span = sorted.at(-1).time - start;
  const step = Math.max(1000, Math.ceil((span + 1) / (bucketLimit * 1000)) * 1000);
  const formatter = span >= 86400000 ? datedClock : clock;
  const buckets = Array.from({ length: Math.floor(span / step) + 1 }, (_, index) =>
    ({ time: start + index * step, end: start + (index + 1) * step, label: formatter.format(start + index * step), entries: [] }));
  for (const entry of sorted) buckets[Math.floor((entry.time - start) / step)].entries.push(entry);
  return buckets;
}

function importStatus(message, error = false) {
  $("import-status").textContent = message;
  $("import-status").dataset.error = String(error);
}

async function openLog(file, folder = null) {
  if ($("import-button").disabled) return;
  const extension = file.name.split(".").at(-1).toLowerCase();
  $("import-button").disabled = true;
  $("use-demo").disabled = true;
  try {
    if (!logExtensions.has(extension)) throw new Error(tr("Choose a .log, .txt or .jsonl file."));
    if (file.size > fileLimit) throw new Error(tr("The file exceeds the viewer's 1 MiB limit."));
    const content = await file.text();
    if (content.includes("\0")) throw new Error(tr("The file must be UTF-8 text."));
    const lines = content.split(/\r\n|\n|\r/);
    if (lines.at(-1) === "") lines.pop();
    if (lines.length > 12000) throw new Error(tr("The file exceeds the viewer's 12,000-line limit."));
    const entries = lines.flatMap((line, index) =>
      line.trim() ? [parseEntry(line, index + 1, extension === "jsonl")] : []);
    if (!entries.length) throw new Error(tr("The file has no log lines."));
    const buckets = groupEntries(entries);
    if (state.folder !== folder || state.demo) clearPreview();
    Object.assign(state, { source: file.name, demo: false, playing: false, buckets, terminalBuckets: buckets,
      selected: null, logSelection: null, follow: true, folder, activeFile: file });
    importStatus(window.logsenseTranslatePlural(entries.length, "Opened {0} line.", "Opened {0} lines.", number.format(entries.length)));
    renderProject();
    render();
    $("project-file").open = false;
    $("project-file").hidden = true;
    $("open-project-file").focus();
  } catch (error) {
    $("project-file").hidden = false;
    $("project-file").open = true;
    importStatus(error.message, true);
  } finally {
    $("import-button").disabled = false;
    $("use-demo").disabled = false;
  }
}

$("import-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const file = $("log-file").files[0];
  if (file) openLog(file);
});
$("project-folder").addEventListener("change", (event) => {
  const files = Array.from(event.target.files).filter((file) =>
    projectExtensions.has(file.name.split(".").at(-1).toLowerCase()) &&
    !file.webkitRelativePath.split("/").slice(1).some((part) => part.startsWith(".") || skippedFolders.has(part.toLowerCase())));
  if (!files.length) return importStatus(tr("This folder has no suitable text files to show."), true);
  if (files.length > 400) return importStatus(tr("The viewer shows at most 400 files per folder. Choose a subfolder."), true);
  const folder = { name: files[0].webkitRelativePath.split("/")[0], files };
  clearPreview();
  const buckets = [];
  Object.assign(state, { source: tr("No log open"), demo: false, playing: false, buckets, terminalBuckets: buckets,
    selected: null, logSelection: null, follow: true, folder, activeFile: null });
  renderProject();
  render();
  $("project-file").hidden = true;
  $("project-file").open = false;
  const trainLog = files.find((file) => file.name.toLowerCase() === "train.log");
  if (trainLog) openLog(trainLog, folder);
});

const projectLinks = [...document.querySelectorAll("[data-project-view]")];
function navigateProject(view) {
  const link = projectLinks.find((item) => item.dataset.projectView === view);
  if (link.href !== location.href) history.pushState(null, "", link.href);
  showView(view);
}
function viewFromLocation() {
  const view = new URLSearchParams(location.search).get("view");
  return view === "editor" || view === "settings" ? view : "monitor";
}
for (const link of projectLinks) {
  link.addEventListener("click", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    // Project, Code and Settings share one page: a click cross-fades like a page change where
    // supported. Code that switches views itself stays synchronous (it focuses right after).
    if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      document.startViewTransition(() => navigateProject(link.dataset.projectView));
    } else navigateProject(link.dataset.projectView);
  });
}
window.addEventListener("popstate", () => showView(viewFromLocation()));
const settingButtons = [...document.querySelectorAll("[data-setting]")];
function showSetting(button) {
  $("settings-path").textContent = button.textContent;
  for (const section of settingButtons) {
    section.setAttribute("aria-pressed", String(section === button));
    $("setting-" + section.dataset.setting).hidden = section !== button;
  }
}
for (const button of settingButtons) {
  button.addEventListener("click", () => {
    showSetting(button);
    try { sessionStorage.setItem("h-logsen-settings-section", button.dataset.setting); } catch { /* per-page preference */ }
  });
}
try {
  const lastSetting = settingButtons.find((button) => button.dataset.setting === sessionStorage.getItem("h-logsen-settings-section"));
  if (lastSetting) showSetting(lastSetting);
} catch { /* use the initial setting section */ }
if (!window.localWorkbench) {
  function openBrowserFolder() {
    const details = $("project-file");
    details.hidden = false;
    details.open = true;
    $("project-folder").focus();
  }
  $("open-project-file").addEventListener("click", openBrowserFolder);
  $("editor-open-project").addEventListener("click", () => {
    navigateProject("monitor");
    openBrowserFolder();
  });
}
function selectPanel(name) {
  const selected = document.querySelector('[data-panel="' + name + '"]');
  for (const button of selected.parentElement.querySelectorAll("[data-panel]")) {
    button.setAttribute("aria-pressed", String(button === selected));
    $(button.dataset.panel).hidden = button !== selected;
  }
  if (name === "training" || name === "machine") {
    $("training-state").hidden = name !== "training";
    $("machine-state").hidden = name !== "machine";
  }
}
document.querySelectorAll("[data-panel]").forEach((button) =>
  button.addEventListener("click", () => selectPanel(button.dataset.panel)));
$("project-files").addEventListener("click", (event) => {
  const button = event.target.closest("[data-project-file]");
  if (!button) return;
  if (button.dataset.localFile !== undefined) {
    const file = state.folder?.files[Number(button.dataset.localFile)] || state.activeFile;
    if (button.dataset.projectFile === "code" || !$("editor").hidden) {
      openPreview(file.name, file.webkitRelativePath || file.name, file);
      return;
    }
    if (file === state.activeFile) document.dispatchEvent(new Event("workspace:show-log"));
    else openLog(file, state.folder);
    return;
  }
  if (button.dataset.demoProject !== state.demoProject) resetDemo(button.dataset.demoProject);
  if (button.dataset.projectFile === "code") {
    const file = button.dataset.fileName;
    openPreview(file, button.dataset.demoProject + "/" + file);
    return;
  }
  if (!$("editor").hidden) navigateProject("monitor");
  previewPath = null;
  const selected = $("project-files").querySelector('[data-demo-project="' + button.dataset.demoProject +
    '"][data-project-file="' + button.dataset.projectFile + '"]');
  for (const file of $("project-files").querySelectorAll("button")) file.setAttribute("aria-pressed", String(file === selected));
  if (button.dataset.projectFile === "log") document.dispatchEvent(new Event("workspace:show-log"));
  else selectPanel(button.dataset.projectFile);
});
$("severity-chart").addEventListener("click", (event) => {
  const button = event.target.closest("[data-bin]");
  if (button) chooseBucket(button.dataset.bin, button.dataset.lane);
});
document.querySelectorAll("[data-activity-mode]").forEach((button, _, buttons) => {
  button.addEventListener("click", () => {
    activityMode = button.dataset.activityMode;
    buttons.forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
    renderActivity(state.buckets.map(summarize));
  });
});
$("activity-live").addEventListener("click", () => {
  chooseBucket("all");
  $("bucket").focus({ preventScroll: true });
});
$("result-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-log]");
  if (!button) return;
  clearMachineTime();
  state.logSelection = state.buckets[Number(button.dataset.openLog)];
  state.follow = false;
  terminalBody.scrollTop = 0;
  document.dispatchEvent(new Event("workspace:show-log"));
  renderTerminal();
});
$("bucket").addEventListener("change", (event) => chooseBucket(event.target.value));
$("pause").addEventListener("click", () => {
  if (state.playing) {
    state.playing = false;
    render();
  } else {
    chooseBucket("all");
  }
});
terminalFollow.addEventListener("click", () => {
  if (state.machineTime != null) {
    clearMachineTime();
    renderTerminal();
    return;
  }
  state.follow = !state.follow;
  if (state.follow && state.selected !== null) return chooseBucket("all");
  if (state.follow) state.logSelection = null;
  renderTerminal();
});
document.addEventListener("workspace:terminal-ready", renderTerminal);
$("use-demo").addEventListener("click", () => {
  resetDemo();
  importStatus("");
  navigateProject("monitor");
  projectLinks[0].focus();
});

const appearanceOptions = $("appearance-options");
function syncAppearanceOptions() {
  for (const option of appearanceOptions.querySelectorAll('input[name="appearance"]')) {
    option.checked = option.value === (document.documentElement.dataset.theme || "graphite");
  }
}
window.addEventListener("pageshow", syncAppearanceOptions);
syncAppearanceOptions();
appearanceOptions.addEventListener("change", (event) => {
  const theme = event.target.value;
  const label = workspaceAppearance.labels.get(theme);
  if (!label) return;
  const saved = workspaceAppearance.set(theme);
  $("appearance-status").textContent = saved ? "✓ " + tr(label) : tr(label);
});

renderProject();
render();
showView(viewFromLocation());
setInterval(() => {
  if (!state.demo) return;
  const time = Math.floor(Date.now() / demoInterval) * demoInterval;
  if (time <= state.terminalBuckets.at(-1).time) return;
  const start = Math.max(state.terminalBuckets.at(-1).time + demoInterval, time - (bucketLimit - 1) * demoInterval);
  const latest = state.terminalBuckets.slice();
  for (let next = start; next <= time; next += demoInterval) latest.push(demoBucket(next));
  state.terminalBuckets = latest.slice(-bucketLimit);
  if (state.playing) {
    state.buckets = state.terminalBuckets;
    render();
  } else if (state.follow) renderTerminal();
}, demoInterval);
