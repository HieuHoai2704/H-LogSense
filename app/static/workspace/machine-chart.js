"use strict";

const workbenchGpu = {
  devices(row) {
    if (Array.isArray(row.gpu) && row.gpu.length) return row.gpu;
    if (![row.gpu_percent, row.vram_used_mib, row.vram_total_mib].some(Number.isFinite)) return [];
    return [{ percent: row.gpu_percent, vram_used_mib: row.vram_used_mib, vram_total_mib: row.vram_total_mib }];
  },
  key(device) {
    return device.uuid ? "uuid:" + device.uuid : Number.isInteger(device.index) ? "index:" + device.index : "legacy";
  },
  reading(row, key) {
    return this.devices(row).find((device) => this.key(device) === key);
  },
};

window.createMachineChart = ({ onPin, onDevice }) => {
  const $ = (id) => document.getElementById(id);
  const root = $("machine-chart");
  const graph = $("machine-trend");
  const svg = graph.querySelector("svg");
  const controls = [...root.querySelectorAll("[data-resource]")];
  const latest = $("machine-latest");
  const deviceSelect = $("machine-device");
  let selectedGpu = null;
  let deviceOptions = "";
  let rows = [];
  const tr = window.logsenseTranslate;
  const locale = document.documentElement.lang;
  const decimal = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  const time = new Intl.DateTimeFormat(locale, { timeStyle: "medium", hourCycle: "h23" });
  const fullTime = new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "medium", hourCycle: "h23" });
  const percent = (value) => value === null ? "—" : decimal.format(value) + "%";
  const resources = {
    cpu: { label: "CPU", title: "CPU utilization", value: (row) => row.cpu_percent },
    ram: { label: "RAM", title: "System memory", value: (row) => row.ram_percent,
      memory: (row) => capacity(row.ram_used_bytes, row.ram_total_bytes, 1024 ** 3) },
    gpu: { label: "GPU", title: "GPU utilization", value: (_, gpu) => gpu?.percent },
    vram: { label: "VRAM", title: "GPU memory", value: (_, gpu) => gpu?.vram_total_mib > 0 &&
      Number.isFinite(gpu.vram_used_mib) ? 100 * gpu.vram_used_mib / gpu.vram_total_mib : null,
      memory: (_, gpu) => capacity(gpu?.vram_used_mib, gpu?.vram_total_mib, 1024) },
  };
  const sources = { host: "Local machine", file: "Project metrics file", run: "Selected run", attached: "Attached process", demo: "Synthetic sample" };
  let resource = "cpu";
  let source = null;
  let pid = null;
  let samples = [];
  let pinned = null;
  let hovered = null;

  function capacity(used, total, divisor) {
    if (!Number.isFinite(used) || !Number.isFinite(total) || used < 0 || total <= 0 || used > total) return "";
    return decimal.format(used / divisor) + " / " + decimal.format(total / divisor) + " GiB";
  }

  function element(tag, attrs) {
    const node = document.createElementNS(svg.namespaceURI, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  }

  const guides = element("path", { class: "machine-guides", d:
    [0, 50, 100, 150, 200].map((y) => "M0 " + y + "H1000").join(" ") + " " +
    [125, 250, 375, 500, 625, 750, 875].map((x) => "M" + x + " 0V200").join(" ") });
  const history = element("g", {});
  const crosshair = element("line", { y1: 0, y2: 200, class: "machine-crosshair" });
  svg.append(guides, history, crosshair);

  function trace(key, target) {
    const segments = [];
    let segment = [];
    for (const sample of samples) {
      const value = sample.values[key];
      if (value === null) {
        if (segment.length) segments.push(segment);
        segment = [];
      } else segment.push([sample.x, 198 - 196 * value / 100]);
    }
    if (segment.length) segments.push(segment);
    const nodes = [];
    for (const points of segments) {
      const line = "M" + points.join(" L");
      if (points.length > 1) {
        nodes.push(element("path", { class: "machine-fill", d:
          line + " L" + points.at(-1)[0] + " 200 H" + points[0][0] + " Z" }));
      }
      nodes.push(element("path", { class: "machine-line", d: points.length > 1 ? line : line + " h.01" }));
    }
    target.replaceChildren(...nodes);
    return Boolean(segments.length);
  }

  function currentIndex() {
    const stamp = hovered ?? pinned;
    const index = stamp === null ? -1 : samples.findIndex((sample) => sample.stamp === stamp);
    return index < 0 ? samples.length - 1 : index;
  }

  function renderReading() {
    const index = currentIndex();
    const sample = samples[index];
    const metric = resources[resource];
    const value = percent(sample?.values[resource] ?? null);
    $("machine-value").textContent = value;
    $("machine-capacity").textContent = sample ? metric.memory?.(sample.row, sample.gpu) ?? "" : "";
    crosshair.style.display = sample && (hovered !== null || pinned !== null) ? "" : "none";
    if (sample) {
      crosshair.setAttribute("x1", sample.x);
      crosshair.setAttribute("x2", sample.x);
    }
    const caption = sample ? tr(hovered !== null ? "Inspecting sample" : pinned !== null ? "Pinned sample" : "Latest sample") +
      " · " + fullTime.format(sample.stamp) : "";
    $("machine-sample").textContent = caption;
    latest.hidden = pinned === null;
    graph.tabIndex = sample ? 0 : -1;
    graph.setAttribute("aria-disabled", String(!sample));
    graph.setAttribute("aria-valuemin", "1");
    graph.setAttribute("aria-valuemax", String(Math.max(1, samples.length)));
    graph.setAttribute("aria-valuenow", String(sample ? index + 1 : 1));
    graph.setAttribute("aria-valuetext", sample ? caption + " · " + value : tr("Waiting for machine samples"));
  }

  function renderDetail() {
    const metric = resources[resource];
    root.dataset.selectedResource = resource;
    $("machine-device-label").hidden = !selectedGpu || (resource !== "gpu" && resource !== "vram");
    deviceSelect.title = deviceSelect.selectedOptions[0]?.textContent || "";
    $("machine-title").textContent = metric.label;
    $("machine-source").textContent = tr(metric.title) + (source ? " · " + tr(sources[source]) : "") + (pid ? " PID " + pid : "");
    for (const button of controls) button.setAttribute("aria-pressed", String(button.dataset.resource === resource));
    const hasData = trace(resource, history);
    $("machine-empty").hidden = hasData;
    $("machine-empty").textContent = samples.length ? tr("No samples for this resource") : tr("Waiting for machine samples");
    const first = samples[0]?.stamp;
    const last = samples.at(-1)?.stamp;
    const formatter = samples.length > 1 && new Date(first).toDateString() !== new Date(last).toDateString() ? fullTime : time;
    for (const [id, stamp] of [["machine-first", first], ["machine-last", first === last ? undefined : last]]) {
      const tick = $(id);
      tick.textContent = stamp === undefined ? "" : formatter.format(stamp);
      if (stamp === undefined) tick.removeAttribute("datetime");
      else tick.dateTime = new Date(stamp).toISOString();
    }
    renderReading();
  }

  function pointAt(event) {
    const rect = graph.getBoundingClientRect();
    const x = 1000 * (event.clientX - rect.left) / rect.width;
    return samples.reduce((closest, candidate) =>
      Math.abs(candidate.x - x) < Math.abs(closest.x - x) ? candidate : closest);
  }

  for (const button of controls) {
    button.addEventListener("click", () => {
      resource = button.dataset.resource;
      hovered = null;
      renderDetail();
    });
  }
  graph.addEventListener("pointermove", (event) => {
    if (!samples.length || event.pointerType === "touch") return;
    const stamp = pointAt(event).stamp;
    if (hovered === stamp) return;
    hovered = stamp;
    renderReading();
  });
  graph.addEventListener("pointerleave", () => {
    hovered = null;
    renderReading();
  });
  graph.addEventListener("click", (event) => {
    if (!samples.length) return;
    hovered = null;
    pinned = pointAt(event).stamp;
    renderReading();
    onPin(pinned);
  });
  graph.addEventListener("keydown", (event) => {
    if (!samples.length || !["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
    event.preventDefault();
    const index = currentIndex();
    hovered = null;
    if (event.key === "Escape") pinned = null;
    else if (event.key === "Home") pinned = samples[0].stamp;
    else if (event.key === "End") pinned = samples.at(-1).stamp;
    else pinned = samples[Math.max(0, Math.min(samples.length - 1, index + (event.key === "ArrowLeft" ? -1 : 1)))].stamp;
    renderReading();
    onPin(pinned);
  });
  latest.addEventListener("click", () => {
    pinned = hovered = null;
    renderReading();
    graph.focus({ preventScroll: true });
    onPin(null);
  });

  deviceSelect.addEventListener("change", () => {
    selectedGpu = deviceSelect.value;
    update(rows, source);
    onDevice(selectedGpu);
  });

  function update(nextRows, nextSource, nextPid = pid) {
    rows = nextRows;
    const devices = new Map();
    for (const row of rows) {
      for (const device of workbenchGpu.devices(row)) {
        const key = workbenchGpu.key(device);
        const label = Number.isInteger(device.index) ? "GPU " + device.index : tr("GPU device");
        devices.set(key, device.name ? label + " · " + device.name : label);
      }
    }
    const options = JSON.stringify([...devices]);
    if (options !== deviceOptions) {
      deviceOptions = options;
      deviceSelect.replaceChildren(...[...devices].map(([key, label]) => new Option(label, key)));
    }
    if (!devices.has(selectedGpu)) selectedGpu = devices.keys().next().value ?? null;
    deviceSelect.value = selectedGpu ?? "";

    if (source !== nextSource || pid !== nextPid) pinned = hovered = null;
    source = nextSource;
    pid = nextPid;
    const byStamp = new Map();
    for (const row of rows) {
      const stamp = Date.parse(row.timestamp);
      if (Number.isFinite(stamp)) byStamp.set(stamp, row);
    }
    samples = [...byStamp].sort(([a], [b]) => a - b).map(([stamp, row]) => {
      const gpu = workbenchGpu.reading(row, selectedGpu);
      const values = {};
      for (const [key, metric] of Object.entries(resources)) {
        const value = metric.value(row, gpu);
        values[key] = Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
      }
      return { stamp, row, values, gpu };
    });
    const first = samples[0]?.stamp;
    const span = samples.at(-1)?.stamp - first;
    for (const sample of samples) sample.x = span ? 1 + (sample.stamp - first) * 998 / span : 999;
    if (!byStamp.has(pinned)) pinned = null;
    if (!byStamp.has(hovered)) hovered = null;
    for (const button of controls) {
      const key = button.dataset.resource;
      const value = samples.at(-1)?.values[key] ?? null;
      button.querySelector("small").textContent = percent(value);
      button.setAttribute("aria-label", resources[key].label + " · " + (value === null ? tr("No data") : percent(value)));
      trace(key, button.querySelector("svg"));
    }
    renderDetail();
    return { pinned, device: selectedGpu, available: samples.some((sample) =>
      Object.values(sample.values).some((value) => value !== null)) };
  }
  return { update, clearPin() { pinned = hovered = null; renderReading(); } };
};
