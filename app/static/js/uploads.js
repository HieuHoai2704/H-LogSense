"use strict";
(() => {
  const t = window.logsenseTranslate;
  const panel = document.getElementById("upload-workspace");
  if (!panel) return;
  const form = document.getElementById("upload-form"),
    status = document.getElementById("upload-status"),
    refresh = document.getElementById("upload-refresh"),
    retry = document.getElementById("upload-retry"),
    progress = document.getElementById("upload-progress"),
    provenance = document.getElementById("upload-provenance");
  const LIMIT = 16 * 1024 * 1024, MAX_POLLS = 20;
  let user = null, csrf = null, authGeneration = 0, listSequence = 0,
    jobSequence = 0, current = null, notifiedUpload = null, timer = null, polls = 0, busy = false;
  const allowed = () => ["staff", "admin"].includes(user?.role);
  function say(text, focus = false) {
    status.textContent = text;
    if (focus) status.focus({ preventScroll: true });
  }
  function key() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    form.elements.idempotency_key.value = "ui-upload-" + [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
  }
  function stopPolling() {
    clearTimeout(timer);
    timer = null;
  }
  async function request(path, method = "GET", body = undefined) {
    const options = { method, headers: { Accept: "application/json" } };
    if (method !== "GET") options.headers["X-CSRF-Token"] = csrf;
    if (body instanceof FormData) options.body = body;
    else if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const response = await fetch(path, options);
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error(t("The import service could not return a status.")); }
    if (!response.ok) {
      const error = new Error(data.error?.message || data.error?.code || t("Import request failed."));
      error.fields = data.error?.fields;
      error.status = response.status;
      throw error;
    }
    return data;
  }
  async function postForm(data) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const token = await request("/api/v1/forms/csrf");
      data.set("csrf_token", token.csrf_token);
      try { return await request("/api/v1/uploads", "POST", data); }
      catch (error) {
        if (attempt === 0 && error.fields?.csrf_token) continue;
        throw error;
      }
    }
  }
  function setBusy(value) {
    busy = value;
    form.setAttribute("aria-busy", String(value));
    for (const element of form.elements) element.disabled = value || !allowed();
    refresh.disabled = value || !current;
    retry.disabled = value || !allowed();
  }
  async function datasets() {
    if (!allowed()) return;
    const ticket = ++listSequence, generation = authGeneration;
    const prior = form.elements.dataset_id.value;
    try {
      const data = await request("/api/v1/datasets?limit=100");
      if (ticket !== listSequence || generation !== authGeneration) return;
      const select = form.elements.dataset_id;
      select.replaceChildren();
      for (const item of data.items) {
        if (item.state === "archived") continue;
        select.add(new Option(item.name + " · " + item.data_mode, String(item.id)));
      }
      const active = document.querySelector('#log-filters [name="dataset_id"]')?.value;
      if ([...select.options].some(option => option.value === prior)) select.value = prior;
      else if ([...select.options].some(option => option.value === active)) select.value = active;
      if (!select.options.length) say(t("No active dataset grant is available. Register a dataset or request access."));
    } catch (error) {
      if (generation === authGeneration) say(t("Could not load granted targets: {0}", error.message));
    }
  }
  function render(data) {
    current = data;
    refresh.disabled = false;
    retry.hidden = !data.can_retry;
    progress.hidden = false;
    const total = Number(data.total_lines), processed = Number(data.processed_count || 0);
    if (total > 0) {
      progress.max = total;
      progress.value = Math.min(processed, total);
    } else {
      progress.removeAttribute("value");
    }
    if (data.state === "completed") {
      if (!(total > 0)) { progress.max = 1; progress.value = 1; }
      say(t("Import completed · dataset {0} · {1} parsed events · {2} malformed rows. Inspect this target in Log Explorer.", data.dataset_id, data.parsed_events, data.malformed_rows));
    } else if (data.state === "failed") {
      say(t("Import failed · {0}. Committed progress is retained. Inspect the source and retry when appropriate.", data.error_code || t("operation_failed")));
    } else {
      say(t("Import {0} · {1} processed lines{2}. Waiting for the ingestion worker; queued work is not completed data.", t(data.state), processed, total > 0 ? " / " + total : ""));
    }
    provenance.hidden = !data.provenance;
    provenance.textContent = data.provenance ? JSON.stringify(data.provenance, null, 2) : "";
  }
  async function check(automatic = false) {
    if (!current || !allowed()) return;
    stopPolling();
    const id = current.upload_id, generation = authGeneration, ticket = ++jobSequence;
    try {
      const data = await request("/api/v1/uploads/" + id);
      if (generation !== authGeneration || ticket !== jobSequence || current?.upload_id !== id) return;
      render(data);
      if (data.state === "completed" && notifiedUpload !== data.upload_id) {
        notifiedUpload = data.upload_id;
        document.dispatchEvent(new CustomEvent("logsense:datasets-changed", {
          detail: { action: "import", dataset_id: data.dataset_id },
        }));
      }
      if (["queued", "running"].includes(data.state)) {
        if (automatic && polls < MAX_POLLS) {
          polls++;
          timer = setTimeout(() => check(true), 1500);
        } else if (automatic) {
          say(t("{0} Automatic refresh paused; use Refresh import status.", (status.textContent)));
        }
      }
    } catch (error) {
      if (generation === authGeneration && ticket === jobSequence)
        say(t("Status query failed: {0}. Use Refresh import status to retry.", error.message));
    }
  }
  function auth(detail) {
    ++authGeneration;
    ++listSequence;
    ++jobSequence;
    stopPolling();
    user = detail?.user || null;
    csrf = detail?.csrf_token || null;
    current = null;
    notifiedUpload = null;
    panel.hidden = !allowed();
    form.reset();
    form.elements.dataset_id.replaceChildren();
    progress.hidden = provenance.hidden = retry.hidden = true;
    provenance.textContent = "";
    key();
    setBusy(false);
    refresh.disabled = true;
    if (allowed()) datasets();
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (busy || !allowed()) return;
    const file = form.elements.file.files[0];
    if (!file || file.size === 0 || file.size > LIMIT) {
      say(t("Choose a nonempty BGL file no larger than 16 MiB."), true);
      return;
    }
    if (!/\.(txt|log|csv)$/i.test(file.name)) {
      say(t("Choose a TXT, LOG or CSV source file."), true);
      return;
    }
    const data = new FormData(form), generation = authGeneration;
    stopPolling();
    setBusy(true);
    say(t("Uploading source for validation… This does not run ingestion inside the request."));
    try {
      const queued = await postForm(data);
      if (generation !== authGeneration) return;
      current = queued;
      render(queued);
      polls = 0;
      await check(true);
    } catch (error) {
      if (generation === authGeneration) say(t("Upload rejected: {0}", error.message), true);
    } finally {
      if (generation === authGeneration) setBusy(false);
    }
  });
  function newSelection() {
    ++jobSequence;
    stopPolling();
    current = null;
    progress.hidden = provenance.hidden = retry.hidden = true;
    provenance.textContent = "";
    refresh.disabled = true;
    key();
    say(t("Source selection changed. No new import has been queued."));
  }
  form.elements.file.addEventListener("change", newSelection);
  form.elements.dataset_id.addEventListener("change", newSelection);
  refresh.addEventListener("click", () => { polls = 0; check(false); });
  retry.addEventListener("click", async () => {
    if (!current || busy || !allowed()) return;
    const generation = authGeneration;
    setBusy(true);
    try {
      current = await request("/api/v1/uploads/" + current.upload_id + "/retry", "POST", {});
      if (generation !== authGeneration) return;
      render(current);
      polls = 0;
      await check(true);
    } catch (error) {
      if (generation === authGeneration) say(t("Retry rejected: {0}", error.message), true);
    } finally {
      if (generation === authGeneration) setBusy(false);
    }
  });
  document.addEventListener("logsense:auth-changed", (event) => auth(event.detail));
  document.addEventListener("logsense:datasets-changed", () => datasets());
  const generation = authGeneration;
  request("/api/v1/auth/me").then(detail => {
    if (generation === authGeneration) auth(detail);
  }).catch(() => {
    if (generation === authGeneration) auth(null);
  });
})();
