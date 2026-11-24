"use strict";
(() => {
  const t = window.logsenseTranslate;
  const tn = window.logsenseTranslatePlural;
  const form = document.getElementById("log-filters"),
    status = document.getElementById("logs-status"),
    investigationNav = document.getElementById("log-investigation-nav"),
    investigationLink = document.getElementById("log-investigation");
  let applied = null,
    scope = null,
    cursor = null,
    historyCursors = [null],
    index = 0,
    controller = null,
    sequence = 0,
    csrf = null,
    baseRange = null,
    opener = null,
    selected = null,
    rawOffset = 0;
  const panel = document.getElementById("log-detail");
  function say(message) {
    status.textContent = message;
  }
  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        data.error?.code === "invalid_credentials"
          ? t("Invalid credentials. Check your username and password.")
          : t(data.error?.message || data.error?.code || "Request failed"),
      );
    return data;
  }
  function query() {
    const p = new URLSearchParams(new FormData(form));
    for (const [k, v] of [...p]) if (!v) p.delete(k);
    for (const k of ["start_time", "end_time"])
      if (p.has(k)) p.set(k, p.get(k) + "Z");
    return p;
  }
  function detailClose() {
    panel.hidden = true;
    document.querySelector(".app-shell").inert = false;
    document.body.classList.remove("detail-modal");
    opener?.focus({ preventScroll: true });
    document.dispatchEvent(new Event("log-evidence-close"));
  }
  async function inspect(id, button, offset = 0) {
    opener = button || opener;
    selected = id;
    rawOffset = offset;
    panel.hidden = false;
    document.body.classList.add("detail-modal");
    document.querySelector(".app-shell").inert = true;
    document.getElementById("log-detail-title").focus();
    document.getElementById("log-detail-status").textContent =
      t("Loading source evidence…");
    document.getElementById("log-raw").textContent = "";
    const requested = id;
    try {
      const p = new URLSearchParams(applied);
      p.set("scope_token", scope);
      p.set("raw_offset", String(offset));
      const data = await api("/api/v1/logs/" + id + "?" + p);
      if (selected !== requested || panel.hidden) return;
      document.getElementById("log-detail-title").textContent = t("Event {0}", id);
      document.getElementById("log-raw").textContent = data.raw.text;
      document.getElementById("log-provenance").textContent = JSON.stringify(
        {
          event: data.event,
          ground_truth_label: data.ground_truth_label,
          provenance: data.provenance,
        },
        null,
        2,
      );
      document.getElementById("log-detail-status").textContent =
        t("Actual imported raw line · redacted");
      const next = document.getElementById("log-raw-next");
      next.hidden = data.raw.next_offset === null;
      next.onclick = () => inspect(id, null, data.raw.next_offset);
      if (!offset)
        document.dispatchEvent(new CustomEvent("logsense:log-inspected", { detail: { id, event: data.event } }));
    } catch (e) {
      document.getElementById("log-detail-status").textContent = e.message;
    }
  }
  async function load(next = null, reset = true) {
    controller?.abort();
    controller = new AbortController();
    const ticket = ++sequence;
    const p = reset ? query() : new URLSearchParams(applied);
    if (!reset && scope) p.set("scope_token", scope);
    if (next) p.set("cursor", next);
    form.setAttribute("aria-busy", "true");
    say(t("Loading MySQL page… Previous results are retained."));
    try {
      const data = await api("/api/v1/logs?" + p, {
        signal: controller.signal,
      });
      if (ticket !== sequence) return;
      const pinned = data.scope_token;
      p.delete("cursor");
      p.set("scope_token", pinned);
      const volumeParams = new URLSearchParams(p);
      const chartWidth = document.querySelector(".timeline-scroll").clientWidth;
      volumeParams.set(
        "bins",
        String(Math.max(20, Math.min(80, Math.floor((chartWidth - 150) / 29)))),
      );
      const volume = await api("/api/v1/logs/timeline?" + volumeParams, {
        signal: controller.signal,
      });
      if (ticket !== sequence) return;
      if (data.count !== volume.count)
        throw new Error(t("Scope mismatch; retry the query."));
      scope = pinned;
      applied = new URLSearchParams(p);
      investigationLink.href = "/?" + new URLSearchParams({
        source: "db-" + applied.get("dataset_id"),
      });
      investigationNav.hidden = false;
      if (reset) {
        historyCursors = [null];
        index = 0;
      }
      cursor = data.next_cursor;
      const body = document.getElementById("log-rows");
      body.replaceChildren();
      for (const row of data.items) {
        const tr = document.createElement("tr");
        for (const value of [
          row.timestamp + " · " + row.id,
          row.severity || "Unavailable",
          row.message,
          (row.host || "Unavailable") + " / " + (row.service || "Unavailable"),
        ]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
        const td = document.createElement("td"),
          button = document.createElement("button");
        button.textContent = t("Inspect →");
        button.setAttribute("aria-label", t("Inspect log {0}", row.id));
        button.onclick = () => inspect(row.id, button);
        td.append(button);
        tr.append(td);
        body.append(tr);
      }
      if (!data.items.length) {
        const tr = document.createElement("tr"),
          td = document.createElement("td");
        td.colSpan = 5;
        td.textContent = t("No imported events match this scope.");
        tr.append(td);
        body.append(tr);
      }
      document.getElementById("logs-count").textContent = data.count;
      document.getElementById("logs-snapshot").textContent =
        t("Input revision {0} · bounded snapshot · UTC [start,end)", data.input_revision);
      document.getElementById("log-page").textContent =
        t("Page {0} · {1} displayed", index + 1, data.items.length);
      document.getElementById("log-next").disabled = !cursor;
      document.getElementById("log-previous").disabled = index === 0;
      const exportLink = document.getElementById("logs-export");
      exportLink.href = "/api/v1/logs/export?" + applied;
      exportLink.setAttribute("aria-disabled", String(data.count > 100000));
      exportLink.onclick = (e) => {
        if (data.count > 100000) {
          e.preventDefault();
          say(t("Narrow the scope to 100,000 parsed events before exporting."));
        }
      };
      const bins = document.getElementById("log-bins");
      bins.style.setProperty("--bins", String(volume.bins.length));
      bins.classList.add("level-bins");
      bins.replaceChildren();
      const tallest = Math.max(1, ...volume.bins.map((cell) => cell.event_count));
      // Bottom to top: routine levels first, the most severe on top of each bar.
      const levelOrder = ["INFO", "UNKNOWN", "WARNING", "ERROR", "SEVERE", "FAILURE", "FATAL"];
      const rank = (level) => (levelOrder.includes(level) ? levelOrder.indexOf(level) : 1);
      for (const cell of volume.bins) {
        const b = document.createElement("button");
        b.className = "level-bar";
        const parts = Object.entries(cell.levels || {}).sort(([a], [b2]) => rank(a) - rank(b2));
        for (const [level, count] of parts) {
          const segment = document.createElement("span");
          segment.className = "level-segment level-" + level.toLowerCase();
          segment.style.height = (100 * count / tallest).toFixed(2) + "%";
          b.append(segment);
        }
        const breakdown = parts.map(([level, count]) => level + " " + count).join(", ");
        b.title =
          tn(cell.event_count, "{0} — {1} · {2} event · coverage unknown", "{0} — {1} · {2} events · coverage unknown", cell.start, cell.end, cell.event_count) +
          (breakdown ? " · " + breakdown : "");
        b.setAttribute("aria-label", b.title);
        b.onclick = () => {
          form.elements.start_time.value = cell.start.replace("Z", "");
          form.elements.end_time.value = cell.end.replace("Z", "");
          load();
        };
        bins.append(b);
      }
      document.dispatchEvent(new CustomEvent("logsense:logs-loaded", {
        detail: { params: new URLSearchParams(applied), scope, count: data.count },
      }));
      say(
        t("MySQL ready · {0} parsed events · no raw-result download beyond this page", data.count),
      );
      const url = new URL(location.href);
      url.search = "workspace=logs&" + query();
      history.replaceState({}, "", url);
    } catch (e) {
      if (e.name !== "AbortError")
        say(t("Query failed: {0}. Previous results retained.", e.message));
    } finally {
      if (ticket === sequence) form.setAttribute("aria-busy", "false");
    }
  }
  async function initialize() {
    const auth = await api("/api/v1/auth/me");
    csrf = auth.csrf_token;
    document.dispatchEvent(new CustomEvent("logsense:auth-changed", { detail: auth }));
    const data = await api("/api/v1/logs/datasets");
    const select = form.elements.dataset_id;
    select.replaceChildren();
    for (const d of data.datasets) {
      const o = new Option(d.name + " · " + d.data_mode, d.id);
      o.dataset.start = d.start_time || "";
      o.dataset.end = d.end_time || "";
      select.add(o);
    }
    document.getElementById("login-panel").hidden = true;
    document.getElementById("log-workspace").hidden = !select.options.length;
    document.getElementById("logs-logout").hidden = false;
    if (!select.options.length) {
      say(t("No dataset access has been granted."));
      return;
    }
    const params = new URLSearchParams(location.search);
    for (const name of ["dataset_id", "host", "severity", "q", "query", "sort", "limit"])
      if (params.has(name)) form.elements[name].value = params.get(name);
    chooseRange();
    for (const name of ["start_time", "end_time"])
      if (params.has(name))
        form.elements[name].value = params.get(name).replace("Z", "");
    await load();
  }
  function chooseRange() {
    const o = form.elements.dataset_id.selectedOptions[0];
    baseRange = [
      o?.dataset.start || "2005-01-01T00:00:00Z",
      o?.dataset.end || "2005-01-02T00:00:00Z",
    ];
    form.elements.start_time.value = baseRange[0].replace("Z", "");
    form.elements.end_time.value = baseRange[1].replace("Z", "");
  }
  form.onsubmit = (e) => {
    e.preventDefault();
    load();
  };
  form.elements.dataset_id.onchange = chooseRange;
  document.getElementById("logs-reset-time").onclick = () => {
    chooseRange();
    load();
  };
  document.getElementById("log-next").onclick = () => {
    index++;
    historyCursors[index] = cursor;
    load(cursor, false);
  };
  document.getElementById("log-previous").onclick = () => {
    index--;
    load(historyCursors[index], false);
  };
  document.getElementById("log-close").onclick = detailClose;
  document.addEventListener("keydown", (e) => {
    if (panel.hidden) return;
    if (e.key === "Escape") {
      e.preventDefault();
      selected = null;
      detailClose();
    }
    if (e.key === "Tab") {
      const all = [...panel.querySelectorAll('button, [tabindex="0"]')].filter(
        (n) => !n.hidden,
      );
      if (e.shiftKey && document.activeElement === all[0]) {
        e.preventDefault();
        all.at(-1).focus();
      } else if (!e.shiftKey && document.activeElement === all.at(-1)) {
        e.preventDefault();
        all[0].focus();
      }
    }
  });
  document.getElementById("login-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await api("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(new FormData(e.target))),
      });
      e.target.elements.password.value = "";
      await initialize();
    } catch (error) {
      say(error.message);
    }
  };
  document.getElementById("logs-logout").onclick = async () => {
    try {
      await api("/api/v1/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
      });
      document.dispatchEvent(new CustomEvent("logsense:auth-changed", { detail: null }));
      location.reload();
    } catch (e) {
      say(e.message);
    }
  };
  let datasetRefresh = 0;
  document.addEventListener("logsense:datasets-changed", async (event) => {
    const ticket = ++datasetRefresh;
    try {
      const data = await api("/api/v1/logs/datasets");
      if (ticket !== datasetRefresh) return;
      const select = form.elements.dataset_id;
      const prior = select.value;
      const currentQuery = query(), oldApplied = applied ? new URLSearchParams(applied) : null;
      oldApplied?.delete("scope_token");
      oldApplied?.delete("cursor");
      const pendingEdits = oldApplied && currentQuery.toString() !== oldApplied.toString();
      const utcValue = (value) => Date.parse(value.endsWith("Z") ? value : value + "Z");
      const followedFullRange = baseRange &&
        utcValue(form.elements.start_time.value) === utcValue(baseRange[0]) &&
        utcValue(form.elements.end_time.value) === utcValue(baseRange[1]);
      select.replaceChildren();
      for (const d of data.datasets) {
        const option = new Option(d.name + " · " + d.data_mode, d.id);
        option.dataset.start = d.start_time || "";
        option.dataset.end = d.end_time || "";
        select.add(option);
      }
      if (data.datasets.some((d) => String(d.id) === prior)) {
        select.value = prior;
        if (event.detail?.action === "import" && String(event.detail.dataset_id) === prior) {
          if (pendingEdits) {
            say(t("Import completed. Previous snapshot retained; Apply filters to refresh."));
          } else {
            if (followedFullRange) chooseRange();
            await load(); // New input revision requires a fresh bounded snapshot.
          }
        }
        return; // Metadata-only changes preserve filters/page/snapshot.
      }
      controller?.abort();
      ++sequence;
      applied = scope = cursor = selected = null;
      historyCursors = [null];
      index = 0;
      document.getElementById("log-rows").replaceChildren();
      document.getElementById("log-bins").replaceChildren();
      document.getElementById("logs-count").textContent = "0";
      document.getElementById("logs-snapshot").textContent = t("No selected snapshot");
      document.getElementById("log-page").textContent = t("No page");
      document.getElementById("log-next").disabled = true;
      document.getElementById("log-previous").disabled = true;
      const exportLink = document.getElementById("logs-export");
      exportLink.removeAttribute("href");
      exportLink.setAttribute("aria-disabled", "true");
      investigationNav.hidden = true;
      document.getElementById("log-workspace").hidden = !select.options.length;
      if (select.options.length) {
        chooseRange();
        await load();
      } else {
        const url = new URL(location.href);
        url.search = "workspace=logs";
        history.replaceState({}, "", url);
        say(t("No dataset access has been granted. Create a dataset or request a grant."));
      }
    } catch (error) {
      say(t("Dataset metadata changed; refreshing the selector failed: {0}", error.message));
    }
  });
  // Read by log-explorer.js (facets, patterns, insights, saved views, live mode).
  window.logsenseLogs = {
    form,
    csrf: () => csrf,
    applied: () => (applied ? new URLSearchParams(applied) : null),
    scope: () => scope,
    reload: () => load(),
    inspect: (id) => inspect(id, null),
    say,
  };
  initialize().catch(() => {
    document.dispatchEvent(new CustomEvent("logsense:auth-changed", { detail: null }));
    say(t("Sign in to access explicitly authorized MySQL datasets."));
  });
})();
