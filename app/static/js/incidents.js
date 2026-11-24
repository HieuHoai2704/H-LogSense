"use strict";
(() => {
  const t = window.logsenseTranslate;
  const tn = window.logsenseTranslatePlural;
  const form = document.getElementById("log-filters"),
    panel = document.getElementById("incident-workspace"),
    status = document.getElementById("incident-status");
  let csrf = null,
    role = null,
    job = null,
    selected = null,
    before = null,
    alertOpener = null,
    validatedModel = null;
  const dataset = () => Number(form.elements.dataset_id.value);
  async function request(path, method = "GET", body = null) {
    const options = { method, headers: { "Content-Type": "application/json" } };
    if (method !== "GET") options.headers["X-CSRF-Token"] = csrf;
    if (body !== null) options.body = JSON.stringify(body);
    const r = await fetch(path, options),
      data = await r.json();
    if (!r.ok)
      throw new Error(
        data.error?.message || data.error?.code || t("Operation failed"),
      );
    return data;
  }
  async function refresh(next = false) {
    try {
      if (!csrf) {
        const auth = await request("/api/v1/auth/me");
        csrf = auth.csrf_token;
        role = auth.user.role;
      }
      panel.hidden = false;
      const data = await request(
        "/api/v1/alerts?dataset_id=" +
          dataset() +
          (next && before ? "&before_id=" + before : ""),
      );
      before = data.next_before_id;
      document.getElementById("more-alerts").disabled = !before;
      const rows = document.getElementById("incident-rows");
      rows.replaceChildren();
      for (const alert of data.items) {
        const tr = document.createElement("tr");
        for (const value of [
          alert.id + " / DB-" + alert.anomaly_id,
          alert.status,
          alert.assigned_to ?? "Unassigned",
        ]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
        const td = document.createElement("td"),
          edit = document.createElement("button"),
          inspect = document.createElement("button");
        edit.textContent = t("Manage {0}", alert.id);
        edit.onclick = () => selectAlert(alert.id);
        inspect.textContent = t("Inspect evidence");
        inspect.onclick = () => evidence(alert, inspect);
        td.append(edit, inspect);
        tr.append(td);
        rows.append(tr);
      }
      if (!data.items.length) {
        const tr = document.createElement("tr"),
          td = document.createElement("td");
        td.colSpan = 4;
        td.textContent = t("No alerts generated for this dataset.");
        tr.append(td);
        rows.append(tr);
      }
      for (const id of ["run-window-rule", "run-window-if"])
        document.getElementById(id).disabled = !["staff", "admin"].includes(role);
      const models = await request("/api/v1/detection/models");
      validatedModel = models.items[0] || null;
      const validatedButton = document.getElementById("run-validated-if");
      const observedEnd = form.elements.dataset_id.selectedOptions[0]?.dataset.end;
      const compatible = validatedModel && observedEnd && Date.parse(observedEnd) > Date.parse(validatedModel.inference_start_utc);
      validatedButton.disabled = !["staff", "admin"].includes(role) || !compatible;
      document.getElementById("validated-if-note").textContent = validatedModel ? (compatible
        ? t("{0} · scores closed windows after {1} · frozen validation threshold; no retraining on this dataset.", validatedModel.name, validatedModel.inference_start_utc)
        : t("{0} · scores closed windows after {1} · selected data is earlier/empty; this profile is unavailable.", validatedModel.name, validatedModel.inference_start_utc)) : t("Validated model artifact unavailable. Existing baseline jobs remain available.");
      for (const element of document.getElementById("alert-rule-form").elements)
        element.disabled = !["staff", "admin"].includes(role);
      status.textContent =
        t("Alert page ready · explicit dataset permission · cooldown decisions are retained.");
    } catch (error) {
      status.textContent = error.message;
    }
  }
  async function selectAlert(id) {
    try {
      const data = await request("/api/v1/alerts/" + id);
      selected = id;
      const edit = document.getElementById("incident-edit");
      edit.hidden = false;
      edit.elements.status.value = data.status;
      edit.elements.assigned_to.value = data.assigned_to || "";
      edit.elements.note.value = "";
      for (const element of edit.elements) element.disabled = !["staff", "admin"].includes(role);
      document.getElementById("incident-history").textContent = JSON.stringify(
        data.history,
        null,
        2,
      );
    } catch (e) {
      status.textContent = e.message;
    }
  }
  async function evidence(alert, opener) {
    alertOpener = opener;
    const drawer = document.getElementById("log-detail");
    drawer.hidden = false;
    document.querySelector(".app-shell").inert = true;
    document.body.classList.add("detail-modal");
    document.getElementById("log-detail-title").textContent =
      t("DB-{0}", alert.anomaly_id);
    document.getElementById("log-detail-title").focus();
    document.getElementById("log-raw").textContent = "";
    document.getElementById("log-raw-next").hidden = true;
    try {
      const data = await request(
        "/api/v1/anomalies/DB-" +
          alert.anomaly_id +
          "/evidence?source=db-" +
          dataset() +
          "&run_id=" +
          alert.run_id,
      );
      document.getElementById("log-raw").textContent = data.raw_event.page.text;
      document.getElementById("log-provenance").textContent = JSON.stringify(
        {
          anomaly: data.anomaly,
          provenance: data.raw_event.provenance,
          detector: data.detector_evidence,
        },
        null,
        2,
      );
      document.getElementById("log-detail-status").textContent =
        t("Actual anomaly evidence · first redacted raw chunk · not a confirmed cause");
    } catch (e) {
      document.getElementById("log-detail-status").textContent = e.message;
    }
    const close = document.getElementById("log-close");
    const restore = () => {
      opener.focus({ preventScroll: true });
      close.removeEventListener("click", restore);
    };
    close.addEventListener("click", restore);
  }
  async function queue(detector, model = null) {
    try {
      const response = await request("/api/v1/detection/jobs", "POST", {
        dataset_id: dataset(),
        idempotency_key: crypto.randomUUID(),
        configuration: model ? { detector, model_id: model.id } : { detector, window_seconds: 300, seed: 42 },
      });
      job = response.job_id;
      document.getElementById("check-analysis-job").disabled = false;
      status.textContent =
        t("Job {0} queued. Run the separate local worker to process it.", job);
    } catch (e) {
      status.textContent = e.message;
    }
  }
  document.getElementById("refresh-alerts").onclick = () => refresh();
  document.getElementById("more-alerts").onclick = () => refresh(true);
  document.getElementById("run-window-rule").onclick = () => queue("rule");
  document.getElementById("run-window-if").onclick = () =>
    queue("isolation_forest");
  document.getElementById("run-validated-if").onclick = () => {
    if (validatedModel) queue("isolation_forest", validatedModel);
  };
  document.addEventListener("logsense:datasets-changed", (event) => {
    if (event.detail?.action === "import") refresh();
  });
  document.getElementById("check-analysis-job").onclick = async () => {
    try {
      const data = await request("/api/v1/detection/jobs/" + job);
      status.textContent =
        tn(data.processed_count, "Job {0} · {1} · {2} unit · {3}", "Job {0} · {1} · {2} units · {3}", job, data.state, data.processed_count, JSON.stringify(data.result));
    } catch (e) {
      status.textContent = e.message;
    }
  };
  document.getElementById("alert-rule-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target));
    body.dataset_id = dataset();
    body.cooldown_seconds = Number(body.cooldown_seconds);
    if (body.detector_id) body.detector_id = Number(body.detector_id);
    else delete body.detector_id;
    if (!body.host) delete body.host;
    try {
      const data = await request("/api/v1/alert-rules", "POST", body);
      status.textContent =
        t("Created rule {0}. New completed analysis jobs apply it.", data.rule_id);
    } catch (error) {
      status.textContent = error.message;
    }
  };
  document.getElementById("incident-edit").onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target));
    if (body.assigned_to) body.assigned_to = Number(body.assigned_to);
    else delete body.assigned_to;
    if (!body.note) delete body.note;
    try {
      await request("/api/v1/alerts/" + selected, "PATCH", body);
      await selectAlert(selected);
      await refresh();
    } catch (error) {
      status.textContent = error.message;
    }
  };
  document.addEventListener("log-evidence-close", () => {
    if (alertOpener) {
      alertOpener.focus({ preventScroll: true });
      alertOpener = null;
    }
  });
  form.elements.dataset_id.addEventListener("change", () => {
    selected = null;
    before = null;
    document.getElementById("incident-edit").hidden = true;
    document.getElementById("incident-rows").replaceChildren();
    refresh();
  });
  const observer = new MutationObserver(() => {
    if (!document.getElementById("log-workspace").hidden) {
      panel.hidden = false;
      refresh();
      observer.disconnect();
    }
  });
  observer.observe(document.getElementById("log-workspace"), {
    attributes: true,
    attributeFilter: ["hidden"],
  });
})();
