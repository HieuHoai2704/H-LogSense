"use strict";

const workbenchHighlightUrl = new URL("code-highlight-worker.js", document.currentScript.src);
window.createWorkbenchEditor = ({ api, onStatus, onLayout }) => {
  const $ = (id) => document.getElementById(id);
  const status = $("local-editor-status");
  const save = $("local-save");
  const run = $("local-run-file");
  const runCode = $("local-run-code");
  const check = $("local-check-code");
  const format = $("local-format-code");
  const formatExtensions = new Set(["py", "js", "ts", "json", "css", "html", "md", "yaml", "yml"]);
  const split = $("code-split");
  const divider = $("code-divider");
  const group = $("code-panes");
  const grammars = { py: "python", js: "javascript", ts: "typescript", json: "json", md: "markdown",
    html: "xml", css: "css", yaml: "yaml", yml: "yaml", sh: "bash", ps1: "powershell", sql: "sql" };

  const panes = [...group.querySelectorAll(".code-pane")].map((element) => {
    const find = (selector) => element.querySelector(selector);
    return { element, tab: find(".code-tab"), close: find(".code-close"), empty: find(".code-empty"),
      layer: find(".local-editor-layer"), editor: find("textarea"), highlight: find(".code-highlight"),
      pdf: find(".pdf-preview"), previous: find('[data-pdf="previous"]'), next: find('[data-pdf="next"]'),
      pageLabel: find(".pdf-page"), pdfStatus: find(".pdf-status"), image: find("img"), zoom: find(".pdf-zoom"),
      label: find(".code-tab").textContent, revision: 0, highlightRevision: 0, file: null, saving: false };
  });
  const [left, right] = panes;
  let active = left;
  let restoring = false;
  let highlighter;
  let highlightFailed = false;
  let checking = false;
  let formatting = false;

  const dirty = (pane) => Boolean(pane.file?.kind === "text" && pane.editor.value !== pane.file.original);
  function canDiscard(candidates = panes) {
    if (candidates.some((pane) => pane.saving)) {
      onStatus("Đợi lưu tệp xong rồi thử lại.");
      return false;
    }
    return !candidates.some(dirty) || window.confirm("Bỏ thay đổi chưa lưu trong tệp đang mở?");
  }

  function update(persist = true) {
    for (const pane of panes) {
      const path = pane.file?.path;
      pane.dirty = dirty(pane);
      pane.tab.textContent = path ? (pane.dirty ? "● " : "") + path.split("/").at(-1) : pane.label;
      pane.tab.title = path || pane.label;
      pane.tab.setAttribute("aria-pressed", String(pane === active));
      pane.element.dataset.active = String(pane === active);
      pane.close.hidden = !path;
      pane.empty.hidden = Boolean(path);
      pane.layer.hidden = pane.file?.kind !== "text";
      pane.pdf.hidden = pane.file?.kind !== "pdf";
    }
    const path = active.file?.path;
    status.textContent = path ? active.label + " · " + path + (dirty(active) ? " · Chưa lưu" : "") : active.label;
    status.title = status.textContent;
    save.disabled = active.saving || !dirty(active);
    const extension = path?.split(".").at(-1).toLowerCase();
    const python = extension === "py";
    run.hidden = check.hidden = !python;
    runCode.hidden = !python && extension !== "js";
    format.hidden = !formatExtensions.has(extension);
    check.disabled = checking;
    format.disabled = formatting || active.saving;
    document.dispatchEvent(new CustomEvent("workspace:code-file", {
      detail: { path, revision: active.file?.revision, dirty: dirty(active) }
    }));
    if (persist) rememberLayout();
  }

  function activate(pane) {
    if (pane !== active) {
      active = pane;
      update();
    }
  }

  function syncScroll(pane) {
    pane.highlight.scrollTop = pane.editor.scrollTop;
    pane.highlight.scrollLeft = pane.editor.scrollLeft;
  }

  function highlight(pane) {
    const language = grammars[pane.file?.path.split(".").at(-1).toLowerCase()];
    const text = pane.editor.value;
    if (highlightFailed || !language || !text || text.length > 40000 || pane.composing) return;
    if (!highlighter) {
      try {
        highlighter = new Worker(workbenchHighlightUrl);
      } catch {
        highlightFailed = true;
        return;
      }
      highlighter.addEventListener("message", ({ data: { side, revision, html } }) => {
        const target = side === "left" ? left : right;
        if (target.highlightRevision !== revision || target.composing || !html) return;
        target.highlight.firstElementChild.innerHTML = html;
        target.layer.dataset.highlight = "true";
        syncScroll(target);
      });
      highlighter.addEventListener("error", () => {
        highlightFailed = true;
        highlighter.terminate();
        for (const target of panes) target.layer.dataset.highlight = "false";
      });
    }
    highlighter.postMessage({ side: pane.element.dataset.side, revision: pane.highlightRevision, language, text });
  }

  function invalidateHighlight(pane) {
    pane.highlightRevision += 1;
    pane.layer.dataset.highlight = "false";
    clearTimeout(pane.highlightTimer);
  }

  function scheduleHighlight(pane) {
    invalidateHighlight(pane);
    if (!pane.composing) pane.highlightTimer = setTimeout(() => highlight(pane), 150);
  }

  function clearImage(pane) {
    if (pane.url) URL.revokeObjectURL(pane.url);
    pane.url = null;
    pane.image.removeAttribute("src");
    pane.image.hidden = true;
  }

  function clear(pane) {
    pane.revision += 1;
    pane.pdfRequest?.abort();
    invalidateHighlight(pane);
    clearImage(pane);
    pane.file = null;
    pane.editor.value = "";
    pane.highlight.firstElementChild.replaceChildren();
  }

  async function renderPdf(pane, page) {
    const file = pane.file;
    pane.pdfRequest?.abort();
    const controller = new AbortController();
    pane.pdfRequest = controller;
    pane.previous.disabled = pane.next.disabled = true;
    pane.pdfStatus.textContent = "Đang đọc trang PDF…";
    try {
      const result = await api.call(api.query("/pdf", { path: file.path, page, zoom: pane.zoom.value }),
        "GET", undefined, false, controller.signal);
      if (controller.signal.aborted || pane.file !== file) return;
      clearImage(pane);
      pane.url = URL.createObjectURL(result.image);
      pane.image.alt = file.path + " · Trang " + page;
      pane.image.src = pane.url;
      pane.image.hidden = false;
      file.page = page;
      file.pages = result.pages;
      pane.pageLabel.textContent = page + " / " + result.pages;
      pane.pdfStatus.textContent = "";
      pane.image.parentElement.scrollTo(0, 0);
    } catch (error) {
      if (!controller.signal.aborted && pane.file === file) pane.pdfStatus.textContent = error.message;
    } finally {
      if (!controller.signal.aborted && pane.file === file) {
        pane.previous.disabled = file.page <= 1;
        pane.next.disabled = file.page >= file.pages;
      }
    }
  }

  async function open(path, target = active) {
    const existing = panes.find((pane) => pane.file?.path === path);
    const pane = existing || target;
    const revision = ++pane.revision;
    if (!existing) {
      if (pane.saving) return onStatus("Đợi lưu tệp xong rồi thử lại.");
      const isPdf = /\.pdf$/i.test(path);
      const source = isPdf ? null : await api.call(api.query("/file", { path }));
      if (revision !== pane.revision || panes.some((other) => other !== pane && other.file?.path === path)) return;
      if (!canDiscard([pane])) return;
      clear(pane);
      if (isPdf) {
        pane.file = { path, kind: "pdf", page: 1, pages: 1 };
        pane.pageLabel.textContent = "—";
        pane.zoom.value = "100";
        renderPdf(pane, 1);
      } else {
        pane.file = { path, kind: "text", revision: source.revision, original: source.text.replace(/\r\n/g, "\n") };
        pane.editor.value = pane.file.original;
        pane.editor.scrollTo(0, 0);
        highlight(pane);
      }
    }
    activate(pane);
    update();
    return pane;
  }

  function focus(pane, target) {
    if (pane.file.kind === "pdf") return pane.tab.focus();
    const editor = pane.editor;
    editor.focus();
    if (!target?.line) return;
    const lines = editor.value.split("\n");
    if (target.line > lines.length) return onStatus("Tệp hiện tại không còn dòng " + target.line + ".");
    const before = lines.slice(0, target.line - 1).reduce((length, line) => length + line.length + 1, 0);
    const length = lines[target.line - 1].length;
    const offset = target.column ? Math.min(length, target.column - 1) : 0;
    editor.setSelectionRange(before + offset, target.column ? before + offset : before + length);
    editor.scrollTop = Math.max(0, (target.line - 1) * parseFloat(getComputedStyle(editor).lineHeight) - editor.clientHeight / 3);
    syncScroll(pane);
    status.textContent = pane.file.path + " · dòng " + target.line + (dirty(pane) ? " · Chưa lưu" : "");
  }

  async function saveFile(pane) {
    if (pane.saving || !dirty(pane)) return;
    const file = pane.file;
    const text = pane.editor.value;
    pane.saving = true;
    update();
    try {
      const result = await api.call("/file", "PUT", { path: file.path, revision: file.revision, text });
      if (pane.file === file) Object.assign(file, { original: text, revision: result.revision });
      onStatus("Đã lưu " + file.path + ".");
    } catch (error) { onStatus(error.message); }
    finally {
      pane.saving = false;
      update();
    }
  }

  for (const pane of panes) {
    pane.element.addEventListener("pointerdown", () => activate(pane));
    pane.element.addEventListener("focusin", () => activate(pane));
    pane.close.addEventListener("click", () => {
      if (canDiscard([pane])) {
        clear(pane);
        update();
        pane.tab.focus();
      }
    });
    pane.editor.addEventListener("scroll", () => syncScroll(pane));
    pane.editor.addEventListener("compositionstart", () => {
      pane.composing = true;
      invalidateHighlight(pane);
    });
    pane.editor.addEventListener("compositionend", () => {
      pane.composing = false;
      scheduleHighlight(pane);
    });
    pane.editor.addEventListener("input", () => {
      const changed = dirty(pane);
      if (pane.dirty !== changed) {
        pane.dirty = changed;
        update(false);
      }
      scheduleHighlight(pane);
    });
    pane.previous.addEventListener("click", () => renderPdf(pane, pane.file.page - 1));
    pane.next.addEventListener("click", () => renderPdf(pane, pane.file.page + 1));
    pane.zoom.addEventListener("change", () => renderPdf(pane, pane.file.page));
  }

  let ratio = 50;
  function rememberLayout() {
    if (restoring) return;
    onLayout({ left: left.file?.path || "", right: right.file?.path || "", split: !right.element.hidden,
      active: active.element.dataset.side, ratio });
  }

  function setSplit(show) {
    right.element.hidden = divider.hidden = !show;
    group.dataset.split = String(show);
    split.setAttribute("aria-pressed", String(show));
    split.textContent = show ? "Một ô" : "Chia đôi";
  }

  async function restore(layout) {
    restoring = true;
    try {
      panes.forEach(clear);
      setRatio(layout?.ratio ?? 50);
      setSplit(Boolean(layout?.split));
      for (const pane of panes) {
        const path = layout?.[pane.element.dataset.side];
        if (path && !pane.element.hidden) {
          try { await open(path, pane); }
          catch { /* A renamed or removed file can be reopened from the current tree. */ }
        }
      }
      active = layout?.split && layout.active === "right" ? right : left;
      update();
    } finally { restoring = false; }
  }
  function setRatio(value) {
    ratio = Math.max(25, Math.min(75, Math.round(value)));
    group.style.setProperty("--code-split", ratio + "%");
    divider.setAttribute("aria-valuenow", ratio);
  }
  divider.addEventListener("pointerdown", (event) => divider.setPointerCapture(event.pointerId));
  divider.addEventListener("pointermove", (event) => {
    if (!divider.hasPointerCapture(event.pointerId)) return;
    const bounds = group.getBoundingClientRect();
    setRatio((event.clientX - bounds.left) * 100 / bounds.width);
  });
  divider.addEventListener("pointerup", rememberLayout);
  divider.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    setRatio(ratio + (event.key === "ArrowLeft" ? -5 : 5));
    rememberLayout();
  });
  split.addEventListener("click", () => {
    const show = right.element.hidden;
    if (!show && !canDiscard([right])) return;
    if (!show) clear(right);
    setSplit(show);
    activate(show ? right : left);
    update();
    (show ? right.tab : split).focus();
  });
  save.addEventListener("click", () => saveFile(active));

  check.addEventListener("click", async () => {
    const pane = active;
    const file = pane.file;
    if (!file || checking) return;
    if (dirty(pane) || pane.saving) return onStatus("Lưu tệp trước khi kiểm tra Python.");
    const root = state.codeRoot;
    const { path, revision } = file;
    const scope = { path, root, revision };
    checking = true;
    update(false);
    window.WorkbenchDock.updateCodeProblems(scope, { status: "Đang chạy Ruff và Pyright…" });
    window.WorkbenchDock.show("problems");
    const sameSnapshot = () => state.codeRoot === root && pane.file === file && file.revision === revision && !dirty(pane);
    try {
      const result = await api.call("/code/check", "POST", { path, revision });
      if (sameSnapshot()) window.WorkbenchDock.updateCodeProblems(scope, result);
    } catch (error) {
      if (sameSnapshot()) window.WorkbenchDock.updateCodeProblems(scope, { status: error.message });
    } finally {
      checking = false;
      update(false);
    }
  });

  format.addEventListener("click", async () => {
    const pane = active;
    const file = pane.file;
    if (!file || formatting || pane.saving || pane.composing) return;
    const root = state.codeRoot;
    const text = pane.editor.value;
    const { path, revision } = file;
    formatting = true;
    update(false);
    try {
      const result = await api.call("/code/format", "POST", { path, revision, text });
      if (state.codeRoot !== root || pane.file !== file || file.revision !== revision ||
          pane.editor.value !== text || pane.composing) return;
      if (result.text === text) return onStatus("Tệp đã đúng định dạng của " + result.tool + ".");
      pane.editor.setRangeText(result.text, 0, text.length, "preserve");
      scheduleHighlight(pane);
      onStatus("Đã định dạng bằng " + result.tool + ". Lưu để ghi thay đổi xuống tệp.");
    } catch (error) { onStatus(error.message); }
    finally {
      formatting = false;
      update(false);
    }
  });

  runCode.addEventListener("click", () => {
    const file = active.file;
    if (!file || dirty(active) || active.saving) return onStatus("Lưu tệp trước khi chạy.");
    const { path, revision } = file;
    document.dispatchEvent(new CustomEvent("workspace:run-file", {
      detail: { shell: "Run File", workspace: "code", path, revision }
    }));
  });
  window.addEventListener("keydown", (event) => {
    if ($("editor").hidden || event.defaultPrevented || event.target.closest?.("#terminal-dock") ||
        event.altKey || event.shiftKey || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "s") return;
    event.preventDefault();
    saveFile(active);
  });
  window.addEventListener("beforeunload", (event) => {
    if (!panes.some(dirty)) return;
    event.preventDefault();
    event.returnValue = "";
  });
  restoring = true;
  update();
  restoring = false;
  return { open, focus, canDiscard, restore,
    hasOpen: (path) => panes.some(({ file }) => file && (file.path === path || file.path.startsWith(path + "/"))),
    file: () => active.file, dirty: () => dirty(active) };
};
