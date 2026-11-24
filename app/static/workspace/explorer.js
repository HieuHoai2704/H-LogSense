"use strict";

window.createWorkbenchExplorer = ({ api: initialApi = window.localWorkbench, onSelect = () => {}, onFile, onError }) => {
  let api = initialApi;
  const $ = (id) => document.getElementById(id);
  const tr = window.logsenseTranslate;
  const number = new Intl.NumberFormat(document.documentElement.lang);
  const tree = $("local-tree");
  const search = $("local-search-input");
  const searchResults = $("local-search-results");
  const searchStatus = $("local-search-status");
  const child = (folder, name) => folder ? folder + "/" + name : name;

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  // Icon kinds are drawn by explorer.css; the label keeps the plain file name for search and tests.
  const fileKinds = {
    code: "py pyw ipynb js mjs cjs ts tsx jsx sh bash zsh ps1 bat cmd c h cpp hpp cs java kt go rs rb php html css scss sql r lua",
    data: "csv tsv json jsonl ndjson parquet xlsx xls yaml yml toml xml npy npz h5 hdf5 db sqlite",
    log: "log out err trace",
    text: "md markdown txt rst pdf doc docx tex",
    image: "png jpg jpeg gif svg webp ico bmp",
    archive: "zip tar gz tgz bz2 xz 7z rar whl"
  };
  const kindByExtension = new Map(Object.entries(fileKinds).flatMap(([kind, list]) => list.split(" ").map((ext) => [ext, kind])));
  function fileKind(name) {
    const dot = name.lastIndexOf(".");
    return dot > 0 ? kindByExtension.get(name.slice(dot + 1).toLowerCase()) || "file" : "file";
  }
  function entryContent(name, kind) {
    const icon = node("span", undefined, "tree-icon");
    icon.dataset.kind = kind;
    icon.setAttribute("aria-hidden", "true");
    return [icon, node("span", name, "tree-label")];
  }

  const checked = new Map();
  let generation = 0;
  let selectedPath = "";
  let viewState;
  let expandedPaths = new Set();
  let searchTimer;
  let searchRequest;
  const request = (path, values) => api.call(api.query(path, values));

  function select(path, directory = false, remember = false) {
    selectedPath = path;
    if (remember && !directory) viewState?.patch({ selected: path });
    onSelect(path, directory);
    for (const button of document.querySelectorAll("#local-tree button[data-path], #local-search-results button[data-path]")) {
      button.setAttribute("aria-pressed", String(button.dataset.path === path));
    }
  }

  async function openFile(path) {
    select(path, false, true);
    await onFile(path);
  }

  function folderButton(name, path) {
    const details = node("details");
    const summary = node("summary");
    const chevron = node("span", undefined, "tree-chevron");
    chevron.setAttribute("aria-hidden", "true");
    summary.append(chevron, ...entryContent(name, "folder"));
    summary.title = name;
    const contents = node("div", undefined, "tree-children");
    details.dataset.path = path;
    details.append(summary, contents);
    const observed = generation;
    details.addEventListener("toggle", () => {
      if (observed !== generation || !details.isConnected) return;
      if (details.open) {
        if (!restoring) {
          select(path, true);
          expandedPaths.delete(path);
          expandedPaths.add(path);
          rememberExpanded();
        }
        restoring = false;
        loadTree(path, contents).catch((error) => onError(error.message));
      } else {
        checked.delete(path);
        expandedPaths.delete(path);
        rememberExpanded();
      }
    });
    let restoring = expandedPaths.has(path);
    if (restoring) details.open = true;
    return details;
  }

  function rememberExpanded() {
    viewState?.patch({ expanded: [...expandedPaths].slice(-32) });
  }

  async function loadTree(path, target, offset = 0) {
    const observed = generation;
    const result = await request("/tree", { path, offset });
    if (generation !== observed || !target.isConnected) return;
    const fingerprint = JSON.stringify(result);
    const previous = checked.get(path);
    if (!offset && previous?.target === target && previous.fingerprint === fingerprint) return;
    if (offset && (previous?.target !== target || previous.next !== offset)) return;
    if (!offset) {
      checked.set(path, { target, fingerprint, paginated: false, next: result.next });
      target.replaceChildren();
    } else {
      previous.paginated = true;
      previous.next = result.next;
      target.querySelector(":scope > .load-more")?.remove();
    }
    for (const entry of result.entries) {
      const next = child(path, entry.name);
      if (entry.directory) target.append(folderButton(entry.name, next));
      else {
        const button = node("button");
        button.append(...entryContent(entry.name, fileKind(entry.name)));
        button.title = entry.name;
        button.type = "button";
        button.dataset.path = next;
        button.setAttribute("aria-pressed", String(selectedPath === next));
        button.addEventListener("click", () => openFile(next).catch((error) => onError(error.message)));
        target.append(button);
      }
    }
    if (result.next !== null) {
      const more = node("button", tr("Show more"), "load-more");
      more.type = "button";
      more.addEventListener("click", async () => {
        more.disabled = true;
        try { await loadTree(path, target, result.next); }
        catch (error) { onError(error.message); }
        finally { more.disabled = false; }
      });
      target.append(more);
    }
  }

  function resetSearch() {
    clearTimeout(searchTimer);
    searchRequest?.abort();
    search.value = "";
    searchResults.replaceChildren();
    searchResults.hidden = true;
    searchStatus.textContent = "";
    tree.hidden = false;
  }

  async function revealFolder(path) {
    const observed = generation;
    resetSearch();
    let parentPath = "";
    let target = tree;
    let folder;
    for (const part of path.split("/")) {
      const nextPath = child(parentPath, part);
      const findFolder = () => [...target.children].find((entry) => entry.dataset.path === nextPath);
      if (checked.get(parentPath)?.target !== target) await loadTree(parentPath, target);
      folder = findFolder();
      while (!folder && observed === generation && checked.get(parentPath)?.next != null) {
        const offset = checked.get(parentPath).next;
        await loadTree(parentPath, target, offset);
        folder = findFolder();
        if (checked.get(parentPath)?.next === offset) break;
      }
      if (observed !== generation) return;
      if (!folder || folder.tagName !== "DETAILS") throw new Error(tr("The folder changed. Search again."));
      folder.open = true;
      parentPath = nextPath;
      target = folder.querySelector(":scope > .tree-children");
    }
    select(path, true);
    folder.querySelector("summary").focus();
  }

  function showSearchResults(result) {
    const rows = result.entries.map((entry) => {
      const item = node("li");
      const button = node("button");
      button.type = "button";
      button.dataset.path = entry.path;
      button.setAttribute("aria-pressed", String(selectedPath === entry.path));
      const [icon, label] = entryContent(entry.name, entry.directory ? "folder" : fileKind(entry.name));
      const text = node("span", undefined, "search-text");
      text.append(label, node("small", entry.path, "search-path"));
      button.append(icon, text);
      button.addEventListener("click", async () => {
        try {
          if (entry.directory) await revealFolder(entry.path);
          else await openFile(entry.path);
        } catch (error) { onError(error.message); }
      });
      item.append(button);
      return item;
    });
    searchResults.replaceChildren(...rows);
    searchStatus.textContent = (rows.length ? number.format(rows.length) + " · " + tr("Results") : tr("No matching files or folders")) +
      (result.partial ? " · " + tr("Search limited. Refine the query.") : "");
  }

  search.addEventListener("input", () => {
    const query = search.value.trim();
    if (!query) return resetSearch();
    clearTimeout(searchTimer);
    searchRequest?.abort();
    const controller = new AbortController();
    searchRequest = controller;
    searchResults.replaceChildren();
    searchResults.hidden = false;
    tree.hidden = true;
    searchStatus.textContent = tr("Searching…");
    searchTimer = setTimeout(async () => {
      try {
        const path = api.query("/tree/search", { q: query });
        const result = await api.call(path, "GET", undefined, false, controller.signal);
        if (!controller.signal.aborted) showSearchResults(result);
      } catch (error) {
        if (!controller.signal.aborted) searchStatus.textContent = error.message;
      }
    }, 220);
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && search.value) {
      event.preventDefault();
      resetSearch();
    }
  });

  async function refreshTree() {
    for (const [path, item] of [...checked].slice(0, 12)) {
      if (!item.target.isConnected) checked.delete(path);
      else if (!item.paginated) await loadTree(path, item.target);
    }
  }

  async function open(root, scope = initialApi, preferences = null) {
    generation += 1;
    api = scope;
    viewState = preferences;
    expandedPaths = new Set(preferences?.data.expanded || []);
    resetSearch();
    $("local-search").hidden = !root;
    const rootLabel = $("local-active-root");
    const name = $("local-root-name");
    name.hidden = !root;
    name.textContent = root ? root.split(/[\\/]/).filter(Boolean).at(-1) || root : "";
    name.title = root || "";
    rootLabel.textContent = root || tr("No folder selected");
    rootLabel.title = root || "";
    checked.clear();
    tree.replaceChildren();
    select(root ? preferences?.data.selected || "" : "");
    if (root) await loadTree("", tree);
  }

  return { open, select, refresh: refreshTree };
};

window.bindWorkbenchFolder = ({ getScope, onOpen, canOpen = () => true }) => {
  const $ = (id) => document.getElementById(id);
  const button = $("open-project-file");
  const form = $("local-project-form");
  const input = $("local-root");
  const recent = $("local-recent");
  const submit = form.querySelector('[type="submit"]');
  const feedback = $("local-folder-feedback");
  const tr = window.logsenseTranslate;
  let busy = false;
  let displayedScope = null;

  function report(scope, message = "", tone = "") {
    if (scope !== displayedScope) return;
    feedback.dataset.tone = tone;
    feedback.hidden = !message;
    feedback.textContent = message;
  }

  function show(visible) {
    form.hidden = !visible;
    button.setAttribute("aria-expanded", String(visible));
    if (visible) {
      input.focus();
      input.select();
    }
  }

  async function choose(scope, pick) {
    if (busy) return;
    busy = true;
    button.disabled = submit.disabled = recent.disabled = true;
    report(scope);
    const previous = scope.root;
    let accepted = false;
    try {
      const path = await pick();
      if (!path || (previous !== path && !canOpen(scope))) {
        report(scope, tr("Folder selection canceled"));
        return;
      }
      report(scope, tr("Opening folder…"));
      await scope.view?.flush();
      const result = await scope.api.call("/project", "POST", { path });
      accepted = true;
      await onOpen(result, scope);
      report(scope, tr(result.root === previous ? "Folder already open" : "Folder switched"));
      show(false);
      button.focus({ preventScroll: true });
    } catch (error) {
      report(scope, tr(accepted ? "Folder contents could not be loaded" : "Could not open folder") + " · " + error.message, "error");
    }
    finally {
      busy = false;
      button.disabled = submit.disabled = recent.disabled = false;
    }
  }

  button.addEventListener("click", () => {
    const scope = getScope();
    if (document.documentElement.hasAttribute("data-workbench-desktop")) choose(scope, scope.api.pickProject);
    else show(form.hidden);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const path = input.value;
    choose(getScope(), () => path);
  });
  recent.addEventListener("change", () => {
    const path = recent.value;
    choose(getScope(), () => path);
  });
  function cancel() {
    show(false);
    report(getScope(), tr("Folder selection canceled"));
    button.focus({ preventScroll: true });
  }
  $("local-folder-cancel").addEventListener("click", cancel);
  form.addEventListener("keydown", (event) => {
    if (event.key === "Escape") cancel();
  });
  return {
    update(scope) {
      if (displayedScope !== scope) {
        displayedScope = scope;
        report(scope);
      }
      button.disabled = busy;
      input.value = scope.root || "";
      recent.replaceChildren(new Option(window.logsenseTranslate("Recent projects"), ""),
        ...scope.recent.map((path) => new Option(path, path)));
    },
    hide: () => show(false),
  };
};
