"use strict";

// Analysis menu: keep dataset links on the dataset in view, and open the Alerts section on #incident-workspace.
(() => {
  const menu = document.getElementById("analysis-menu");
  if (!menu) return;
  const link = (key) => menu.querySelector(`a[data-menu-item="${key}"]`);

  function setDataset(id) {
    if (!/^\d+$/.test(String(id ?? ""))) return;
    for (const key of ["overview", "logs", "alerts", "quality", "pipeline", "schedule"]) {
      const anchor = link(key);
      if (!anchor) continue;
      const url = new URL(anchor.href, location.href);
      url.searchParams.set("dataset_id", id);
      anchor.href = url.pathname + url.search + url.hash;
    }
    const investigation = link("investigation");
    if (investigation) investigation.href = "/?" + new URLSearchParams({ source: "db-" + id });
  }
  window.analysisMenu = { setDataset };

  // Report pages: choosing another dataset shows it at once (the button stays for no-script use).
  for (const select of document.querySelectorAll(".dataset-picker select")) {
    const button = select.form.querySelector("button");
    if (button) button.hidden = true;
    select.addEventListener("change", () => select.form.requestSubmit());
  }

  const alerts = document.getElementById("incident-workspace");
  if (!alerts) return;
  const alertsLink = link("alerts");
  const logsLink = link("logs");
  const logsCurrent = logsLink?.getAttribute("aria-current");
  function showAlerts() {
    const active = location.hash === "#incident-workspace";
    // One highlighted entry: Alerts while its section is the target, Log Explorer otherwise.
    alertsLink?.toggleAttribute("aria-current", active);
    if (active) alertsLink?.setAttribute("aria-current", "page");
    if (logsCurrent) {
      if (active) logsLink.removeAttribute("aria-current");
      else logsLink.setAttribute("aria-current", logsCurrent);
    }
    if (!active) return;
    alerts.open = true;
    follow();
  }
  // The section is hidden until the signed-in workspace loads, and the log table above it grows as
  // results arrive; keep the section in view for a few seconds unless the person scrolls first.
  let following = null;
  function follow() {
    following?.disconnect();
    const stop = () => { following?.disconnect(); following = null; };
    const align = () => {
      if (location.hash !== "#incident-workspace") return stop();
      if (!alerts.hidden) alerts.scrollIntoView({ block: "start" });
    };
    following = new ResizeObserver(align);
    following.observe(document.body);
    new MutationObserver(align).observe(alerts, { attributes: true, attributeFilter: ["hidden"] });
    for (const event of ["wheel", "touchstart", "keydown", "mousedown"]) {
      window.addEventListener(event, stop, { once: true, passive: true });
    }
    setTimeout(stop, 5000);
    align();
  }
  window.addEventListener("hashchange", showAlerts);
  showAlerts();
})();
