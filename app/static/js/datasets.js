"use strict";
(() => {
  const t = window.logsenseTranslate;
  const panel = document.getElementById("dataset-workspace");
  if (!panel) return;
  const status = document.getElementById("dataset-status"),
    rows = document.getElementById("dataset-rows"),
    create = document.getElementById("dataset-create"),
    edit = document.getElementById("dataset-edit"),
    search = document.getElementById("dataset-search"),
    previous = document.getElementById("dataset-previous"),
    next = document.getElementById("dataset-next"),
    confirmation = document.getElementById("dataset-delete-confirm");
  let user = null,
    csrf = null,
    authGeneration = 0,
    querySequence = 0,
    editorSequence = 0,
    controller = null,
    pageCursors = [null],
    pageIndex = 0,
    nextCursor = null,
    appliedSearch = "",
    selected = null,
    pendingDelete = null,
    mutationPending = false;

  const canManage = () => ["manager", "admin"].includes(user?.role);
  const canDelete = () => user?.role === "admin";
  function say(message, focus = false) {
    status.textContent = message;
    if (focus) status.focus({ preventScroll: true });
  }
  async function request(path, { method = "GET", body, signal } = {}) {
    const options = { method, signal, headers: { Accept: "application/json" } };
    if (method !== "GET") {
      options.headers["X-CSRF-Token"] = csrf;
      if (!(body instanceof FormData)) options.headers["Content-Type"] = "application/json";
    }
    if (body !== undefined) options.body = body instanceof FormData ? body : JSON.stringify(body);
    const response = await fetch(path, options);
    if (response.status === 204) return null;
    let data;
    try {
      data = await response.json();
    } catch (_) {
      throw new Error(t("The server could not return dataset metadata."));
    }
    if (!response.ok) {
      const error = new Error(data.error?.message || data.error?.code || t("Dataset operation failed."));
      error.status = response.status;
      error.fields = data.error?.fields;
      throw error;
    }
    return data;
  }
  async function formRequest(path, data) {
    // Request a current signed token for every submission. A rejected expired
    // token is retried once; business operations are never blindly retried.
    for (let attempt = 0; attempt < 2; attempt++) {
      const token = await request("/api/v1/forms/csrf");
      data.set("csrf_token", token.csrf_token);
      try {
        return await request(path, { method: "POST", body: data });
      } catch (error) {
        if (attempt === 0 && error.fields?.csrf_token) continue;
        throw error;
      }
    }
  }
  function closeEditors() {
    ++editorSequence;
    selected = null;
    pendingDelete = null;
    edit.hidden = true;
    confirmation.hidden = true;
  }
  function updatePermissions() {
    document.getElementById("dataset-create-panel").hidden = !canManage();
    document.getElementById("dataset-delete-note").hidden = !canDelete();
    for (const control of create.elements) control.disabled = !canManage() || mutationPending;
    for (const control of edit.elements) control.disabled = !canManage() || mutationPending;
    document.getElementById("dataset-delete-submit").disabled = !canDelete() || mutationPending;
  }
  function busy(value) {
    mutationPending = value;
    create.setAttribute("aria-busy", String(value));
    edit.setAttribute("aria-busy", String(value));
    updatePermissions();
    for (const button of rows.querySelectorAll("button")) button.disabled = value;
  }
  function changed(action, datasetId) {
    document.dispatchEvent(new CustomEvent("logsense:datasets-changed", {
      detail: { action, dataset_id: datasetId },
    }));
  }
  function render(items) {
    rows.replaceChildren();
    for (const item of items) {
      const tr = document.createElement("tr");
      tr.dataset.datasetId = String(item.id);
      const name = document.createElement("td"), label = document.createElement("strong"),
        key = document.createElement("small");
      label.textContent = item.name;
      key.textContent = item.dataset_key + " · " + item.id;
      name.append(label, key);
      tr.append(name);
      for (const value of [
        item.source_name + " · " + item.source_id,
        t(item.data_mode),
        t("{0} · revision {1}", t(item.state), item.input_revision),
      ]) {
        const td = document.createElement("td");
        td.textContent = value;
        tr.append(td);
      }
      const actions = document.createElement("td");
      if (canManage()) {
        const rename = document.createElement("button");
        rename.type = "button";
        rename.textContent = t("Rename");
        rename.setAttribute("aria-label", t("Rename dataset {0}", item.name));
        rename.addEventListener("click", () => openEditor(item.id));
        actions.append(rename);
      }
      if (canDelete() && item.input_revision === 0 && ["registered", "archived"].includes(item.state)) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = t("Delete");
        remove.setAttribute("aria-label", t("Delete empty dataset {0}", item.name));
        remove.addEventListener("click", () => {
          closeEditors();
          pendingDelete = item;
          document.getElementById("dataset-delete-message").textContent =
            t("Delete the empty dataset \"{0}\"? This cannot be undone. Imported data prevents deletion.", item.name);
          confirmation.hidden = false;
          document.getElementById("dataset-delete-cancel").focus();
        });
        actions.append(remove);
      } else if (canDelete()) {
        const protectedData = document.createElement("span");
        protectedData.textContent = t("Imported data protected");
        actions.append(protectedData);
      }
      if (!actions.childElementCount) actions.textContent = t("Read only");
      tr.append(actions);
      rows.append(tr);
    }
    if (!items.length) {
      const tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = canManage() ? t("No granted datasets match. Register a dataset below or adjust the search.") : t("No granted datasets match. Adjust the search or request a dataset grant.");
      tr.append(td);
      rows.append(tr);
    }
  }
  async function loadPage(cursor = null, targetPage = 0, filter = appliedSearch) {
    if (!user) return false;
    controller?.abort();
    controller = new AbortController();
    const ticket = ++querySequence;
    panel.setAttribute("aria-busy", "true");
    previous.disabled = next.disabled = true;
    say(t("Loading granted dataset metadata… Previous rows are retained."));
    const params = new URLSearchParams({ limit: "50" });
    if (filter) params.set("q", filter);
    if (cursor !== null) params.set("after_id", String(cursor));
    try {
      const data = await request("/api/v1/datasets?" + params, { signal: controller.signal });
      if (ticket !== querySequence || !user) return false;
      if (!Array.isArray(data.items)) throw new Error(t("Dataset metadata is unavailable."));
      if (targetPage === 0) pageCursors = [null];
      else pageCursors[targetPage] = cursor;
      pageIndex = targetPage;
      appliedSearch = filter;
      nextCursor = data.next_after_id;
      render(data.items);
      document.getElementById("dataset-page").textContent =
        t("Page {0} · {1} shown · your granted datasets", pageIndex + 1, data.items.length);
      say(t("Dataset metadata ready · only explicitly granted datasets are listed."));
      return true;
    } catch (error) {
      if (error.status === 403 && ticket === querySequence) {
        setAuth(null);
        return false;
      }
      if (error.name !== "AbortError" && ticket === querySequence)
        say(t("Dataset query failed: {0} Previous rows retained.", error.message));
      return false;
    } finally {
      if (ticket === querySequence) {
        panel.setAttribute("aria-busy", "false");
        previous.disabled = pageIndex === 0;
        next.disabled = nextCursor === null || nextCursor === undefined;
      }
    }
  }
  async function openEditor(id) {
    closeEditors();
    const ticket = editorSequence, generation = authGeneration;
    say(t("Loading dataset details…"));
    try {
      const data = await request("/api/v1/datasets/" + id);
      if (ticket !== editorSequence || generation !== authGeneration || !canManage()) return;
      selected = data.dataset;
      document.getElementById("dataset-edit-title").textContent = t("Rename {0}", selected.dataset_key);
      edit.elements.name.value = selected.name;
      edit.hidden = false;
      updatePermissions();
      edit.elements.name.focus();
      say(t("Only the display name is editable; source, key and provenance stay fixed."));
    } catch (error) {
      if (ticket === editorSequence) say(error.message, true);
    }
  }
  function setAuth(detail) {
    ++authGeneration;
    ++querySequence;
    controller?.abort();
    closeEditors();
    user = detail?.user || null;
    csrf = detail?.csrf_token || null;
    search.reset();
    appliedSearch = "";
    pageCursors = [null];
    pageIndex = 0;
    nextCursor = null;
    panel.hidden = !user;
    panel.setAttribute("aria-busy", "false");
    mutationPending = false;
    updatePermissions();
    if (!user) {
      rows.replaceChildren();
      create.reset();
      document.getElementById("dataset-page").textContent = "";
      return;
    }
    loadPage(null, 0, "");
  }

  create.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (mutationPending || !canManage()) return;
    const data = new FormData(create), key = create.elements.dataset_key.value;
    const generation = authGeneration;
    busy(true);
    try {
      const result = await formRequest("/forms/datasets", data);
      if (generation !== authGeneration) return;
      create.reset();
      search.elements.q.value = key;
      await loadPage(null, 0, key);
      changed("create", result.dataset.id);
      say(t("Dataset registered. No log data has been uploaded or imported."));
    } catch (error) {
      if (generation === authGeneration) say(error.message, true);
    } finally {
      if (generation === authGeneration) busy(false);
    }
  });
  edit.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selected || mutationPending || !canManage()) return;
    const id = selected.id, generation = authGeneration, data = new FormData(edit);
    busy(true);
    try {
      await formRequest("/forms/datasets/" + id + "/rename", data);
      if (generation !== authGeneration) return;
      closeEditors();
      await loadPage(pageCursors[pageIndex], pageIndex);
      changed("rename", id);
      say(t("Dataset name saved."));
    } catch (error) {
      if (generation === authGeneration) say(error.message, true);
    } finally {
      if (generation === authGeneration) busy(false);
    }
  });
  document.getElementById("dataset-delete-submit").addEventListener("click", async () => {
    if (!pendingDelete || mutationPending || !canDelete()) return;
    const id = pendingDelete.id, generation = authGeneration;
    const data = new FormData();
    data.set("confirmation", "y");
    busy(true);
    try {
      await formRequest("/forms/datasets/" + id + "/delete", data);
      if (generation !== authGeneration) return;
      closeEditors();
      await loadPage(null, 0);
      changed("delete", id);
      say(t("Empty dataset metadata deleted. Imported records were not deleted."));
    } catch (error) {
      if (generation === authGeneration) {
        confirmation.hidden = true;
        pendingDelete = null;
        say(error.message, true);
      }
    } finally {
      if (generation === authGeneration) busy(false);
    }
  });
  document.getElementById("dataset-edit-cancel").addEventListener("click", closeEditors);
  document.getElementById("dataset-delete-cancel").addEventListener("click", closeEditors);
  document.getElementById("dataset-refresh").addEventListener("click", () => loadPage(null, 0));
  search.addEventListener("submit", (event) => {
    event.preventDefault();
    closeEditors();
    loadPage(null, 0, search.elements.q.value.trim());
  });
  previous.addEventListener("click", () => loadPage(pageCursors[pageIndex - 1], pageIndex - 1));
  next.addEventListener("click", () => loadPage(nextCursor, pageIndex + 1));
  document.addEventListener("logsense:auth-changed", (event) => setAuth(event.detail));
  const generation = authGeneration;
  request("/api/v1/auth/me").then((detail) => {
    if (generation === authGeneration) setAuth(detail);
  }).catch(() => {
    if (generation === authGeneration) setAuth(null);
  });
})();
