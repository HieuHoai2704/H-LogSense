"use strict";

(() => {
  const api = window.localWorkbench;
  const controls = document.getElementById("local-project-form");
  if (!controls || !api) return;

  const codeApi = api.scope("code");
  const projectScope = { api, root: null, recent: [], view: window.createWorkbenchViewState(api) };
  const codeScope = { api: codeApi, root: null, recent: [], view: window.createWorkbenchViewState(codeApi) };
  const visibleScope = () => $("editor").hidden ? projectScope : codeScope;
  const status = $("local-status");
  const runList = $("local-runs");
  const runDetail = window.WorkbenchRunDetail;
  const compare = window.WorkbenchRunCompare;
  let current = null;
  let generation = 0;
  let logPath = null;
  let logCursor = {};
  let logView = 0;
  let logRequest = 0;
  let logApplied = 0;
  let run = null;
  let selectedPath = "";
  let selectedDirectory = false;
  let machineHistory = [];
  let refreshDue = 0;
  let refreshRunning = false;
  let codeRefreshDue = 0;

  const request = (path, values) => api.call(api.query(path, values));
  const setStatus = (message) => { status.textContent = message; };
  const codeEditor = window.createWorkbenchEditor({ api: codeApi, onStatus: setStatus,
    onLayout(editor) { if (codeScope.root) codeScope.view.patch({ editor }); } });
  const codeFile = (path) => /\.pdf$/i.test(path) || projectExtensions.has(path.split(".").at(-1).toLowerCase());

  function updateSelection(path, directory) {
    selectedPath = path;
    selectedDirectory = directory;
    document.querySelector('[data-file-action="rename"]').disabled = !path;
    $("local-selected").textContent = path || "Thư mục gốc";
    const canWatch = !directory && visibleScope().root === current && /\.(log|txt|jsonl)$/i.test(path);
    const canEdit = !directory && codeFile(path);
    $("local-watch-log").hidden = !canWatch;
    $("local-open-editor").hidden = !canEdit;
    $("local-file-actions").hidden = !canWatch && !canEdit;
  }

  const explorer = window.createWorkbenchExplorer({
    onSelect: updateSelection,
    onFile(path) {
      setStatus("");
      if (!$("monitor").hidden) {
        if (/\.log$/i.test(path)) return watchLog(path);
        if (/^metrics\.csv$/i.test(path.split("/").at(-1))) selectPanel("training");
        if (/^machine\.jsonl$/i.test(path.split("/").at(-1))) selectPanel("machine");
        return;
      }
      if (!$("editor").hidden && codeFile(path)) {
        return selectFile(path);
      }
    },
    onError: setStatus,
  });

  let projectOutput = { text: "", entries: [] };
  let codeRun = null;

  const runActive = (record) => Boolean(record && ["starting", "running"].includes(record.status));
  function syncCodeRunStatus() {
    const selected = !$("editor").hidden && codeScope.root !== current ? codeRun : null;
    $("dock-output-run").hidden = !selected;
    $("dock-output-status").textContent = selected ? selected.script + " · " + selected.status : "";
    $("dock-output-stop").hidden = !runActive(selected);
  }

  function syncDockOutput() {
    const codeOnly = !$("editor").hidden && codeScope.root !== current;
    syncCodeRunStatus();
    const output = codeOnly ? codeRun?.output : projectOutput;
    window.WorkbenchDock.updateLog(output?.text || "", output?.entries || [], visibleScope().root);
  }

  function parseLog(text, source) {
    const lines = text.split(/\r?\n/);
    return lines.flatMap((line, index) => {
      if (!line.trim()) return [];
      try {
        return [parseEntry(line, index + 1, /\.jsonl$/i.test(source))];
      } catch {
        return [];
      }
    });
  }

  function applyLog(text, source) {
    const entries = parseLog(text, source);
    const buckets = entries.length ? groupEntries(entries) : [];
    const sameSource = !state.demo && state.localSource === source;
    Object.assign(state, { demo: false, playing: false, source, localSource: source === tr("No log open") ? null : source,
      terminalBuckets: buckets });
    if (!sameSource) Object.assign(state, { buckets, selected: null, logSelection: null });
    else if (state.selected === null) state.buckets = buckets;
    render();
    projectOutput = { text, entries };
    syncDockOutput();
  }

  async function readSelectedLog() {
    const view = logView;
    const sequence = ++logRequest;
    const source = logPath;
    const selectedRun = run;
    let result;
    try {
      result = selectedRun
        ? await request("/runs/" + selectedRun, logCursor)
        : source ? { log: await request("/log", { path: source, ...logCursor }) } : null;
    } catch (error) {
      if (view === logView && sequence > logApplied) {
        logApplied = sequence;
        state.logUnavailable = true;
        if (selectedRun) {
          state.machineLive = false;
          renderMetrics();
        }
        renderActivityStatus();
        throw error;
      }
      return;
    }
    if (!result || view !== logView || sequence < logApplied) return;
    logApplied = sequence;
    state.logUnavailable = false;
    const log = result.log;
    logCursor = { offset: log.offset, stamp: log.stamp };
    if (log.changed) applyLog(log.text, source || result.run.log || result.run.script + " · " + selectedRun.slice(0, 8));
    else renderActivityStatus();
    if (result.run) {
      runDetail.update(result);
      state.training = result.training;
      state.machine = result.machine;
      state.runStatus = result.run.status;
      state.machineLive = ["starting", "running"].includes(state.runStatus);
      const attached = result.run.source === "attached";
      state.machineSource = attached ? "attached" : "run";
      state.machinePid = attached ? result.run.pid : null;
      $("local-run-status").textContent = result.run.script + " · " + result.run.status;
      $("local-stop-run").hidden = attached || !["starting", "running"].includes(result.run.status);
      renderMetrics();
    }
  }

  async function watchLog(path, restore = false) {
    if (!restore) explorer.select(path, false, true);
    logPath = path;
    run = null;
    resetLogView();
    applyLog("", path);
    runList.value = "";
    $("local-stop-run").hidden = true;
    $("local-run-status").textContent = "";
    if (!restore) navigateProject("monitor");
    await readSelectedLog();
    if (!restore && logPath === path) projectScope.view.patch({ log: path });

  }

  async function selectFile(path, target = null, root = visibleScope().root) {
    if (root !== codeScope.root) {
      setStatus("Mở thư mục này trong tab Code để chỉnh sửa tệp: " + root);
      return;
    }
    const pane = await codeEditor.open(path);
    if (codeScope.root !== root || !pane) return;
    navigateProject("editor");
    explorer.select(path, false, true);
    codeEditor.focus(pane, target);
  }

  document.addEventListener("workbench:open-source", ({ detail }) => {
    selectFile(detail.path, detail, detail.root).catch((error) => setStatus(error.message));
  });

  function setScope(scope, result) {
    scope.root = result.root;
    scope.recent = result.recent;
    scope.api.setProject(result.project);
  }

  let shownScope = null;
  let shownRoot = null;
  async function showExplorer() {
    const scope = visibleScope();
    if (shownScope === scope && shownRoot === scope.root) return;
    shownScope = scope;
    shownRoot = scope.root;
    cancelFileAction(false);
    folderChooser.hide();
    folderChooser.update(scope);
    $("local-explorer-title").textContent = tr(scope === codeScope ? "Code folder" : "Project folders");
    $("local-controls").hidden = !scope.root;
    syncDockOutput();
    const root = scope.root;
    try { await explorer.open(root, scope.api, scope.view); }
    catch (error) {
      if (shownScope === scope && shownRoot === root) shownScope = null;
      throw error;
    }
  }

  async function openProjectRoot(result) {
    generation += 1;
    current = result.root;
    setScope(projectScope, result);
    compare.clear();
    logPath = null;
    run = null;
    resetLogView();
    machineHistory = [];
    Object.assign(state, { localRoot: current, localSource: null, machine: [], machineSource: null, training: [] });
    window.WorkbenchDock.rootChanged("project");
    applyLog("", tr("No log open"));
    state.localSource = null;
    renderProject();
    render();
    $("local-stop-run").hidden = true;
    $("local-run-status").textContent = "";
    runList.replaceChildren(new Option(tr("Run history"), ""));
    refreshDue = 0;
    await projectScope.view.load(current);
    const savedLog = projectScope.view.data.log;
    if (savedLog) {
      try { await watchLog(savedLog, true); }
      catch {
        logPath = null;
        resetLogView();
        applyLog("", tr("No log open"));
        projectScope.view.patch({ log: "" });
      }
    }
  }

  const codeInterpreter = $("code-interpreter");
  async function refreshCodeInterpreter() {
    const root = codeScope.root;
    codeInterpreter.hidden = true;
    if (!root) return;
    const info = await codeApi.call("/environment");
    if (root !== codeScope.root) return;
    codeInterpreter.replaceChildren(...Object.entries(info.interpreters).map(([key, path]) => {
      const option = new Option(key === "app" ? "Python của H-logsen" : "Python · " + key, key);
      option.title = path;
      return option;
    }));
    codeInterpreter.value = info.selected;
    codeInterpreter.title = info.interpreters[info.selected];
    codeInterpreter.hidden = false;
  }

  codeInterpreter.addEventListener("change", async () => {
    const root = codeScope.root;
    const interpreter = codeInterpreter.value;
    codeInterpreter.disabled = true;
    try {
      await codeApi.call("/environment", "PUT", { interpreter });
      if (root === codeScope.root) setStatus("Đã chọn Python. Mở phiên terminal mới để dùng môi trường này.");
    } catch (error) { setStatus(error.message); }
    finally {
      codeInterpreter.disabled = false;
      if (root === codeScope.root) refreshCodeInterpreter().catch((error) => setStatus(error.message));
    }
  });

  async function openCodeRoot(result) {
    codeRun = null;
    setScope(codeScope, result);
    refreshCodeInterpreter().catch((error) => { if (!$("editor").hidden) setStatus(error.message); });
    await codeScope.view.load(result.root);
    await codeEditor.restore(codeScope.view.data.editor);
    state.codeRoot = result.root;
    window.WorkbenchDock.rootChanged("code");
    renderProject();
  }

  const folderChooser = window.bindWorkbenchFolder({
    getScope: visibleScope,
    canOpen: (scope) => scope !== codeScope || codeEditor.canDiscard(),
    onOpen: async (result, scope) => {
      if (scope === codeScope) {
        if (result.root !== scope.root) await openCodeRoot(result);
        else setScope(scope, result);
      } else {
        if (result.root !== scope.root) await openProjectRoot(result);
        else setScope(scope, result);
        if (!codeScope.root) await openCodeRoot(await codeApi.call("/session"));
      }
      if (scope === visibleScope()) await showExplorer();
      setStatus("");
    },
  });
  document.addEventListener("workbench:view", ({ detail }) => {
    if (detail !== "settings") {
      showExplorer().catch((error) => setStatus(error.message));
      setStatus("");
    }
  });

  function submit(form, action) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      button.disabled = true;
      try { await action(); }
      catch (error) { setStatus(error.message); }
      finally { button.disabled = false; }
    });
  }

  $("local-open-editor").addEventListener("click", () => selectFile(selectedPath).catch((error) => setStatus(error.message)));
  $("local-watch-log").addEventListener("click", () => {
    watchLog(selectedPath).then(() => document.dispatchEvent(new Event("workspace:show-log")))
      .catch((error) => setStatus(error.message));
  });
  const manage = $("local-manage");
  const fileName = $("local-target");
  const fileStatus = $("local-file-status");
  let pendingAction = null;
  function cancelFileAction(restoreFocus = true) {
    const trigger = pendingAction?.button;
    pendingAction = null;
    manage.hidden = true;
    if (restoreFocus) trigger?.focus();
  }

  for (const button of $("local-controls").querySelectorAll("[data-file-action]")) {
    button.addEventListener("click", () => {
      const action = button.dataset.fileAction;
      const scope = visibleScope();
      if (action === "rename" && scope.root === codeScope.root && codeEditor.hasOpen(selectedPath)) {
        setStatus("Đóng tệp đang mở trong Code trước khi đổi tên.");
        return;
      }
      const lastSlash = selectedPath.lastIndexOf("/");
      const parent = selectedDirectory && action !== "rename" ? selectedPath : selectedPath.slice(0, Math.max(0, lastSlash));
      pendingAction = { action, parent, path: selectedPath, directory: selectedDirectory, button, scope, root: scope.root };
      const title = { file: "Tạo tệp", directory: "Tạo thư mục", rename: "Đổi tên" }[action];
      $("local-file-label").textContent = title + " · " + (parent || "Thư mục gốc");
      fileName.value = action === "rename" ? selectedPath.split("/").at(-1) : "";
      fileStatus.textContent = "";
      manage.hidden = false;
      fileName.select();
      fileName.focus();
    });
  }
  $("local-file-cancel").addEventListener("click", cancelFileAction);
  manage.addEventListener("keydown", (event) => {
    if (event.key === "Escape") cancelFileAction();
  });
  submit(manage, async () => {
    const pending = pendingAction;
    if (!pending || pending.scope.root !== pending.root) return;
    const name = fileName.value.trim();
    if (!name || /[/\\]/.test(name)) {
      fileStatus.textContent = "Nhập tên, không kèm đường dẫn.";
      fileName.focus();
      return;
    }
    const target = pending.parent ? pending.parent + "/" + name : name;
    const { action, path } = pending;
    try {
      if (action === "rename" && pending.root === codeScope.root && codeEditor.hasOpen(path)) {
        fileStatus.textContent = "Đóng tệp đang mở trong Code trước khi đổi tên.";
        return;
      }
      await pending.scope.api.call("/tree", "POST", action === "rename" ? { action, path, target } : { action, path: target });
      if (pending.scope.root !== pending.root || pendingAction !== pending) return;
      explorer.select(target, action === "directory" || (action === "rename" && pending.directory));
      cancelFileAction();
      await explorer.refresh();
      setStatus("Đã cập nhật cây dự án.");
    } catch (error) {
      if (pendingAction === pending) fileStatus.textContent = error.message;
    }
  });

  function resetLogView() {
    clearMachineTime();
    if (["run", "attached"].includes(state.machineSource)) {
      state.machine = [];
      state.machineSource = null;
      state.machinePid = null;
    }
    logView += 1;
    logCursor = {};
    state.logUnavailable = false;
    state.selected = null;
    state.logSelection = null;
    state.follow = true;
    state.runStatus = null;
    state.machineLive = false;
    runDetail.clear();
  }

  async function selectRun(id) {
    run = id || null;
    resetLogView();
    if (run) {
      logPath = null;
      $("local-run-status").textContent = "Đang đọc lượt chạy…";
      $("local-stop-run").hidden = true;
      navigateProject("monitor");
      renderMetrics();
      await readSelectedLog();
    } else {
      logPath = null;
      $("local-run-status").textContent = "";
      $("local-stop-run").hidden = true;
      applyLog("", tr("No log open"));
      state.localSource = null;
    }
  }

  $("use-demo").addEventListener("click", () => {
    run = logPath = null;
    resetLogView();
    compare.clear();
    runList.value = "";
    $("local-run-status").textContent = "";
    $("local-stop-run").hidden = true;
  });

  $("local-run-file").addEventListener("click", async () => {
    const file = codeEditor.file();
    if (!file || codeEditor.dirty()) return setStatus("Lưu tệp trước khi chạy.");
    if (codeScope.root !== current && runActive(codeRun)) return setStatus("Dừng lượt chạy hiện tại trước khi chạy tệp khác.");
    try {
      $("local-run-file").disabled = true;
      const raw = $("local-run-args").value.trim();
      const configFiles = $("local-run-config").value.split(/\r?\n/).map((path) => path.trim()).filter(Boolean);
      const root = codeScope.root;
      const record = await codeApi.call("/runs", "POST", { script: file.path, args: raw ? JSON.parse(raw) : [], config_files: configFiles });
      if (codeScope.root !== root) return;
      if (root === current) {
        await selectRun(record.id);
        refreshDue = 0;
      } else {
        codeRun = { id: record.id, script: file.path, status: record.status, cursor: {}, output: null };
        if (!$("editor").hidden) {
          syncDockOutput();
          window.WorkbenchDock.show("output");
        }
        await refreshCodeRun();
      }
      setStatus("Đã khởi động lượt chạy.");
    } catch (error) { setStatus(error.message); }
    finally { $("local-run-file").disabled = false; }
  });
  runList.addEventListener("change", () => selectRun(runList.value).catch((error) => setStatus(error.message)));
  const attachDialog = $("attach-run-dialog");
  const attachForm = $("attach-run-form");
  const attachMode = $("attach-run-mode");
  const attachError = $("attach-run-error");
  function updateAttachForm() {
    const byPid = attachMode.value === "pid";
    $("attach-run-pid-fields").hidden = !byPid;
    $("attach-run-id-field").hidden = byPid;
    for (const name of ["pid", "log", "metrics"]) attachForm.elements[name].disabled = !byPid;
    attachForm.elements.run_id.disabled = byPid;
    attachForm.elements.run_id.required = !byPid;
    $("attach-run-hint").textContent = byPid
      ? "Chọn PID đang chạy trong dự án. Tệp log và CSV loss là tùy chọn."
      : "Nhập ID lượt chạy H-logsen hoặc ID đã đăng ký trong runs/<run_id>/h-logsen.json.";
    attachError.hidden = true;
  }
  attachMode.addEventListener("change", updateAttachForm);
  $("open-attach-run").addEventListener("click", () => {
    if (!current) return setStatus("Mở thư mục dự án trước khi gắn lượt chạy.");
    updateAttachForm();
    attachDialog.showModal();
  });
  $("attach-run-cancel").addEventListener("click", () => attachDialog.close());
  submit(attachForm, async () => {
    attachError.hidden = true;
    const observed = generation;
    const values = Object.fromEntries(new FormData(attachForm));
    if ("pid" in values) values.pid = Number(values.pid);
    try {
      const record = await api.call("/runs/attach", "POST", values);
      if (observed !== generation || !attachDialog.open) return;
      attachDialog.close();
      await selectRun(record.id);
      refreshDue = 0;
    } catch (error) {
      if (!attachDialog.open) return setStatus(error.message);
      attachError.textContent = error.message;
      attachError.hidden = false;
    }
  });
  $("local-stop-run").addEventListener("click", async () => {
    if (!run) return;
    const button = $("local-stop-run");
    button.disabled = true;
    try {
      await api.call("/runs/" + run + "/stop", "POST");
      setStatus("Đã yêu cầu dừng lượt chạy.");
    } catch (error) { setStatus(error.message); }
    finally { button.disabled = false; }
  });

  async function refreshEnvironment(packages = false) {
    if (!current) return;
    const info = await request("/environment", { packages: packages ? 1 : null });
    $("local-interpreter").replaceChildren(...Object.entries(info.interpreters).map(([key, path]) => new Option(key + " · " + path, key)));
    $("local-interpreter").value = info.selected;
    if (info.packages) {
      $("local-package-list").textContent = "Python " + info.version + "\n" + info.packages.map((item) => item.join(" ")).join("\n");
    }
  }
  $("local-interpreter").addEventListener("change", async (event) => {
    try {
      await api.call("/environment", "PUT", { interpreter: event.target.value });
      $("local-package-list").textContent = "Đã đổi interpreter. Bấm xem gói để tải danh sách.";
      if (current === codeScope.root) await refreshCodeInterpreter();
    } catch (error) { setStatus(error.message); }
  });
  $("local-list-packages").addEventListener("click", () => refreshEnvironment(true).catch((error) => setStatus(error.message)));
  document.querySelector('[data-setting="environments"]').addEventListener("click", () => refreshEnvironment().catch((error) => setStatus(error.message)));

  submit($("local-ssh"), async () => {
    if (!current) throw new Error("Mở một dự án cục bộ trước.");
    const values = Object.fromEntries(new FormData($("local-ssh")));
    navigateProject("monitor");
    document.dispatchEvent(new CustomEvent("workspace:ssh", { detail: { shell: "SSH", host: values.host, user: values.user, port: Number(values.port) } }));
  });
  $("local-features").addEventListener("change", async (event) => {
    const input = event.target;
    if (!input.name) return;
    input.disabled = true;
    try { await api.call("/features", "PUT", { feature: input.name, enabled: input.checked }); }
    catch (error) { input.checked = !input.checked; setStatus(error.message); }
    finally { input.disabled = false; }
  });

  async function refreshProject() {
    const observed = generation;
    const [metrics, recent] = await Promise.all([request("/metrics", { sample: 1 }), api.call("/runs")]);
    if (observed !== generation || state.demo) return;
    if (!run) {
      if (metrics.live) {
        machineHistory = [...machineHistory, metrics.live].slice(-120);
      }
      state.machine = metrics.machine.length ? metrics.machine : machineHistory;
      state.machineSource = metrics.machine.length ? "file" : machineHistory.length ? "host" : null;
      state.training = metrics.training;
      state.machineLive = !metrics.machine.length && Boolean(metrics.live);
      renderMetrics();
    }
    $("local-metric-status").textContent = metrics.warnings.join(" ");
    const selected = run || "";
    runList.replaceChildren(new Option(tr("Run history"), ""), ...recent.runs.map((item) =>
      new Option(item.script + " · " + item.status + " · " + new Date(item.started_at).toLocaleString("vi"), item.id)));
    runList.value = selected;
    compare.setRuns(recent.runs.filter((item) => item.source !== "attached"), selected);
    if (visibleScope() === projectScope) await explorer.refresh();
    if (observed === generation && !state.demo && !run && !logPath && metrics.default_log) {
      logPath = metrics.default_log;
      applyLog("", logPath);
      await readSelectedLog();
    }
  }

  async function refreshCodeRun() {
    const selected = codeRun;
    if (!runActive(selected) || selected.pending) return;
    selected.pending = true;
    try {
      const result = await codeApi.call(codeApi.query("/runs/" + selected.id, selected.cursor));
      if (selected !== codeRun) return;
      selected.status = result.run.status;
      const log = result.log;
      selected.cursor = { offset: log.offset, stamp: log.stamp };
      if (log.changed) selected.output = { text: log.text, entries: parseLog(log.text, "") };
      if (!$("editor").hidden) {
        if (log.changed) syncDockOutput();
        syncCodeRunStatus();
      }
    } finally { selected.pending = false; }
  }
  $("dock-output-stop").addEventListener("click", async (event) => {
    if (!runActive(codeRun)) return;
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await codeApi.call("/runs/" + codeRun.id + "/stop", "POST");
      await refreshCodeRun();
    } catch (error) { setStatus(error.message); }
    finally { button.disabled = false; }
  });

  async function tick() {
    try {
      if (codeScope.root && !$("editor").hidden && Date.now() >= codeRefreshDue) {
        codeRefreshDue = Date.now() + 4000;
        refreshCodeRun().catch((error) => setStatus(error.message));
        if (visibleScope() === codeScope) explorer.refresh().catch((error) => setStatus(error.message));
      }
      if (current && !state.demo) {
        await readSelectedLog().catch((error) => setStatus(error.message));
        if (Date.now() >= refreshDue && !refreshRunning) {
          refreshDue = Date.now() + 4000;
          refreshRunning = true;
          const observed = generation;
          refreshProject().catch((error) => {
            if (observed !== generation) return;
            if (!run && state.machineLive) {
              state.machineLive = false;
              renderMetrics();
            }
            setStatus(error.message);
          }).finally(() => { refreshRunning = false; });
        }
      }
    } catch (error) { setStatus(error.message); }
    finally { setTimeout(tick, 900); }
  }

  async function initialize() {
    try {
      const [info, codeInfo] = await Promise.all([api.call("/session"), codeApi.call("/session")]);
      const shellPicker = $("local-shell");
      shellPicker.replaceChildren(...info.shells.map((shell) => new Option(shell, shell)));
      if (info.os === "win32" && info.shells.includes("CMD")) shellPicker.value = "CMD";
      for (const input of $("local-features").querySelectorAll("input[name]")) input.checked = Boolean(info.features[input.name]);
      await openProjectRoot(info);
      await openCodeRoot(codeInfo);
      if (shellPicker.value) document.dispatchEvent(new Event("workspace:shells-ready"));
      await showExplorer();
      tick();
    } catch (error) { setStatus(error.message); }
  }

  initialize();
})();
