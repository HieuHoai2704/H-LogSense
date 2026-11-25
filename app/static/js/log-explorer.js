"use strict";

// Log Explorer additions in the style of production log tools: facet counts, log patterns, insights
// (error spikes, new patterns, detector anomalies), surrounding logs, saved views and live refresh.
// logs.js owns the query, the page and the snapshot; this file listens to its events.
(() => {
  const t = window.logsenseTranslate || ((message) => message);
  const tn = window.logsenseTranslatePlural || ((n, one, other, ...values) => (n === 1 ? one : other).replace(/\{(\d+)\}/g, (_, i) => values[i]));
  const $ = (id) => document.getElementById(id);
  const logs = () => window.logsenseLogs;
  const number = new Intl.NumberFormat(document.documentElement.lang || "en");
  let current = null; // { params, scope }
  let patternsFor = null;
  let liveTimer = null;

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(t(data.error?.message || data.error?.code || "Request failed"));
    return data;
  }

  function scoped(path) {
    const params = new URLSearchParams(current.params);
    params.set("scope_token", current.scope);
    params.delete("cursor");
    return path + "?" + params;
  }

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  // ---- query bar helpers ----

  const queryInput = () => logs()?.form.elements.query;

  function quote(value) {
    return /[\s"]/.test(value) ? '"' + value.replace(/"/g, "") + '"' : value;
  }

  function addToQuery(fragment, { replaceField } = {}) {
    const input = queryInput();
    if (!input) return;
    let text = input.value.trim();
    if (replaceField) {
      // A field filter replaces an earlier filter on the same field and the opposite one.
      const pattern = new RegExp("(^|\\s)-?" + replaceField + ':(?:"[^"]*"|\\S+)', "gi");
      text = text.replace(pattern, " ").trim();
    }
    input.value = (text ? text + " " : "") + fragment;
    submit();
  }

  function submit() {
    const form = logs()?.form;
    if (form) form.requestSubmit();
  }

  // ---- facets ----

  const FACET_TITLES = { level: "Log level", host: "Host", service: "Component" };

  function renderFacets(facets) {
    const host = $("facet-groups");
    host.replaceChildren();
    // A fixed order: JSON object keys arrive sorted alphabetically.
    for (const name of ["level", "service", "host"].filter((key) => facets[key])) {
      const facet = facets[name];
      const group = element("section", null, "facet-group");
      const heading = element("h3", t(FACET_TITLES[name] || name));
      if (facet.distinct > facet.values.length)
        heading.append(element("small", " " + t("top {0} of {1}", facet.values.length, number.format(facet.distinct))));
      group.append(heading);
      const total = facet.values.reduce((sum, item) => sum + item.count, 0) || 1;
      for (const item of facet.values) {
        const value = item.value ?? "";
        const button = element("button", null, "facet-value");
        button.type = "button";
        button.disabled = item.value === null;
        const label = element("span", item.value === null ? t("(none)") : value, "facet-label" + (name === "level" ? " level-text level-" + value.toLowerCase() : ""));
        const count = element("span", number.format(item.count), "facet-count");
        const bar = element("span", null, "facet-bar");
        bar.style.width = (100 * item.count / total).toFixed(1) + "%";
        button.append(bar, label, count);
        button.title = t("Click to filter. Shift-click to exclude.");
        button.addEventListener("click", (event) => {
          const field = name === "level" ? "level" : name;
          const fragment = (event.shiftKey || event.altKey ? "-" : "") + field + ":" + quote(value);
          addToQuery(fragment, { replaceField: event.shiftKey || event.altKey ? null : field });
        });
        group.append(button);
      }
      if (!facet.values.length) group.append(element("p", t("No values in this scope."), "evidence-note"));
      host.append(group);
    }
  }

  // ---- insights ----

  function insightCard(kind, title, body, actions) {
    const card = element("article", null, "insight insight-" + kind);
    card.append(element("strong", title), element("p", body));
    card.title = body;
    if (actions.length) {
      const row = element("div", null, "insight-actions");
      row.append(...actions);
      card.append(row);
    }
    return card;
  }

  function actionButton(label, handler) {
    const button = element("button", label);
    button.type = "button";
    button.addEventListener("click", handler);
    return button;
  }

  function zoomTo(start, end) {
    const form = logs().form;
    form.elements.start_time.value = start.replace("Z", "");
    form.elements.end_time.value = end.replace("Z", "");
    submit();
  }

  // "2005-06-04T07:10:53.050000Z" -> "2005-06-04 07:10:53": the drawer and the zoom keep the exact value.
  const shortTime = (value) => String(value).replace("T", " ").replace(/\.\d+/, "").replace("Z", "");

  function renderInsights(data) {
    const host = $("log-insights");
    host.replaceChildren();
    const cards = [];
    for (const spike of data.error_spikes) {
      cards.push(insightCard(
        "danger",
        t("Error spike"),
        t("{0} error-level events between {1} and {2}; the usual level in this range is about {3} per interval.",
          number.format(spike.count), shortTime(spike.start), shortTime(spike.end), number.format(spike.baseline)),
        [actionButton(t("Zoom in"), () => zoomTo(spike.start, spike.end))],
      ));
    }
    for (const pattern of data.new_patterns) {
      cards.push(insightCard(
        "warning",
        t("New log pattern"),
        tn(pattern.count, "First seen {0} · {1} event: {2}", "First seen {0} · {1} events: {2}", shortTime(pattern.first), number.format(pattern.count), pattern.pattern),
        pattern.filter_terms.length
          ? [actionButton(t("Show these logs"), () => addToQuery(pattern.filter_terms.map((term) => '"' + term + '"').join(" ")))]
          : [],
      ));
    }
    const anomalies = data.detector_anomalies;
    if (anomalies.total) {
      const link = element("a", t("Open investigation"), "button");
      link.href = "/?" + new URLSearchParams(data.investigation);
      const high = (anomalies.by_priority.High || 0) + (anomalies.by_priority.Critical || 0);
      cards.push(insightCard(
        high ? "danger" : "info",
        t("Detector anomalies"),
        t("{0} anomalies from the detectors in this time range ({1} high or critical).", number.format(anomalies.total), number.format(high)),
        [link],
      ));
    }
    if (!cards.length) {
      cards.push(insightCard("ok", t("No insights"), t("No error spikes, new patterns or detector anomalies in this scope."), []));
    }
    host.append(...cards);
    host.hidden = false;
  }

  // ---- patterns ----

  async function loadPatterns() {
    if (!current || patternsFor === current.scope) return;
    const requested = current.scope;
    $("patterns-status").textContent = t("Grouping logs into patterns…");
    $("pattern-rows").replaceChildren();
    try {
      const data = await api(scoped("/api/v1/logs/patterns"));
      if (!current || current.scope !== requested) return;
      patternsFor = requested;
      $("patterns-status").textContent = (data.truncated
        ? t("{0} patterns in the newest {1} events of this scope.", number.format(data.pattern_count), number.format(data.scanned))
        : t("{0} patterns in {1} events.", number.format(data.pattern_count), number.format(data.scanned))) +
        " " + t("Numbers and hexadecimal values are shown as <*>.");
      const rows = $("pattern-rows");
      for (const pattern of data.patterns) {
        const tr = element("tr");
        const share = element("td");
        share.append(element("strong", number.format(pattern.count)), element("small", " " + (pattern.share * 100).toFixed(1) + "%"));
        const levels = element("td");
        for (const [level, count] of Object.entries(pattern.levels)) {
          levels.append(element("span", level + " " + number.format(count), "level-chip level-" + level.toLowerCase()));
        }
        const text = element("td", null, "pattern-text");
        text.append(element("code", pattern.pattern));
        const seen = element("td", pattern.first + " → " + pattern.last, "nowrap");
        const actions = element("td");
        if (pattern.filter_terms.length)
          actions.append(actionButton(t("Show logs"), () => {
            selectTab("logs");
            addToQuery(pattern.filter_terms.map((term) => '"' + term + '"').join(" "));
          }));
        actions.append(actionButton(t("Example"), () => logs().inspect(pattern.sample_id)));
        tr.append(share, levels, text, seen, actions);
        rows.append(tr);
      }
      if (!data.patterns.length) {
        const tr = element("tr"), td = element("td", t("No imported events match this scope."));
        td.colSpan = 5;
        tr.append(td);
        rows.append(tr);
      }
    } catch (error) {
      $("patterns-status").textContent = error.message;
    }
  }

  function selectTab(name) {
    const patterns = name === "patterns";
    $("tab-logs").setAttribute("aria-selected", String(!patterns));
    $("tab-patterns").setAttribute("aria-selected", String(patterns));
    $("log-list-view").hidden = patterns;
    $("log-patterns").hidden = !patterns;
    if (patterns) loadPatterns();
  }

  // ---- surrounding logs in the detail panel ----

  async function loadContext(id, event) {
    const body = $("log-context");
    body.replaceChildren();
    $("log-context-status").textContent = t("Loading surrounding logs…");
    const hostButton = $("log-filter-host"), patternButton = $("log-filter-pattern");
    hostButton.hidden = !event.host;
    hostButton.onclick = () => {
      document.getElementById("log-close").click();
      addToQuery("host:" + quote(event.host), { replaceField: "host" });
    };
    try {
      const data = await api(scoped("/api/v1/logs/" + id + "/context"));
      const rows = [...data.before.map((row) => [row, false]), [data.event, true], ...data.after.map((row) => [row, false])];
      for (const [row, focus] of rows) {
        const tr = element("tr", null, focus ? "context-focus" : "");
        tr.append(
          element("td", row.timestamp, "nowrap"),
          element("td", row.severity || "", "level-text level-" + (row.severity || "unknown").toLowerCase()),
          element("td", row.message),
        );
        if (!focus) {
          tr.tabIndex = 0;
          tr.title = t("Open this event");
          tr.addEventListener("click", () => logs().inspect(row.id));
          tr.addEventListener("keydown", (e) => { if (e.key === "Enter") logs().inspect(row.id); });
        }
        body.append(tr);
      }
      $("log-context-status").textContent = t("{0} events before and {1} after on host {2}, regardless of the current filters.",
        data.before.length, data.after.length, event.host || t("(none)"));
      patternButton.hidden = !data.pattern_terms.length;
      patternButton.onclick = () => {
        document.getElementById("log-close").click();
        addToQuery(data.pattern_terms.map((term) => '"' + term + '"').join(" "));
      };
    } catch (error) {
      $("log-context-status").textContent = error.message;
    }
  }

  // ---- saved views ----

  const VIEW_FIELDS = ["dataset_id", "start_time", "end_time", "host", "severity", "q", "query", "sort", "limit"];
  let views = [];

  function renderViews(selected = "") {
    const select = $("saved-views");
    select.replaceChildren(new Option(t("Choose a saved view"), ""));
    for (const view of views) select.add(new Option(view.name, view.name, false, view.name === selected));
    $("saved-view-delete").disabled = !select.value;
  }

  async function loadViews() {
    try {
      views = (await api("/api/v1/logs/views")).views;
      renderViews();
    } catch {
      views = [];
    }
  }

  function currentParams() {
    const params = {};
    const data = new FormData(logs().form);
    for (const key of VIEW_FIELDS) {
      const value = data.get(key);
      if (value) params[key] = key.endsWith("_time") ? value + "Z" : String(value);
    }
    return params;
  }

  function applyView(view) {
    const form = logs().form;
    for (const key of VIEW_FIELDS) {
      const field = form.elements[key];
      if (!field) continue;
      const value = view.params[key] ?? "";
      field.value = key.endsWith("_time") ? value.replace("Z", "") : value;
    }
    submit();
  }

  async function changeViews(method, body, name) {
    const csrf = logs().csrf();
    const path = "/api/v1/logs/views" + (method === "DELETE" ? "?" + new URLSearchParams({ name }) : "");
    const data = await api(path, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf || "" },
      body: body ? JSON.stringify(body) : undefined,
    });
    views = data.views;
  }

  // ---- live mode ----

  function setLive(on) {
    clearInterval(liveTimer);
    liveTimer = null;
    $("live-status").textContent = "";
    if (!on) return;
    const tick = () => {
      if (document.hidden || !$("log-detail").hidden) return;
      submit();
      $("live-status").textContent = t("Live · refreshed {0}", new Date().toLocaleTimeString(document.documentElement.lang || undefined));
    };
    liveTimer = setInterval(tick, 15000);
    tick();
  }

  // ---- wiring ----

  document.addEventListener("logsense:logs-loaded", async (event) => {
    current = { params: event.detail.params, scope: event.detail.scope };
    patternsFor = null;
    const requested = current.scope;
    if (!$("log-patterns").hidden) loadPatterns();
    try {
      const [facets, insights] = await Promise.all([
        api(scoped("/api/v1/logs/facets")),
        api(scoped("/api/v1/logs/insights")),
      ]);
      if (!current || current.scope !== requested) return;
      renderFacets(facets.facets);
      renderInsights(insights);
    } catch (error) {
      $("facet-groups").replaceChildren(element("p", error.message, "evidence-note"));
    }
  });
  document.addEventListener("logsense:log-inspected", (event) => {
    if (current) loadContext(event.detail.id, event.detail.event);
  });
  document.addEventListener("logsense:auth-changed", (event) => {
    if (event.detail) loadViews();
  });

  $("tab-logs").addEventListener("click", () => selectTab("logs"));
  $("tab-patterns").addEventListener("click", () => selectTab("patterns"));
  $("live-mode").addEventListener("change", (event) => setLive(event.target.checked));
  $("saved-views").addEventListener("change", (event) => {
    const view = views.find((item) => item.name === event.target.value);
    $("saved-view-delete").disabled = !view;
    if (view) applyView(view);
  });
  $("saved-view-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = event.target.elements.name.value.trim();
    if (!name) return;
    try {
      await changeViews("POST", { name, params: currentParams() });
      event.target.reset();
      renderViews(name);
      logs().say(t("Saved view {0}.", name));
    } catch (error) {
      logs().say(error.message);
    }
  });
  $("saved-view-delete").addEventListener("click", async () => {
    const name = $("saved-views").value;
    if (!name) return;
    try {
      await changeViews("DELETE", null, name);
      renderViews();
      logs().say(t("Deleted view {0}.", name));
    } catch (error) {
      logs().say(error.message);
    }
  });
})();
