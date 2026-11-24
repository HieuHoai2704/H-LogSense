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

  const root = document.documentElement;
  if (token && root.hasAttribute("data-workbench-desktop")) {
    const reduced = matchMedia("(prefers-reduced-transparency: reduce), (forced-colors: active)");
    let latest;
    let update = Promise.resolve();
    function syncWindowGlass() {
      const api = window.pywebview?.api;
      const enabled = root.matches('[data-theme|="glass"]') && !reduced.matches;
      if (!api?.set_window_glass || enabled === latest) return;
      latest = enabled;
      update = update.then(() => api.set_window_glass(token, enabled)).then((applied) => {
        if (latest === enabled) root.toggleAttribute("data-native-glass", enabled && applied === true);
      }).catch(() => {
        if (latest === enabled) {
          root.removeAttribute("data-native-glass");
          latest = undefined;
        }
      });
    }
    // Native title bar colours follow the palette (used by Linux/GTK; other platforms ignore it).
    let latestChrome = "";
    function hexColor(value) {
      const probe = document.createElement("span");
      probe.style.color = value;
      document.body.append(probe);
      const rgb = getComputedStyle(probe).color.match(/\d+(\.\d+)?/g)?.slice(0, 3).map(Number);
      probe.remove();
      return rgb ? { hex: "#" + rgb.map((part) => Math.round(part).toString(16).padStart(2, "0")).join(""), rgb } : null;
    }
    function syncWindowTheme() {
      const api = window.pywebview?.api;
      const host = document.querySelector(".workspace-nav") || document.body;
      if (!api?.set_window_theme || !host) return;
      const style = getComputedStyle(host);
      const background = hexColor(style.getPropertyValue("--panel").trim() || style.backgroundColor);
      const foreground = hexColor(style.getPropertyValue("--text").trim() || style.color);
      if (!background || !foreground) return;
      const [r, g, b] = background.rgb;
      const dark = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.5;
      const key = [dark, background.hex, foreground.hex].join();
      if (key === latestChrome) return;
      latestChrome = key;
      api.set_window_theme(token, dark, background.hex, foreground.hex).catch(() => { latestChrome = ""; });
    }
    function syncWindowChrome() {
      syncWindowGlass();
      syncWindowTheme();
    }
    window.addEventListener("pywebviewready", syncWindowChrome);
    window.addEventListener("pageshow", syncWindowChrome);
    document.addEventListener("workspace:theme", syncWindowChrome);
    reduced.addEventListener("change", syncWindowGlass);
    syncWindowChrome();
  }

  // Resolved at call time; logs.html loads this file without i18n.js, so keep the English key there.
  const tr = (message) => window.logsenseTranslate ? window.logsenseTranslate(message) : message;

  function query(path, values) {
    const search = new URLSearchParams(Object.entries(values).filter(([, value]) => value !== null && value !== undefined));
    return search.size ? path + "?" + search : path;
  }

  async function call(workspace, project, path, method = "GET", data, keepalive = false, signal) {
    if (!token) throw new Error(tr("Open the app from the desktop launcher to grant access."));
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

  async function pickProject(workspace) {
    if (!token || !window.pywebview?.api?.pick_project) throw new Error(tr("The dialog is still starting. Try again shortly."));
    return window.pywebview.api.pick_project(token, workspace);
  }

  const scopes = new Map();
  function scope(workspace) {
    if (scopes.has(workspace)) return scopes.get(workspace);
    let project = null;
    const client = {
      call: (...args) => call(workspace, project, ...args),
      setProject: (value) => { project = value; },
      pickProject: () => pickProject(workspace),
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
