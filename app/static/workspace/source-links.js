"use strict";

(() => {
  function reference(raw, root) {
    if (!root) return null;
    const line = raw.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").trim();
    const python = line.match(/\bFile ["']([^"']+)["'], line (\d+)\b/);
    const stack = line.match(/^at\s+.*?\((.+)\)$/)?.[1] ?? line.replace(/^at\s+/, "");
    const located = stack.match(/^(.+?\.(?:py|[cm]?[jt]sx?|sql|sh|ps1)):(\d+)(?::(\d+))?(?=\s|:|$)/i);
    const failed = line.match(/^FAILED\s+(.+?\.py)::/);
    const match = python || located || failed;
    if (!match) return null;
    let path = match[1].replaceAll("\\", "/");
    const absolute = /^(?:[A-Za-z]:|\/)/.test(path);
    if (absolute) {
      const base = root.replaceAll("\\", "/").replace(/\/+$/, "") + "/";
      const windows = /^[A-Za-z]:/.test(base);
      if (!(windows ? path.toLowerCase().startsWith(base.toLowerCase()) : path.startsWith(base))) return null;
      path = path.slice(base.length);
    }
    path = path.replace(/^\.\//, "");
    if (!path || path.split("/").some((part) => !part || part.startsWith(".") || /[:<>"|?*\x00-\x1f]/.test(part))) return null;
    const lineNumber = match[2] ? Number(match[2]) : null;
    const column = located === match && match[3] ? Number(match[3]) : null;
    if (lineNumber !== null && (!Number.isSafeInteger(lineNumber) || lineNumber < 1)) return null;
    if (column !== null && (!Number.isSafeInteger(column) || column < 1)) return null;
    return { path, line: lineNumber, column, root, absolute };
  }

  function open(target) {
    document.dispatchEvent(new CustomEvent("workbench:open-source", { detail: target }));
  }

  function button(target) {
    const link = document.createElement("button");
    link.type = "button";
    link.className = "source-jump";
    link.textContent = target.line
      ? window.logsenseTranslate("Open {0}:{1}", target.path, target.line)
      : window.logsenseTranslate("Open {0} · line unknown", target.path);
    link.addEventListener("click", () => open(target));
    return link;
  }

  window.WorkbenchSourceLinks = { reference, open, button };
})();
