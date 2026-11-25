"use strict";

// Pipeline & jobs: job actions through the existing job and upload APIs, then reload the page.
(() => {
  const t = window.logsenseTranslate || ((message) => message);
  const panel = document.querySelector(".pipeline-actions");
  const detail = document.getElementById("job-detail");
  if (detail && location.hash === "#job-detail") detail.focus({ preventScroll: true });
  if (!panel) return;
  const status = document.getElementById("pipeline-action-status");
  const errors = {
    job_not_retryable: "This job cannot be retried in its current state.",
    worker_active: "A worker is still running this job.",
    idempotency_conflict: "This run was already requested with another configuration.",
    forbidden: "Your account cannot run jobs for this dataset.",
  };

  async function call(path, body, csrf) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(body ?? {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = data.error?.code;
      throw new Error(t(errors[code] || data.error?.message || "The request failed ({0}).", response.status));
    }
    return data;
  }

  panel.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    for (const item of panel.querySelectorAll("button")) item.disabled = true;
    status.textContent = t("Sending…");
    try {
      const auth = await fetch("/api/v1/auth/me").then((response) => response.json());
      const job = panel.dataset.job;
      let result;
      if (button.dataset.action === "retry") {
        result = await call(`/api/v1/detection/jobs/${job}/retry`, {}, auth.csrf_token);
      } else if (button.dataset.action === "rerun") {
        result = await call("/api/v1/detection/jobs", {
          dataset_id: Number(panel.dataset.dataset),
          idempotency_key: "rerun-" + job + "-" + crypto.randomUUID(),
          configuration: JSON.parse(button.dataset.configuration),
        }, auth.csrf_token);
      } else {
        result = await call(`/api/v1/uploads/${encodeURIComponent(button.dataset.upload)}/retry`, {}, auth.csrf_token);
      }
      const url = new URL(location.href);
      const queued = result.job_id ?? result.id;
      if (queued) url.searchParams.set("job", queued);
      url.hash = "job-detail";
      // A hash-only change would not reload; replace the address, then reload to show the new state.
      history.replaceState(null, "", url);
      location.reload();
    } catch (error) {
      status.textContent = error.message;
      for (const item of panel.querySelectorAll("button")) item.disabled = false;
    }
  });
})();
