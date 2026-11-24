"use strict";

const workspaceAppearance = (() => {
  const labels = new Map([
    ["graphite", "Graphite"], ["paper", "Paper"], ["mono", "Monochrome"],
    ["warm", "Warm gray"], ["glass", "Black glass"],
    ["glass-forest", "Forest green glass"], ["glass-mint", "Light green glass"],
    ["glass-blue", "Blue glass"]
  ]);
  const key = "h-logsen-ui-palette";
  const transparencyKey = "h-logsen-glass-transparency";
  const transparencyCookie = "h_logsen_glass_transparency";
  const root = document.documentElement;
  let transparency = null;

  function applyTransparency(value) {
    transparency = Number.isInteger(value) && value >= 0 && value <= 100 ? value : null;
    if (transparency === null) root.style.removeProperty("--glass-opacity-override");
    else root.style.setProperty("--glass-opacity-override", (100 - transparency) + "%");
  }

  function apply(theme) {
    root.dataset.theme = labels.has(theme) ? theme : "graphite";
  }

  function load() {
    try {
      const cookie = document.cookie.match(/(?:^|;\s*)h_logsen_theme=([\w-]+)/)?.[1];
      const theme = cookie || localStorage.getItem(key);
      if (theme) apply(theme);
      const savedTransparency = document.cookie.match(/(?:^|;\s*)h_logsen_glass_transparency=(\d+)/)?.[1]
        ?? localStorage.getItem(transparencyKey);
      applyTransparency(savedTransparency === null ? null : Number(savedTransparency));
    } catch {
      // The workspace still works when storage is unavailable.
    }
  }

  load();
  window.addEventListener("pageshow", load);

  return {
    labels,
    transparency() {
      return transparency ?? 100 - parseFloat(getComputedStyle(root).getPropertyValue("--glass-opacity"));
    },
    setTransparency(value, persist = false) {
      applyTransparency(value);
      if (!persist) return;
      try {
        document.cookie = transparencyCookie + "=" + (transparency ?? "") +
          "; path=/; max-age=" + (transparency === null ? 0 : 31536000) + "; SameSite=Lax";
        if (transparency === null) localStorage.removeItem(transparencyKey);
        else localStorage.setItem(transparencyKey, String(transparency));
      } catch {
        // Keep the current adjustment when storage is unavailable.
      }
    },
    set(theme) {
      apply(theme);
      document.dispatchEvent(new CustomEvent("workspace:theme", { detail: root.dataset.theme }));
      try {
        document.cookie = "h_logsen_theme=" + root.dataset.theme + "; path=/; max-age=31536000; SameSite=Lax";
        localStorage.setItem(key, root.dataset.theme);
        return true;
      } catch {
        return false;
      }
    }
  };
})();

(() => {
  const root = document.documentElement;
  if (!root.hasAttribute("data-workspace-home")) return;

  const fromLauncher = new URLSearchParams(location.hash.slice(1)).get("workbench");
  try {
    if (!fromLauncher && sessionStorage.getItem("h-logsen-home-visited")) return;
    sessionStorage.setItem("h-logsen-home-visited", "1");
  } catch {
    if (!fromLauncher) return;
  }

  if (!matchMedia("(prefers-reduced-motion: no-preference)").matches) return;

  root.setAttribute("data-workspace-launch", "");
  const events = new AbortController();
  const dismiss = () => {
    root.removeAttribute("data-workspace-launch");
    events.abort();
  };
  const options = { capture: true, signal: events.signal };
  for (const event of ["pointerdown", "keydown", "focusin", "pagehide"]) {
    window.addEventListener(event, dismiss, options);
  }
  const finish = (event) => {
    if (event.target.id === "workspace-launch") dismiss();
  };
  window.addEventListener("animationend", finish, options);
  window.addEventListener("animationcancel", finish, options);
})();
