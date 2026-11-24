"use strict";

(() => {
  const tr = window.logsenseTranslate;
  const panel = document.getElementById("run-compare");
  if (!panel) return;
  const toggle = document.getElementById("run-compare-toggle");
  const close = document.getElementById("run-compare-close");
  function show(visible) {
    panel.hidden = !visible;
    toggle.setAttribute("aria-expanded", String(visible));
    (visible ? close : toggle).focus({ preventScroll: true });
  }
  toggle.addEventListener("click", () => show(panel.hidden));
  close.addEventListener("click", () => show(false));
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) show(false);
  });

  const form = panel.querySelector("form");
  const left = form.elements.left;
  const right = form.elements.right;
  const submit = form.querySelector("button");
  const status = document.getElementById("run-compare-status");
  const content = document.getElementById("run-compare-content");
  const body = document.getElementById("run-compare-rows");
  const formatter = new Intl.NumberFormat(document.documentElement.lang, { maximumSignificantDigits: 7 });
  const numeric = (value, suffix = "") => Number.isFinite(value) ? formatter.format(value) + suffix : null;
  let revision = 0;
  let runKey = "";
  let pending = false;

  function syncSubmit() {
    submit.disabled = pending || !left.value || !right.value || left.value === right.value;
  }

  function invalidate() {
    revision += 1;
    pending = false;
    content.hidden = true;
    status.textContent = "";
    syncSubmit();
  }

  function setRuns(runs, selected) {
    const key = JSON.stringify(runs.map(({ id, status }) => [id, status]));
    if (key === runKey) return;
    runKey = key;
    const ids = new Set(runs.map((run) => run.id));
    const oldLeft = left.value;
    const oldRight = right.value;
    for (const select of [left, right]) {
      select.replaceChildren(new Option(tr("Choose a run"), ""), ...runs.map((run) =>
        new Option(run.script + " · " + run.status + " · " + new Date(run.started_at).toLocaleString(document.documentElement.lang) + " · " + run.id.slice(0, 8), run.id)));
    }
    left.value = ids.has(oldLeft) ? oldLeft : ids.has(selected) ? selected : runs[0]?.id ?? "";
    right.value = ids.has(oldRight) ? oldRight : runs.find((run) => run.id !== left.value)?.id ?? "";
    if (left.value !== oldLeft || right.value !== oldRight) invalidate();
    if (runs.length < 2) status.textContent = tr("At least two runs are needed in the project.");
    syncSubmit();
  }

  function clear() {
    runKey = "";
    left.replaceChildren();
    right.replaceChildren();
    invalidate();
  }

  function add(label, first, second, showChange = false) {
    const row = document.createElement("tr");
    const header = document.createElement("th");
    header.scope = "row";
    header.textContent = label;
    row.append(header);
    for (const value of [first, second]) {
      const cell = document.createElement("td");
      cell.textContent = value ?? "—";
      row.append(cell);
    }
    if (showChange && first != null && second != null && first !== second) row.dataset.changed = "true";
    body.append(row);
  }

  function gitLabel(profile) {
    const git = profile?.git;
    if (git?.status !== "available") return null;
    const state = git.dirty === null ? tr("changes unknown") : git.dirty ? tr("uncommitted changes") : tr("clean");
    return [git.commit, git.branch, state].filter(Boolean).join(" · ");
  }

  function environmentLabel(profile) {
    const info = profile?.interpreter;
    return info ? [info.id, info.version, info.platform, info.architecture, info.executable].filter(Boolean).join(" · ") : null;
  }

  function elapsed(run) {
    if (!run.ended_at) return null;
    const seconds = (Date.parse(run.ended_at) - Date.parse(run.started_at)) / 1000;
    return seconds >= 0 ? numeric(seconds, " s") : null;
  }

  function loss(first, second, field, container) {
    const series = [first, second].map((points) => new Map(points.map((point) => [point.epoch, point[field]])));
    const epochs = [...new Set([...series[0].keys(), ...series[1].keys()])].sort((a, b) => a - b);
    const rows = epochs.map((epoch) => ({ epoch, left: series[0].get(epoch), right: series[1].get(epoch) }));
    renderMeasured(document.getElementById(container), rows, ["left", "right"], [tr("Run A"), tr("Run B")], "epoch");
    return rows.filter((row) => Number.isFinite(row.left) && Number.isFinite(row.right)).at(-1);
  }

  function render([first, second]) {
    body.replaceChildren();
    add(tr("Compared run"), first.run.script + " · " + first.run.id, second.run.script + " · " + second.run.id);
    add(tr("Status"), first.run.status, second.run.status);
    add(tr("Time since the run was requested"), elapsed(first.run), elapsed(second.run));
    add("Git", gitLabel(first.profile), gitLabel(second.profile), true);
    add("Python", environmentLabel(first.profile), environmentLabel(second.profile), true);
    add(tr("Script SHA-256"), first.profile?.script.sha256, second.profile?.script.sha256, true);
    const parameters = (profile) => profile?.parameters.map(({ name, value }) => name + "=" + value).join(" · ") || null;
    add(tr("Recorded numeric parameters"), parameters(first.profile), parameters(second.profile), true);
    const files = [first, second].map((item) => new Map(item.profile?.config_files.map((file) => [file.path, file.sha256]) ?? []));
    for (const path of new Set([...files[0].keys(), ...files[1].keys()])) {
      add(path, files[0].get(path), files[1].get(path), true);
    }
    for (const [key, label, unit] of [["cpu_percent", "CPU", "%"], ["gpu_percent", "GPU", "%"],
      ["ram_percent", "RAM", "%"], ["vram_used_mib", "VRAM", " MiB"]]) {
      const peak = (run) => {
        const measure = run.machine[key];
        return measure.samples ? numeric(measure.peak, unit) + " · " + window.logsenseTranslatePlural(measure.samples, "{0} sample", "{0} samples", measure.samples) : null;
      };
      add(tr("Peak {0}", label), peak(first), peak(second));
    }
    for (const [field, label, id] of [["train_loss", "Train loss", "compare-train-loss"],
      ["val_loss", "Validation loss", "compare-validation-loss"]]) {
      const latest = loss(first.training, second.training, field, id);
      add(label + (latest ? " · epoch " + latest.epoch : " · " + tr("no shared epoch")),
        numeric(latest?.left), numeric(latest?.right));
    }
    content.hidden = false;
    status.textContent = tr("Compared the two runs. Loss and machine load use at most 120 points read per run.");
  }

  form.addEventListener("change", invalidate);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submit.disabled) return;
    const observed = ++revision;
    pending = true;
    syncSubmit();
    content.hidden = true;
    status.textContent = tr("Reading both runs…");
    try {
      const api = window.localWorkbench;
      const result = await api.call(api.query("/runs/compare", { left: left.value, right: right.value }));
      if (observed === revision) render(result.runs);
    } catch (error) {
      if (observed === revision) status.textContent = error.message;
    } finally {
      if (observed === revision) {
        pending = false;
        syncSubmit();
      }
    }
  });

  clear();
  window.WorkbenchRunCompare = { setRuns, clear };
})();
