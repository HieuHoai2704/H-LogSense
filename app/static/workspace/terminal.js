"use strict";

(() => {
  const tr = window.logsenseTranslate;
  const appName = document.title;
  const dock = document.getElementById("terminal-dock");
  const mount = document.getElementById("terminal-panes");
  const notice = document.getElementById("terminal-status");
  const sessionSelect = document.getElementById("terminal-sessions");
  const log = document.getElementById("terminal-log-content");
  const pool = document.getElementById("terminal-log-pool");
  const toolPool = document.getElementById("terminal-tool-pool");
  const tools = toolPool ? [...toolPool.children] : [];
  const sessions = new Map();
  const empty = textNode("div", "", "terminal-empty");
  empty.append(textNode("p", tr("No sessions yet. Click + New session to open a new pane."), "terminal-placeholder"));
  const emptyView = { element: empty, tool: null };
  let nextId = 1;
  let active;
  let maximized = null;

  function textNode(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }

  function control(label, action, className) {
    const button = textNode("button", label, className);
    button.type = "button";
    button.addEventListener("click", action);
    return button;
  }

  function status(message = "") {
    notice.textContent = message;
    notice.hidden = !message;
  }

  const examples = {
    shell: ["Shell", tr("Sample session"), tr("Layout preview pane. Not connected to a shell on this machine.")],
    log: [tr("Monitored log"), tr("Log · Read-only"), ""]
  };

  function selectPane(id) {
    if (active === id) return;
    active = id;
    refreshSelection();
    status();
  }

  function newPane(kind, profile) {
    const id = nextId++;
    const [name, metadata, sample] = profile
      ? [profile.shell === "Run File" ? profile.path.split("/").at(-1) : profile.shell, profile.host || tr("Local"), ""]
      : examples[kind];
    const element = document.createElement("section");
    element.className = "terminal-pane";
    element.dataset.pane = id;
    const header = document.createElement("header");
    const select = control(String(id).padStart(2, "0") + " · " + name, () => {
      selectPane(id);
      focusPane(sessions.get(id));
    }, "pane-select");
    const zoom = control(tr("Maximize"), () => {
      active = id;
      maximized = maximized === id ? null : id;
      render();
      zoom.focus();
    });
    zoom.setAttribute("aria-label", tr("Maximize") + " " + name);
    const close = control(tr("Close"), () => closePane(id));
    close.dataset.paneClose = "";
    close.setAttribute("aria-label", tr("Close") + " " + name);
    header.append(select, textNode("small", metadata), close, zoom);
    element.append(header);
    let live;
    if (kind === "log") element.append(log);
    else if (profile) {
      const host = textNode("div", tr("Opening session…"), "live-shell");
      element.append(host);
      live = new window.WorkbenchTerminal(host, profile, status);
    } else {
      const transcript = textNode("pre", sample, "terminal-transcript");
      transcript.tabIndex = 0;
      element.append(transcript);
    }
    element.addEventListener("pointerdown", () => selectPane(id));
    element.addEventListener("focusin", () => selectPane(id));
    const session = { id, kind, element, select, zoom, name, live, popup: null, tool: null };
    sessions.set(id, session);
    return { id };
  }

  const split = (direction, first, second, ratio = 0.5) => ({ direction, first, second, ratio });
  let tree = window.localWorkbench?.authorized ? null : newPane("log");
  active = tree?.id;

  function replaceLeaf(node, id, replacement) {
    if (!node || !node.direction) return node?.id === id ? replacement : node;
    const first = replaceLeaf(node.first, id, replacement);
    const second = replaceLeaf(node.second, id, replacement);
    if (!first || !second) return first || second;
    return split(node.direction, first, second, node.ratio);
  }

  function refreshSelection() {
    sessionSelect.replaceChildren(...[...sessions.values()].map((session) =>
      new Option(String(session.id).padStart(2, "0") + " · " + session.name + (session.popup ? " · " + tr("Separate window") : ""), session.id)));
    sessionSelect.disabled = !sessions.size;
    sessionSelect.value = active ?? "";
    for (const session of sessions.values()) {
      const selected = session.id === active;
      session.element.dataset.active = String(selected);
      session.select.setAttribute("aria-pressed", String(selected));
      session.zoom.textContent = session.id === maximized ? tr("Restore") : tr("Maximize");
      session.zoom.setAttribute("aria-label", session.zoom.textContent + " " + session.name);
      session.zoom.hidden = Boolean(session.popup);
    }
    reportTool();
  }

  function reportTool() {
    const view = sessions.get(active) ?? emptyView;
    document.dispatchEvent(new CustomEvent("workspace:dock-tool", { detail: view.tool ?? "terminal" }));
  }

  function syncTools() {
    const owners = new Map();
    for (const view of [emptyView, ...sessions.values()]) {
      const visible = view.tool && mount.contains(view.element);
      if (visible) {
        view.element.dataset.tool = view.tool;
        owners.set("dock-" + view.tool, view.element);
      } else delete view.element.dataset.tool;
    }
    for (const tool of tools) {
      const target = owners.get(tool.id) ?? toolPool;
      if (tool.parentElement !== target) target.append(tool);
    }
  }

  function showTool(name) {
    const view = sessions.get(active) ?? emptyView;
    if (view.popup && name !== "terminal") {
      status(tr("Reattach the terminal window to open tools in this pane."));
      return false;
    }
    if (name !== "terminal") {
      // Each workspace tool has a single shared view and can move between panes.
      for (const owner of [emptyView, ...sessions.values()]) {
        if (owner.tool === name) owner.tool = null;
      }
    }
    view.tool = name === "terminal" ? null : name;
    mount.hidden = false;
    updateCollapse();
    syncTools();
    reportTool();
    if (!view.tool && view !== emptyView) focusPane(view);
    return true;
  }

  function focusPane(session) {
    if (!session) return;
    if (session.popup) session.popup.focus();
    if (!session.tool && session.live?.emulator && !session.live.emulator.options.disableStdin) session.live.emulator.focus();
    else session.select.focus({ preventScroll: true });
  }

  function build(node) {
    if (!node.direction) {
      const session = sessions.get(node.id);
      if (!session.popup) return session.element;
      const placeholder = document.createElement("div");
      placeholder.className = "terminal-placeholder";
      placeholder.append(textNode("p", session.name + " · " + tr("Separate window")),
        control(tr("Reattach"), () => attach(session)));
      return placeholder;
    }
    const group = document.createElement("div");
    group.className = "terminal-split";
    group.dataset.direction = node.direction;
    const divider = document.createElement("div");
    const across = node.direction === "right";
    divider.className = "terminal-divider";
    divider.setAttribute("role", "separator");
    divider.setAttribute("aria-orientation", across ? "vertical" : "horizontal");
    divider.setAttribute("aria-label", tr("Resize the two terminal panes"));
    divider.setAttribute("aria-valuemin", "20");
    divider.setAttribute("aria-valuemax", "80");
    divider.tabIndex = 0;
    function setRatio(value) {
      node.ratio = Math.min(.8, Math.max(.2, value));
      group.style.setProperty("--first", node.ratio + "fr");
      group.style.setProperty("--second", 1 - node.ratio + "fr");
      divider.setAttribute("aria-valuenow", Math.round(node.ratio * 100));
    }
    setRatio(node.ratio);
    divider.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      divider.setPointerCapture(event.pointerId);
    });
    divider.addEventListener("pointermove", (event) => {
      if (!divider.hasPointerCapture(event.pointerId)) return;
      const bounds = group.getBoundingClientRect();
      setRatio(across ? (event.clientX - bounds.left) / bounds.width : (event.clientY - bounds.top) / bounds.height);
    });
    divider.addEventListener("keydown", (event) => {
      const keys = across ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
      if (!keys.includes(event.key)) return;
      event.preventDefault();
      setRatio(node.ratio + (event.key === keys[0] ? -.05 : .05));
    });
    group.append(build(node.first), divider, build(node.second));
    return group;
  }

  function render() {
    const visible = maximized ? { id: maximized } : tree;
    mount.replaceChildren(visible ? build(visible) : empty);
    syncTools();
    refreshSelection();
  }

  function addPane(kind, direction, profile, keepFocus = false) {
    if (sessions.size >= 6) {
      status(tr("Terminal supports up to 6 panes at once."));
      return;
    }
    emptyView.tool = null;
    const pane = newPane(kind, profile);
    tree = tree ? replaceLeaf(tree, active, split(direction, { id: active }, pane)) : pane;
    active = pane.id;
    maximized = null;
    mount.hidden = false;
    updateCollapse();
    render();
    const session = sessions.get(active);
    if (!keepFocus) focusPane(session);
    session.live?.begin();
  }

  function attach(session, closeWindow = true) {
    const popup = session.popup;
    if (!popup) return;
    session.popup = null;
    active = session.id;
    render();
    session.live?.attach();
    if (closeWindow && !popup.closed) popup.close();
    status();
  }

  function closePane(id) {
    const session = sessions.get(id);
    const popup = session.popup;
    session.popup = null;
    session.live?.close();
    if (session.kind === "log") pool.append(log);
    sessions.delete(id);
    tree = replaceLeaf(tree, id, null);
    if (maximized === id) maximized = null;
    if (active === id) active = [...sessions.values()].find((item) => item.live)?.id ?? sessions.keys().next().value;
    render();
    if (popup && !popup.closed) popup.close();
    if (sessions.has(active)) focusPane(sessions.get(active));
    else dock.querySelector('[data-terminal-action="new"]').focus();
  }

  function detach() {
    const session = sessions.get(active);
    if (!session) return status(tr("Open a session before detaching a window."));
    if (session.popup && !session.popup.closed) {
      session.popup.focus();
      return;
    }
    const popup = window.open("about:blank", "_blank", "popup,width=780,height=510");
    if (!popup) return status(tr("The browser is blocking new windows."));
    session.popup = popup;
    session.tool = null;
    if (maximized === active) maximized = null;
    const page = popup.document;
    page.title = appName + " · " + session.name;
    page.documentElement.lang = document.documentElement.lang;
    page.documentElement.dataset.theme = document.documentElement.dataset.theme;
    const workspaceStyles = document.querySelector('link[href$="/workspace/appearance.css"]');
    const projectStyles = document.querySelector('link[href$="/workspace/project.css"]');
    const controlStyles = document.querySelector('link[href$="/workspace/controls.css"]');
    const terminalStyles = document.querySelector('link[href$="/vendor/xterm/xterm.css"]');
    for (const { href } of [workspaceStyles, projectStyles, controlStyles, terminalStyles].filter(Boolean)) {
      const stylesheet = page.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = href;
      page.head.append(stylesheet);
    }
    const frame = page.createElement("div");
    frame.className = "detached-shell";
    const header = page.createElement("header");
    header.append(textNode("strong", page.title), control(tr("Reattach"), () => attach(session)));
    frame.append(header, session.element);
    page.body.replaceChildren(frame);
    session.live?.attach();
    popup.addEventListener("pagehide", () => {
      if (session.popup === popup) attach(session, false);
    }, { once: true });
    render();
  }

  const collapseButton = dock.querySelector('[data-terminal-action="collapse"]');
  function updateCollapse() {
    collapseButton.setAttribute("aria-expanded", String(!mount.hidden));
    collapseButton.textContent = mount.hidden ? tr("Open terminal") : tr("Collapse");
  }

  function openShell(direction, keepFocus = false) {
    if (!window.localWorkbench) return addPane("shell", direction);
    const shell = document.getElementById("local-shell").value;
    if (!shell) return status(tr("Open the app from the launcher and choose a shell."));
    addPane("shell", direction, { shell, workspace: document.getElementById("editor").hidden ? "project" : "code" }, keepFocus);
  }
  document.addEventListener("workspace:ssh", (event) => addPane("shell", "right", event.detail));
  document.addEventListener("workspace:run-file", ({ detail }) => addPane("shell", "right", detail));
  document.addEventListener("workspace:shells-ready", () => {
    if (![...sessions.values()].some((session) => session.live)) {
      openShell("right", document.activeElement !== document.body);
    }
  }, { once: true });

  const actions = {
    new: () => openShell("right"),
    log: () => document.dispatchEvent(new Event("workspace:show-log")),
    right: () => openShell("right"),
    down: () => openShell("down"),
    detach,
    collapse: () => {
      mount.hidden = !mount.hidden;
      updateCollapse();
    }
  };
  sessionSelect.addEventListener("change", () => {
    active = Number(sessionSelect.value);
    if (maximized && maximized !== active) {
      maximized = null;
      render();
    } else refreshSelection();
    focusPane(sessions.get(active));
    status();
  });
  for (const id of ["terminal-split-menu", "terminal-more-menu"]) {
    const menu = document.getElementById(id);
    menu.addEventListener("change", () => {
      const action = actions[menu.value];
      menu.value = "";
      if (action) {
        status();
        action();
      }
    });
  }
  for (const button of dock.querySelectorAll("[data-terminal-action]")) {
    button.addEventListener("click", () => {
      status();
      actions[button.dataset.terminalAction]();
    });
  }
  document.addEventListener("workspace:show-log", ({ detail }) => {
    const session = [...sessions.values()].find((item) => item.kind === "log");
    if (!session) return addPane("log", "right", undefined, detail?.keepFocus);
    active = session.id;
    session.tool = null;
    if (maximized && maximized !== active) maximized = null;
    mount.hidden = false;
    updateCollapse();
    render();
    if (detail?.keepFocus) return;
    if (session.popup) session.popup.focus();
    session.select.focus({ preventScroll: true });
  });
  document.addEventListener("workspace:theme", (event) => {
    for (const { popup, live } of sessions.values()) {
      if (popup && !popup.closed) popup.document.documentElement.dataset.theme = event.detail;
      live?.refreshTheme();
    }
  });
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    for (const session of sessions.values()) {
      session.live?.close();
      const popup = session.popup;
      session.popup = null;
      if (popup && !popup.closed) popup.close();
    }
  });

  window.WorkbenchTerminalPanes = { showTool };
  render();
  document.dispatchEvent(new Event("workspace:terminal-ready"));
})();
