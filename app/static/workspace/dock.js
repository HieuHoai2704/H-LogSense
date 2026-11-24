"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const dock = $("terminal-dock");
  const tabs = [...dock.querySelectorAll("[data-dock-tab]")];
  const mount = $("terminal-panes");
  const portsOpen = () => !mount.hidden && mount.contains($("dock-ports"));
  const api = window.localWorkbench;
  const codeApi = api.scope("code");
  const inCode = () => !$("editor").hidden;
  let code = {};
  let codeProblems = null;
  let logProblems = 0;
  let debuggerSession = null;
  let portRequest = 0;

  document.addEventListener("workspace:dock-tool", ({ detail }) => {
    for (const button of tabs) button.setAttribute("aria-pressed", String(detail === button.dataset.dockTab));
  });

  async function refreshPorts() {
    const observed = ++portRequest;
    const status = $("dock-ports-status");
    $("dock-port-rows").replaceChildren();
    const root = inCode() ? state.codeRoot : state.localRoot;
    status.textContent = root ? "Đang đọc các cổng TCP…" : "Mở thư mục để xem các cổng trên máy.";
    if (!root) return;
    try {
      const result = await (inCode() ? codeApi : api).call("/ports");
      if (observed !== portRequest) return;
      const rows = result.ports.map(({ address, port, pid, status }) => {
        const row = document.createElement("tr");
        for (const value of [address, port, pid ?? "—", status === "listening" ? "Lắng nghe" : "Chưa rõ"]) {
          row.insertCell().textContent = value;
        }
        return row;
      });
      $("dock-port-rows").replaceChildren(...rows);
      status.textContent = rows.length + (result.truncated ? "+ cổng" : " cổng");
    } catch (error) {
      if (observed === portRequest) status.textContent = error.message;
    }
  }

  function show(panel) {
    if (window.WorkbenchTerminalPanes.showTool(panel) && panel === "ports") refreshPorts();
  }

  for (const button of tabs) button.addEventListener("click", () => show(button.dataset.dockTab));
  function refreshVisiblePorts() {
    if (portsOpen()) refreshPorts();
  }
  document.addEventListener("workbench:view", () => {
    refreshVisiblePorts();
    syncCodeProblems();
  });
  dock.querySelector('[data-terminal-action="collapse"]').addEventListener("click", refreshVisiblePorts);
  $("dock-ports-refresh").addEventListener("click", refreshPorts);

  function updateLog(text, entries, root) {
    $("dock-output-text").textContent = text || "Chờ đầu ra của tệp log hoặc lượt chạy.";
    const problems = $("dock-problem-rows");
    const source = window.WorkbenchSourceLinks;
    const found = [];
    const visited = new Set();
    for (const entry of entries) {
      const reference = source.reference(entry.raw, root);
      const key = reference && reference.path + ":" + reference.line + ":" + reference.column;
      if (key && visited.has(key)) continue;
      if (!reference && !isSignal(entry) && !/^\w*(Error|Exception):/.test(entry.raw)) continue;
      if (key) visited.add(key);
      found.push({ entry, reference });
    }
    problems.replaceChildren(...found.slice(-100).reverse().map(({ entry, reference }) => {
      const item = document.createElement("li");
      item.textContent = entry.raw;
      if (reference) item.append(" ", source.button(reference));
      return item;
    }));
    logProblems = found.length;
    syncProblemCount();
    $("dock-problems-status").textContent = !entries.length ? "Chờ nguồn log." :
      found.length > 100 ? "100 mục gần nhất trong " + found.length + " mục từ log." :
      found.length ? found.length + " mục từ log." : "Chưa ghi nhận cảnh báo, lỗi hoặc traceback.";
  }

  function activeCodeProblems() {
    return inCode() && !code.dirty && codeProblems && codeProblems.scope.root === state.codeRoot &&
      codeProblems.scope.path === code.path && codeProblems.scope.revision === code.revision
      ? codeProblems.result : null;
  }

  function syncProblemCount() {
    const count = logProblems + (activeCodeProblems()?.total ?? 0);
    $("dock-problem-count").textContent = count ? "· " + count : "";
  }

  function syncCodeProblems() {
    const section = $("dock-code-problems");
    section.hidden = !inCode() || !code.path?.toLowerCase().endsWith(".py");
    const result = activeCodeProblems();
    const status = $("dock-code-problems-status");
    const issues = $("dock-code-problem-rows");
    issues.replaceChildren();
    if (result?.issues) {
      const parts = [];
      if (result.completed.length) {
        const count = result.total > result.issues.length ? result.issues.length + "/" + result.total : result.total;
        parts.push(result.completed.join(" + ") + " · " + count + " mục");
      }
      parts.push(...Object.values(result.unavailable));
      status.textContent = parts.join(" · ");
      for (const issue of result.issues) {
        const row = document.createElement("li");
        const rule = issue.rule ? " " + issue.rule : "";
        row.textContent = issue.tool + rule + " · " + issue.severity + " · " + issue.message + " ";
        row.append(window.WorkbenchSourceLinks.button({ path: code.path, root: state.codeRoot,
          line: issue.line, column: issue.column }));
        issues.append(row);
      }
    } else {
      status.textContent = result?.status || (code.dirty ? "Lưu tệp rồi kiểm tra lại." : "Bấm Kiểm tra Python để chạy Ruff và Pyright.");
    }
    syncProblemCount();
  }

  const debugStart = $("dock-debug-start");
  const debugStop = $("dock-debug-stop");
  const debugStatus = $("dock-debug-status");
  const debugHost = $("dock-debug-shell");
  function syncDebug() {
    const ready = state.codeRoot && code.path?.toLowerCase().endsWith(".py");
    debugStart.disabled = !ready || code.dirty || Boolean(debuggerSession);
    debugStop.hidden = debugHost.hidden = !debuggerSession;
    if (debuggerSession) return;
    debugStatus.textContent = !ready ? "Mở một tệp Python trong Code." :
      code.dirty ? "Lưu " + code.path + " trước khi gỡ lỗi." : code.path + " · Python pdb";
  }
  function stopDebug() {
    debuggerSession?.close();
    debuggerSession = null;
    syncDebug();
  }
  debugStart.addEventListener("click", () => {
    if (debugStart.disabled) return;
    debugStatus.textContent = code.path + " · n: bước tiếp · s: vào hàm · c: chạy tiếp · q: thoát";
    debuggerSession = new window.WorkbenchTerminal(debugHost, { shell: "Python Debug", path: code.path, workspace: "code" },
      (message) => { debugStatus.textContent = message; });
    syncDebug();
    debuggerSession.begin();
  });
  debugStop.addEventListener("click", stopDebug);
  document.addEventListener("workspace:code-file", ({ detail }) => {
    code = detail;
    syncDebug();
    syncCodeProblems();
  });
  document.addEventListener("workspace:theme", () => debuggerSession?.refreshTheme());
  window.addEventListener("pagehide", (event) => { if (!event.persisted) stopDebug(); });
  window.WorkbenchDock = { updateLog, show, updateCodeProblems(scope, result) {
    codeProblems = { scope, result };
    syncCodeProblems();
  }, rootChanged(scope) {
    portRequest += 1;
    $("dock-port-rows").replaceChildren();
    $("dock-ports-status").textContent = "";
    if (scope === "code") {
      codeProblems = null;
      stopDebug();
      syncCodeProblems();
    }
    if (portsOpen()) refreshPorts();
  } };
})();
