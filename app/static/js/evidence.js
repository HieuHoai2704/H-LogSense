"use strict";
// Evidence is read from explicit contracts; no prose or importance is generated.
window.EvidenceDrawer = (() => {
  const panel = document.getElementById("detail-panel");
  const byId = id => document.getElementById(id);
  let current = null, currentId = null, opener = null, originScroll = 0;
  let mainController, rawController, relatedController;
  let generation = 0, rawSequence = 0, relatedSequence = 0;
  let raw = null, related = null, relatedCursor = "", cursorHistory = [];
  let rawOffset = 0, requestedRawOffset = 0, mainLoading = false, rawLoading = false, relatedLoading = false;
  const app = () => window.Investigation;
  const unavailable = value => value == null || value === "" ? "Unavailable — not supplied" : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);

  function url(path, extras = {}) {
    const target = app().stateURL(); target.pathname = path;
    target.searchParams.set("revision", app().revision());
    for (const [key, value] of Object.entries(extras)) {
      if (value === "" || value == null) target.searchParams.delete(key);
      else target.searchParams.set(key, value);
    }
    return target;
  }
  function endpoint(suffix = "") { return `/api/v1/anomalies/${encodeURIComponent(currentId)}/evidence${suffix}`; }
  function contextParams(cursor = relatedCursor) {
    return {relation: byId("related-relation").value, context_seconds: byId("related-window").value,
      context_limit: byId("related-limit").value, context_cursor: cursor};
  }
  async function fetchJSON(target, controller) {
    let timeout = false;
    const timer = setTimeout(() => { timeout = true; controller.abort(); }, 15000);
    try {
      const response = await fetch(target, {signal: controller.signal});
      const payload = await response.json().catch(() => { throw new Error("Evidence server response unavailable."); });
      if (!response.ok) throw new Error(payload.error?.message || "Evidence unavailable.");
      return payload;
    } catch (error) {
      if (timeout) throw new Error("Evidence query timed out. Retry or close the panel.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  function putFields(id, pairs) {
    const list = byId(id); list.replaceChildren();
    for (const [label, value] of pairs) {
      const row = document.createElement("div"), term = document.createElement("dt"), detail = document.createElement("dd");
      term.textContent = label; detail.textContent = unavailable(value);
      row.append(term, detail); list.append(row);
    }
  }
  function availability() {
    const disabled = !current || mainLoading || rawLoading || relatedLoading || !raw || !related;
    byId("export-evidence").disabled = disabled;
    byId("copy-raw").disabled = !raw || rawLoading;
  }
  function refreshContext() {
    const state = app().state();
    byId("evidence-scope").textContent = state.selection_start
      ? `Timeline selection: ${state.selection_start} – ${state.selection_end}${state.selection_detector ? ` · ${state.selection_detector}` : ""}`
      : `Result scope: ${state.source} · ${state.start_time} – ${state.end_time}`;
  }
  function rawHighlight(text) {
    const pre = byId("detail-raw"); pre.replaceChildren();
    const needle = app().state().q?.trim();
    if (!needle) { pre.textContent = text; return; }
    let offset = 0, found, highlights = 0;
    const haystack = text.toLowerCase(), match = needle.toLowerCase();
    while ((found = haystack.indexOf(match, offset)) >= 0 && highlights++ < 200) {
      pre.append(document.createTextNode(text.slice(offset, found)));
      const mark = document.createElement("mark"); mark.textContent = text.slice(found, found+needle.length); pre.append(mark);
      offset = found+needle.length;
    }
    pre.append(document.createTextNode(text.slice(offset)));
  }
  function renderRaw(page) {
    raw = page; rawOffset = page.offset; byId("raw-retry").hidden = true; rawHighlight(page.text);
    byId("raw-position").textContent = page.total_chars ? `${page.offset+1}–${page.offset+page.text.length} / ${page.total_chars} characters` : "Empty raw text";
    byId("raw-previous").disabled = page.offset === 0;
    byId("raw-next").disabled = !page.has_more;
    byId("raw-note").textContent = `Synthetic text; original log unavailable. Redaction applied.${page.has_more ? " More text available in chunks." : ""}`;
    byId("raw-redaction-note").textContent = page.redaction_note;
  }
  function renderRelated(data) {
    related = data;
    const container = byId("detail-related"); container.replaceChildren();
    for (const event of data.items) {
      const row = document.createElement("div"); row.className = "related-record";
      const button = document.createElement("button"); button.dataset.relatedId = event.id;
      button.textContent = `${event.id} · ${event.message || "Message unavailable"}`;
      const meta = document.createElement("p"); meta.textContent = `${event.timestamp} · ${event.host ?? "Unavailable"} / ${event.service ?? "Unavailable"}`;
      const reason = document.createElement("p"); reason.textContent = event.relationship_reasons.join(" · ");
      row.append(button, meta, reason); container.append(row);
    }
    if (!data.items.length) container.textContent = "No related fixture records match this relationship and context interval.";
    byId("related-status").textContent = `${data.items.length} records on this page · ${data.interval.start} – ${data.interval.end} · original raw context logs unavailable`;
    byId("related-previous").disabled = !cursorHistory.length;
    byId("related-next").disabled = !data.has_more;
    byId("related-retry").hidden = true;
    for (const option of data.available_relations) {
      const element = [...byId("related-relation").options].find(o => o.value === option.value);
      if (element) element.disabled = !option.available;
    }
  }
  function render(data) {
    const a = data.anomaly, d = data.detector_evidence, p = data.raw_event.provenance;
    current = data;
    byId("detail-title").textContent = a.id;
    byId("detail-message").textContent = data.summary.observed_signal ?? "Signal statement unavailable.";
    byId("detail-priority").textContent = a.severity ?? "Priority unavailable";
    byId("detail-priority").className = `severity severity-${(a.severity || "").toLowerCase()}`;
    putFields("detail-fields", [["Detection timestamp · UTC", a.timestamp], ["Host", a.host], ["Service", a.service],
      ["Detector", a.detector], ["Detection unit", a.unit], ["Dataset", `${a.dataset_name} · ${a.dataset_id}`], ["Model run", a.model_run_id]]);
    putFields("raw-provenance", [["Raw fixture timestamp", p.raw_timestamp], ["Adapted UTC timestamp", p.parsed_timestamp], ["Host", p.host],
      ["Source file", p.source_file], ["Source line", p.source_line], ["Event reference", p.event_reference], ["Parsing status", p.parsing_status]]);
    byId("detail-parsed").textContent = JSON.stringify(data.parsed_fields, null, 2);
    byId("detail-actual").textContent = unavailable(d.observed_value);
    byId("detail-typical").textContent = unavailable(d.reference_statistics);
    byId("explanation-status").textContent = d.explanation_status;
    let pairs = d.kind === "ml" ? [["Detection method", d.method], ["Model name", d.model_name], ["Model version", d.model_version],
      ["Feature schema", d.feature_schema], ["Detection score · synthetic", d.score], ["Score direction", d.score_direction],
      ["Configured threshold", d.configured_threshold], ["Detection unit", d.detection_unit], ["Feature evidence", d.feature_evidence]]
      : [["Rule ID", d.rule_id], ["Rule version", d.rule_version], ["Configured threshold", d.configured_threshold],
         ["Observation window", d.observation_window], ["Detection score · synthetic", d.score]];
    if (d.kind === "unknown") pairs = [["Detection method", d.method], ["Detector family", null], ["Detection unit", d.detection_unit], ["Detection score · synthetic", d.score]];
    putFields("detector-evidence", pairs);
    byId("detail-disclaimer").textContent = d.score_interpretation;
    byId("previous-anomaly").disabled = !data.navigation.previous_id;
    byId("next-anomaly").disabled = !data.navigation.next_id;
    byId("detail-status").textContent = data.navigation.in_result_scope ? "DEMO · Selected synthetic supporting record" : data.navigation.note;
    byId("previous-anomaly").title = byId("next-anomaly").title = data.navigation.note;
    byId("filter-evidence-host").hidden = !a.host;
    byId("filter-evidence-service").hidden = !a.service;
    renderRaw(data.raw_event.page); renderRelated(data.related_events);
    byId("detail-content").hidden = false;
    refreshContext(); availability();
  }
  async function open(id, trigger = null) {
    if (panel.hidden) { originScroll = window.scrollY; opener = trigger; }
    else if (trigger?.closest("#workspace-results")) opener = trigger;
    mainController?.abort(); rawController?.abort(); relatedController?.abort();
    generation++; rawSequence++; relatedSequence++;
    const ticket = generation;
    currentId = id; current = null; raw = related = null; mainLoading = true; rawLoading = relatedLoading = false;
    relatedCursor = ""; cursorHistory = []; rawOffset = 0;
    app().markSelected(id); panel.hidden = false; app().updatePanelMode(); panel.scrollTop = 0;
    byId("detail-title").textContent = id; byId("detail-title").focus({preventScroll: true});
    byId("detail-content").hidden = true; byId("retry-detail").hidden = true;
    byId("previous-anomaly").disabled = byId("next-anomaly").disabled = true;
    byId("detail-status").textContent = "Loading selected evidence…"; refreshContext(); availability();
    mainController = new AbortController();
    try {
      const data = await fetchJSON(url(endpoint(), contextParams("")), mainController);
      if (ticket !== generation || panel.hidden) return;
      mainLoading = false; render(data);
    } catch (error) {
      if (error.name !== "AbortError" && ticket === generation) {
        byId("detail-status").textContent = error.message; byId("retry-detail").hidden = false;
      }
    } finally { if (ticket === generation) { mainLoading = false; availability(); } }
  }
  function close(restore = true) {
    generation++; rawSequence++; relatedSequence++;
    mainController?.abort(); rawController?.abort(); relatedController?.abort();
    const oldId = currentId;
    currentId = null; current = null; panel.hidden = true; app().markSelected(null); app().updatePanelMode();
    if (restore) {
      const target = opener?.isConnected ? opener : document.querySelector(`[data-event-id="${CSS.escape(oldId || "")}"]`) || byId("events-title");
      target?.focus({preventScroll: true}); window.scrollTo({top: originScroll, behavior: "instant"});
    }
  }
  async function loadRaw(offset) {
    const ticket = ++rawSequence, owner = generation;
    rawController?.abort(); rawController = new AbortController(); rawLoading = true;
    requestedRawOffset = offset; byId("raw-retry").hidden = true;
    byId("raw-previous").disabled = byId("raw-next").disabled = true;
    byId("detail-raw").textContent = "Loading raw evidence chunk…"; availability();
    try {
      const data = await fetchJSON(url(endpoint("/raw"), {raw_offset: offset, raw_limit: raw?.limit || 2048}), rawController);
      if (ticket === rawSequence && owner === generation) renderRaw(data.raw_event);
    } catch (error) {
      if (error.name !== "AbortError" && ticket === rawSequence && owner === generation) {
        byId("detail-raw").textContent = `Raw evidence unavailable: ${error.message}`; raw = null;
        byId("raw-retry").hidden = false; byId("raw-previous").disabled = byId("raw-next").disabled = true;
      }
    } finally { if (ticket === rawSequence && owner === generation) { rawLoading = false; availability(); } }
  }
  async function loadRelated(cursor = "") {
    const ticket = ++relatedSequence, owner = generation;
    relatedController?.abort(); relatedController = new AbortController(); relatedLoading = true;
    byId("detail-related").replaceChildren(); byId("related-status").textContent = "Loading bounded related records…";
    byId("related-retry").hidden = true; byId("related-previous").disabled = byId("related-next").disabled = true; related = null; availability();
    try {
      const data = await fetchJSON(url(`/api/v1/anomalies/${encodeURIComponent(currentId)}/related`, contextParams(cursor)), relatedController);
      if (ticket === relatedSequence && owner === generation) { relatedCursor = cursor; renderRelated(data.related_events); }
    } catch (error) {
      if (error.name !== "AbortError" && ticket === relatedSequence && owner === generation) {
        byId("related-status").textContent = error.message; byId("related-retry").hidden = false;
      }
    } finally { if (ticket === relatedSequence && owner === generation) { relatedLoading = false; availability(); } }
  }
  async function copy(text) {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard is unavailable in this browser context.");
      await navigator.clipboard.writeText(text); app().notify("Copied redacted evidence.");
    } catch (error) { app().notify(`Copy failed: ${error.message}`); }
  }
  async function exportEvidence() {
    if (!current || !raw || !related || mainLoading || rawLoading || relatedLoading) return;
    const button = byId("export-evidence"), controller = new AbortController();
    const id = currentId;
    button.disabled = true; button.textContent = "Exporting evidence…";
    try {
      const data = await fetchJSON(url(endpoint("/export"), {...contextParams(), raw_offset: raw.offset, raw_limit: raw.limit}), controller);
      const file = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
      const link = document.createElement("a"); link.href = file; link.download = `synthetic-evidence-${id}.json`; link.click();
      setTimeout(() => URL.revokeObjectURL(file), 1000); app().notify("Exported current redacted evidence page; omitted data is identified in availability.");
    } catch (error) { app().notify(`Evidence export failed: ${error.message}`); }
    finally { button.textContent = "Export evidence JSON"; availability(); }
  }
  function filterDimension(key, value) {
    if (!current || !value) return;
    const target = app().clearSelection(app().stateURL()); target.searchParams.delete(key); target.searchParams.append(key, value);
    close(false); app().load(target);
  }
  panel.addEventListener("click", event => {
    const id = event.target.id;
    if (id === "previous-anomaly" && current?.navigation.previous_id) open(current.navigation.previous_id);
    if (id === "next-anomaly" && current?.navigation.next_id) open(current.navigation.next_id);
    if (id === "copy-raw" && raw) copy(raw.text);
    if (id === "raw-retry") loadRaw(requestedRawOffset);
    if (id === "raw-next" && raw?.has_more) loadRaw(raw.next_offset);
    if (id === "raw-previous") loadRaw(Math.max(0, rawOffset-(raw?.limit || 2048)));
    if (id === "related-next" && related?.next_cursor) { cursorHistory.push(relatedCursor); loadRelated(related.next_cursor); }
    if (id === "related-previous" && cursorHistory.length) loadRelated(cursorHistory.pop());
    if (id === "related-retry") { cursorHistory = []; loadRelated(""); }
    if (id === "filter-evidence-host") filterDimension("host", current?.anomaly.host);
    if (id === "filter-evidence-service") filterDimension("service", current?.anomaly.service);
    if (id === "view-evidence-raw") { byId("raw-section").open = true; byId("detail-raw").scrollIntoView({block: "center"}); byId("detail-raw").focus({preventScroll: true}); }
    if (id === "copy-evidence-reference" && current) { const reference = app().stateURL(); reference.searchParams.set("anomaly_id", current.anomaly.id); copy(reference.href); }
    if (id === "export-evidence") exportEvidence();
    if (id === "focus-evidence-range" && related) {
      const target = app().clearSelection(app().stateURL()); target.searchParams.set("range", "custom");
      target.searchParams.set("start_time", related.interval.start); target.searchParams.set("end_time", related.interval.end);
      target.searchParams.set("resolution", "auto"); close(false); app().load(target);
    }
  });
  panel.addEventListener("change", event => {
    if (event.target.id === "wrap-raw") byId("detail-raw").classList.toggle("no-wrap", !event.target.checked);
    if (["related-relation", "related-window", "related-limit"].includes(event.target.id)) { cursorHistory = []; relatedCursor = ""; loadRelated(""); }
  });
  document.addEventListener("DOMContentLoaded", () => {
    const reference = new URL(location.href).searchParams.get("anomaly_id");
    if (reference && /^LS-\d{4,12}$/.test(reference)) open(reference);
  });
  return {open, close, refreshContext};
})();
