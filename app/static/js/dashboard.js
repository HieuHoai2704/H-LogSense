"use strict";
// Applied state belongs to the last successful, atomic server response.
const initial = JSON.parse(document.getElementById("initial-state").textContent);
let applied = initial.state;
let revision = initial.revision;
const mount = document.getElementById("workspace-results");
const shell = document.querySelector(".app-shell");
const panel = document.getElementById("detail-panel");
const status = document.getElementById("query-status");
let pending = null, sequence = 0, retryURL = null, pendingKey = "";
let dirty = false, editVersion = 0;
let selectedId = null;
let drag = null, suppressClick = false, keyboardAnchor = null, toastTimer, resizeTimer;
let viewMode = applied.mode;

function params(state) {
  const values = new URLSearchParams();
  for (const [key, value] of Object.entries(state)) {
    if (Array.isArray(value)) value.forEach(v => values.append(key, v));
    else if (value !== null && value !== undefined && value !== "") values.set(key, value);
  }
  return values;
}
function stateURL(state = applied) { const url = new URL("/", location.origin); url.search = params(state); return url; }
function clearSelection(url) { ["selection_start", "selection_end", "selection_detector", "page"].forEach(k => url.searchParams.delete(k)); return url; }
function formURL(clear = true) {
  const url = new URL("/", location.origin);
  url.search = new URLSearchParams(new FormData(document.getElementById("filters")));
  return clear ? clearSelection(url) : url;
}
function scopeLabel(state) {
  return `${state.source} · ${state.start_time} – ${state.end_time}${state.q ? ` · search: ${state.q}` : ""}${["host", "service", "severity", "detector"].map(k => state[k]?.length ? ` · ${k}: ${state[k].join(", ")}` : "").join("")}`;
}
function exportAvailability(disabled) {
  const link = document.getElementById("export-button");
  link?.classList.toggle("export-disabled", disabled);
  link?.setAttribute("aria-disabled", String(disabled));
  if (link) link.tabIndex = disabled ? -1 : 0;
}
function markDirty() {
  editVersion++; dirty = true; exportAvailability(true);
  status.textContent = "Filters changed — Apply or Done to update. Results still show: " + scopeLabel(applied);
}
function notify(message) {
  const toast = document.getElementById("toast"); toast.textContent = message; toast.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
}
function plotWidth() {
  const width = document.querySelector(".overall-row .heat-cells")?.getBoundingClientRect().width || 1000;
  return Math.max(240, Math.min(4000, Math.round(width)));
}
function applyMode(mode, updateURL = false) {
  viewMode = mode;
  const timeline = document.querySelector(".timeline-panel");
  timeline?.classList.toggle("mode-volume", mode === "volume");
  timeline?.classList.toggle("mode-severity", mode === "severity");
  document.querySelectorAll("[data-mode]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
  document.getElementById("severity-legend").hidden = mode !== "severity";
  document.getElementById("volume-legend").hidden = mode !== "volume";
  const field = document.querySelector('[name="mode"]'); if (field) field.value = mode;
  applied.mode = mode;
  if (updateURL) history.replaceState({}, "", stateURL());
}
function visibleCells() { return [...mount.querySelectorAll("[data-cell]")].filter(c => c.getClientRects().length); }
function initializeChart() {
  const cells = visibleCells(); cells.forEach(c => c.tabIndex = -1);
  const target = cells.find(c => c.classList.contains("selected-cell")) || cells[0];
  if (target) target.tabIndex = 0;
  const reset = document.querySelector('[data-nav="reset"]');
  if (reset) reset.disabled = applied.start_time === applied.base_start_time && applied.end_time === applied.base_end_time;
  const zoom = document.querySelector('[data-nav="in"]');
  if (zoom) zoom.disabled = Date.parse(applied.end_time)-Date.parse(applied.start_time) <= 60000;
  applyMode(viewMode);
}
function focusDescriptor() {
  const element = document.activeElement;
  if (!mount.contains(element)) return null;
  if (element.id) return {id: element.id};
  if (element.matches("[data-cell]")) return {start: element.dataset.start, detector: element.dataset.detector};
  if (element.dataset.eventId) return {event: element.dataset.eventId};
  if (element.name) return {name: element.name, value: element.value};
  return null;
}
function restoreFocus(key) {
  if (!key || !panel.hidden) return;
  let element = key.id ? document.getElementById(key.id) : key.start ? [...mount.querySelectorAll("[data-cell]")].find(c => c.dataset.start === key.start && c.dataset.detector === key.detector) : key.event ? mount.querySelector(`[data-event-id="${CSS.escape(key.event)}"]`) : [...mount.querySelectorAll("[name]")].find(c => c.name === key.name && c.value === key.value);
  if (!element || !element.getClientRects().length) element = document.getElementById("events-title");
  element?.focus({preventScroll: true});
}
function restoreDraft(data) {
  const form = document.getElementById("filters");
  for (const element of form.elements) {
    if (!element.name || element.type === "hidden") continue;
    if (element.type === "checkbox") element.checked = data.getAll(element.name).includes(element.value);
    else if (data.has(element.name)) element.value = data.get(element.name);
  }
}
async function load(url, historyMode = "push") {
  const apiURL = new URL("/api/v1/investigation", location.origin);
  apiURL.search = url.search; apiURL.searchParams.set("width", plotWidth());
  const key = apiURL.href;
  if (pending && pendingKey === key) return;
  pending?.abort(); const controller = new AbortController(); pending = controller; pendingKey = key;
  const ticket = ++sequence, submittedVersion = editVersion;
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
  retryURL = url; mount.setAttribute("aria-busy", "true");
  document.getElementById("request-error").hidden = true; exportAvailability(true);
  status.textContent = `Updating requested scope… Showing previous results: ${scopeLabel(applied)}`;
  try {
    const response = await fetch(apiURL, {signal: controller.signal});
    const data = await response.json().catch(() => { throw new Error("Server response unavailable. Retry this query."); });
    if (!response.ok) throw new Error(data.error?.message || "Query failed.");
    if (ticket !== sequence) return;
    const focus = focusDescriptor();
    const scroll = document.querySelector(".timeline-scroll")?.scrollLeft || 0;
    const disclosures = [...mount.querySelectorAll("details[id],details[data-group]")].map(d => ({id: d.id, group: d.dataset.group, open: d.open}));
    const newerDraft = editVersion !== submittedVersion;
    const draft = newerDraft ? new FormData(document.getElementById("filters")) : null;
    // Escaped HTML is rendered by this application's Jinja templates only.
    const priorScope = applied;
    mount.innerHTML = data.html; applied = data.state; revision = data.revision;
    dirty = newerDraft;
    if (draft) restoreDraft(draft);
    for (const d of disclosures) {
      const element = d.id ? document.getElementById(d.id) : [...mount.querySelectorAll("[data-group]")].find(e => e.dataset.group === d.group);
      if (element) element.open = d.open;
    }
    initializeChart();
    document.querySelector(".timeline-scroll").scrollLeft = scroll;
    if (selectedId && ["source","start_time","end_time","host","service","severity","detector","q","selection_start","selection_end","selection_detector"].some(k => JSON.stringify(priorScope[k]) !== JSON.stringify(applied[k]))) closeDetail(false);
    if (selectedId) window.EvidenceDrawer.refreshContext();
    if (selectedId) markSelectedRow();
    const canonical = stateURL();
    if (historyMode === "push" && canonical.href !== location.href) history.pushState({}, "", canonical);
    if (historyMode === "replace") history.replaceState({}, "", canonical);
    status.textContent = `Query ready · ${data.result_count} results · ${data.query_ms} ms · DEMO${dirty ? " · Unapplied filter changes" : ""}`;
    restoreFocus(focus);
  } catch (error) {
    if ((error.name !== "AbortError" || timedOut) && ticket === sequence) {
      dirty = true;
      document.getElementById("request-error").hidden = false;
      document.getElementById("error-message").textContent = `${timedOut ? "Query timed out after 15 seconds." : error.message} Previous results retained. Requested filters have not been applied.`;
      status.textContent = "Query failed. Showing previous scope: " + scopeLabel(applied);
    }
  } finally {
    clearTimeout(timeout);
    if (ticket === sequence) { pending = null; pendingKey = ""; mount.setAttribute("aria-busy", "false"); exportAvailability(dirty); }
  }
}
function changeRange(url, start, end) {
  clearSelection(url); url.searchParams.set("range", "custom");
  url.searchParams.set("start_time", new Date(start).toISOString()); url.searchParams.set("end_time", new Date(end).toISOString());
  url.searchParams.set("resolution", "auto"); return url;
}
function navigate(action) {
  if (dirty && !pending) { notify("Apply or revert filter changes before navigating the timeline."); return; }
  const a = Date.parse(applied.start_time), b = Date.parse(applied.end_time), span = b-a;
  let start = a, end = b;
  if (action === "in") { start = a+span/4; end = b-span/4; }
  if (action === "out") { start = a-span/2; end = b+span/2; }
  if (action === "previous") { start -= span; end -= span; }
  if (action === "next") { start += span; end += span; }
  if (action === "selection") { start = Date.parse(applied.selection_start); end = Date.parse(applied.selection_end); }
  if (action === "reset") { start = Date.parse(applied.base_start_time); end = Date.parse(applied.base_end_time); }
  if (!Number.isFinite(start+end) || end-start < 60000 || end-start > 366*86400000) { notify("Choose a range between one minute and 366 days."); return; }
  load(changeRange(stateURL(), start, end));
}
function selectRange(first, last) {
  if (dirty) { notify("Apply or revert filter changes before selecting bins."); return; }
  const url = clearSelection(stateURL());
  url.searchParams.set("selection_start", first < last ? first : last);
  // Caller supplies chronological start and exclusive end in normal cases.
  url.searchParams.set("selection_end", first < last ? last : first);
  load(url);
}
function inspectCell(cell) {
  const severity = JSON.parse(cell.dataset.breakdown);
  const name = cell.dataset.detector ? document.querySelector(`[name="detector"][value="${CSS.escape(cell.dataset.detector)}"]`)?.parentElement.querySelector("span")?.textContent : "Overall";
  document.getElementById("bin-inspector").textContent = `${name} · ${cell.dataset.label} · ${cell.dataset.count} anomalies · C ${severity.Critical}, H ${severity.High}, M ${severity.Medium}, L ${severity.Low} · ${cell.dataset.coverage} fixture coverage${cell.dataset.coverage !== "complete" ? " — observed count may be incomplete" : ""}`;
}
function previewRange(start, end) {
  mount.querySelectorAll("[data-cell]").forEach(c => c.classList.toggle("brush-preview", c.dataset.start < end && c.dataset.end > start));
}
function clearPreview() { mount.querySelectorAll(".brush-preview").forEach(c => c.classList.remove("brush-preview")); }
function updatePanelMode() {
  const split = innerWidth >= 1520;
  const open = !panel.hidden;
  document.body.classList.toggle("detail-modal", open && !split);
  document.body.classList.toggle("detail-split", open && split);
  panel.setAttribute("role", split ? "region" : "dialog");
  if (open && !split) panel.setAttribute("aria-modal", "true"); else panel.removeAttribute("aria-modal");
  shell.inert = open && !split;
}
function markSelectedRow() {
  mount.querySelectorAll("[data-row-id]").forEach(row => {
    const selected = row.dataset.rowId === selectedId;
    row.classList.toggle("selected-row", selected);
    row.querySelectorAll("[data-event-id]").forEach(button => {
      button.setAttribute("aria-expanded", String(selected));
      button.setAttribute("aria-controls", "detail-panel");
      if (button.classList.contains("inspect-button")) button.textContent = selected ? "Selected" : "Inspect →";
    });
  });
}
function closeDetail(restore = true) { window.EvidenceDrawer.close(restore); }
function openDetail(id, trigger = null) { return window.EvidenceDrawer.open(id, trigger); }
async function exportCSV(link) {
  if (pending || dirty || link.dataset.exporting) { notify("Wait for the applied scope before exporting."); return; }
  link.dataset.exporting = "true"; link.textContent = "Exporting…";
  try {
    const response = await fetch(link.href);
    if (!response.ok) { const data = await response.json(); throw new Error(data.error?.message || "Export failed."); }
    const file = URL.createObjectURL(await response.blob());
    const download = document.createElement("a"); download.href = file; download.download = "synthetic-investigation-results.csv"; download.click();
    setTimeout(() => URL.revokeObjectURL(file), 1000);
    notify(`Exported ${response.headers.get("X-Result-Count")} synthetic anomalies from the applied scope.`);
  } catch (error) { notify(error.message); }
  finally { if (link.isConnected) link.textContent = "Export scoped CSV"; delete link.dataset.exporting; }
}

document.addEventListener("submit", event => { if (event.target.id === "filters") { event.preventDefault(); load(formURL()); } });
document.addEventListener("input", event => {
  if (event.target.id === "detector-search") { const text = event.target.value.toLowerCase(); document.querySelectorAll('#picker-detector .facet-option').forEach(label => label.hidden = !label.textContent.toLowerCase().includes(text)); return; }
  if (event.target.form?.id === "filters" && event.target.name) markDirty();
});
document.addEventListener("change", event => {
  const field = event.target;
  if (field.id === "row-sort") { const url = stateURL(); url.searchParams.set("sort", field.value); url.searchParams.delete("row_page"); load(url); return; }
  if (field.form?.id !== "filters" || field.tagName !== "SELECT") return;
  if (field.name === "range" && field.value === "custom") { document.getElementById("custom-range").hidden = false; markDirty(); return; }
  const url = formURL(field.name !== "timezone");
  if (field.name === "source" || field.name === "range") {
    ["start_time", "end_time", "base_start_time", "base_end_time"].forEach(k => url.searchParams.delete(k));
    if (field.name === "source") { url.searchParams.set("range", "full"); closeDetail(false); }
  }
  load(url);
});
document.addEventListener("click", event => {
  const target = event.target;
  const link = target.closest("a[data-workspace-link]");
  if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
    event.preventDefault();
    if (suppressClick) return;
    if (dirty && link.hasAttribute("data-cell")) { notify("Apply or revert filters before selecting a bin."); return; }
    load(new URL(link.href)); return;
  }
  const inspect = target.closest("[data-event-id]"); if (inspect) { openDetail(inspect.dataset.eventId, inspect); return; }
  const related = target.closest("[data-related-id]"); if (related) { openDetail(related.dataset.relatedId); return; }
  const nav = target.closest("[data-nav]"); if (nav) { navigate(nav.dataset.nav); return; }
  const mode = target.closest("[data-mode]"); if (mode) { applyMode(mode.dataset.mode, !pending); return; }
  const picker = target.closest(".apply-picker"); if (picker) { picker.closest("details").open = false; load(formURL()); return; }
  if (target.id === "export-button") { event.preventDefault(); exportCSV(target); }
  if (target.id === "close-detail") closeDetail();
  if (target.id === "retry-detail" && selectedId) openDetail(selectedId);
  if (target.id === "retry-button" && retryURL) load(retryURL);
  if (target.id === "revert-button") { editVersion++; load(stateURL(), "none"); }
  if (target.id === "range-selection-toggle") { const box = document.getElementById("range-selection-form"); box.hidden = !box.hidden; target.setAttribute("aria-expanded", String(!box.hidden)); if (!box.hidden) document.getElementById("selection-input-start").focus(); }
  if (target.id === "select-exact-range" || target.id === "use-custom-range") {
    const select = target.id === "select-exact-range";
    const a = document.getElementById(select ? "selection-input-start" : "custom-start").value;
    const b = document.getElementById(select ? "selection-input-end" : "custom-end").value;
    if (!a || !b || Date.parse(a+"Z") >= Date.parse(b+"Z")) { notify("Enter a valid start and exclusive end in UTC."); return; }
    if (select) selectRange(new Date(a+"Z").toISOString(), new Date(b+"Z").toISOString());
    else { const url = changeRange(formURL(), Date.parse(a+"Z"), Date.parse(b+"Z")); url.searchParams.delete("base_start_time"); url.searchParams.delete("base_end_time"); load(url); }
  }
});
document.addEventListener("pointerover", event => { const cell = event.target.closest("[data-cell]"); if (cell) inspectCell(cell); });
document.addEventListener("focusin", event => { const cell = event.target.closest("[data-cell]"); if (cell) { visibleCells().forEach(c => c.tabIndex = c === cell ? 0 : -1); inspectCell(cell); } });
document.addEventListener("dragstart", event => { if (event.target.closest("[data-cell]")) event.preventDefault(); });
document.addEventListener("pointerdown", event => {
  const cell = event.target.closest("[data-cell]");
  if (cell && event.button === 0 && event.pointerType !== "touch") drag = {cell, x: event.clientX, last: cell, moved: false};
});
document.addEventListener("pointermove", event => {
  if (!drag) return;
  const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-cell]");
  if (!cell) return;
  if (Math.abs(event.clientX-drag.x) > 6) drag.moved = true;
  drag.last = cell;
  if (drag.moved) previewRange(drag.cell.dataset.start < cell.dataset.start ? drag.cell.dataset.start : cell.dataset.start, drag.cell.dataset.end > cell.dataset.end ? drag.cell.dataset.end : cell.dataset.end);
});
document.addEventListener("pointerup", () => {
  if (!drag) return;
  if (drag.moved) {
    suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
    const a = drag.cell.dataset.start < drag.last.dataset.start ? drag.cell.dataset.start : drag.last.dataset.start;
    const b = drag.cell.dataset.end > drag.last.dataset.end ? drag.cell.dataset.end : drag.last.dataset.end;
    selectRange(a, b);
  }
  drag = null; clearPreview();
});
document.addEventListener("pointercancel", () => { drag = null; clearPreview(); });
document.addEventListener("keydown", event => {
  if (!panel.hidden && (event.key === "Escape" || (event.key === "Tab" && panel.getAttribute("aria-modal") === "true"))) {
    if (event.key === "Escape") { event.preventDefault(); closeDetail(); return; }
    const controls = [...panel.querySelectorAll('button,a[href],input,select,summary,[tabindex="0"]')].filter(c => !c.disabled && c.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement.id === "detail-title")) { event.preventDefault(); last?.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) { event.preventDefault(); first?.focus(); }
    return;
  }
  if (event.key === "Escape") {
    const picker = event.target.closest(".filter-picker"); if (picker) { picker.open = false; picker.querySelector("summary").focus(); return; }
  }
  const cell = event.target.closest("[data-cell]"); if (!cell) return;
  const rows = [...mount.querySelectorAll(".heat-row:not(.axis-row)")].filter(r => r.getClientRects().length);
  const row = cell.closest(".heat-row"), ri = rows.indexOf(row), cells = [...row.querySelectorAll("[data-cell]")], ci = cells.indexOf(cell);
  let next = null;
  if (event.key === "ArrowRight") next = cells[Math.min(cells.length-1, ci+1)];
  if (event.key === "ArrowLeft") next = cells[Math.max(0, ci-1)];
  if (event.key === "ArrowDown") next = rows[Math.min(rows.length-1, ri+1)]?.querySelectorAll("[data-cell]")[ci];
  if (event.key === "ArrowUp") next = rows[Math.max(0, ri-1)]?.querySelectorAll("[data-cell]")[ci];
  if (event.key === "Home") next = (event.ctrlKey ? rows[0] : row).querySelector("[data-cell]");
  if (event.key === "End") next = [...(event.ctrlKey ? rows.at(-1) : row).querySelectorAll("[data-cell]")].at(-1);
  if (next) {
    event.preventDefault();
    if (event.shiftKey) { keyboardAnchor ||= cell; previewRange(keyboardAnchor.dataset.start < next.dataset.start ? keyboardAnchor.dataset.start : next.dataset.start, keyboardAnchor.dataset.end > next.dataset.end ? keyboardAnchor.dataset.end : next.dataset.end); }
    else { keyboardAnchor = null; clearPreview(); }
    next.focus(); return;
  }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (keyboardAnchor) { const a = keyboardAnchor.dataset.start < cell.dataset.start ? keyboardAnchor.dataset.start : cell.dataset.start; const b = keyboardAnchor.dataset.end > cell.dataset.end ? keyboardAnchor.dataset.end : cell.dataset.end; keyboardAnchor = null; selectRange(a, b); clearPreview(); }
    else cell.click();
  }
  if (event.key === "Escape") { event.preventDefault(); if (keyboardAnchor) { keyboardAnchor = null; clearPreview(); } else if (applied.selection_start) load(clearSelection(stateURL())); }
});
document.addEventListener("toggle", event => { if (event.target.matches(".detector-group")) { const cells = visibleCells(); if (!cells.some(c => c.tabIndex === 0) && cells[0]) cells[0].tabIndex = 0; } }, true);
window.addEventListener("popstate", () => { viewMode = new URL(location.href).searchParams.get("mode") || "severity"; load(new URL(location.href), "none"); });
window.addEventListener("resize", () => {
  updatePanelMode(); clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (!dirty && !pending && Math.abs(plotWidth()-applied.width) >= 140) load(stateURL(), "replace"); }, 250);
});
window.Investigation = {
  state: () => applied, revision: () => revision, stateURL, clearSelection, load, notify, updatePanelMode,
  markSelected: id => { selectedId = id; markSelectedRow(); }
};
initializeChart();
// Resolve width-dependent bins once; subsequent renders use the server canonical state.
if (Math.abs(plotWidth()-applied.width) >= 140) load(stateURL(), "replace");
