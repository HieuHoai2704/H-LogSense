"use strict";

(() => {
  const params = new URLSearchParams(location.hash.slice(1));
  const supplied = params.get("workbench");
  let token = supplied;
  try {
    if (supplied) sessionStorage.setItem("h-logsen-workbench", supplied);
    else token = sessionStorage.getItem("h-logsen-workbench");
  } catch {
    // A token in the launcher URL still works for this document.
  }
  if (supplied) history.replaceState(history.state, "", location.pathname + location.search);

  // Resolved at call time; logs.html loads this file without i18n.js, so keep the English key there.
  const tr = (message) => window.logsenseTranslate ? window.logsenseTranslate(message) : message;

  function query(path, values) {
    const search = new URLSearchParams(Object.entries(values).filter(([, value]) => value !== null && value !== undefined));
    return search.size ? path + "?" + search : path;
  }

  async function call(workspace, project, path, method = "GET", data, keepalive = false, signal) {
    if (!token) throw new Error(tr("Open H-logsen from its launcher or start command to grant access."));
    const headers = { Authorization: "Bearer " + token, "X-Workspace": workspace };
    if (project) headers["X-Project"] = project;
    if (data !== undefined) headers["Content-Type"] = "application/json";
    const response = await fetch("/api/local/v1" + path, {
      method, headers, keepalive, signal, redirect: "error", cache: "no-store",
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    if (response.status === 204) return;
    if (response.ok) {
      if (response.headers.get("Content-Type") === "image/png") {
        return { image: await response.blob(), pages: Number(response.headers.get("X-PDF-Pages")) };
      }
      return response.json();
    }
    const result = await response.json().catch(() => null);
    const error = new Error(typeof result?.error === "string" ? result.error : tr("Request failed."));
    error.status = response.status;
    throw error;
  }

  const scopes = new Map();
  function scope(workspace) {
    if (scopes.has(workspace)) return scopes.get(workspace);
    let project = null;
    const client = {
      call: (...args) => call(workspace, project, ...args),
      setProject: (value) => { project = value; },
      query,
      authorized: Boolean(token),
    };
    scopes.set(workspace, client);
    return client;
  }
  window.localWorkbench = { ...scope("project"), scope };
})();

window.createWorkbenchViewState = (api) => {
  let data = {};
  let pending = {};
  let timer;
  let write = Promise.resolve();
  let revision = 0;

  function flush() {
    clearTimeout(timer);
    if (!Object.keys(pending).length) return write;
    const sent = pending;
    pending = {};
    const observed = revision;
    write = write.then(async () => {
      if (observed !== revision) return;
      try {
        const size = new TextEncoder().encode(JSON.stringify(sent)).length;
        await api.call("/view-state", "PUT", sent, size < 48 * 1024);
      } catch {
        if (observed === revision) pending = { ...sent, ...pending };
      }
    });
    return write;
  }

  window.addEventListener("pagehide", () => { flush(); });
  return {
    get data() { return data; },
    async load(root) {
      const observed = ++revision;
      clearTimeout(timer);
      pending = {};
      data = {};
      if (!root) return;
      try {
        const saved = await api.call("/view-state");
        if (observed === revision) data = { ...saved, ...data };
      } catch { /* A new tree can still open if preferences are unavailable. */ }
    },
    patch(changes) {
      const updated = Object.fromEntries(Object.entries(changes).filter(([key, value]) =>
        JSON.stringify(value) !== JSON.stringify(data[key])));
      if (!Object.keys(updated).length) return;
      Object.assign(data, updated);
      Object.assign(pending, updated);
      clearTimeout(timer);
      timer = setTimeout(flush, 120);
    },
    flush,
  };
};
