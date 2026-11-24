"use strict";

(() => {
  const panel = document.getElementById("run-detail");
  if (!panel) return;
  const byId = (id) => document.getElementById(id);
  const slider = byId("run-time");
  const follow = byId("run-follow");
  const timeValue = byId("run-time-value");
  const checkpoints = byId("run-checkpoints");
  const profilePanel = byId("run-profile");
  const profileStatus = byId("run-profile-status");
  const profileRows = byId("run-profile-metadata");
  const profileFiles = byId("run-profile-files");
  const profileRefresh = byId("run-profile-refresh");
  const sourceLinks = byId("run-source-links");
  const isoPrefix = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})(?=\s|$)/i;
  const lossSeries = [["train_loss", "Train loss"], ["val_loss", "Validation loss", "5 3"]];
  const machineSeries = [["cpu_percent", "CPU"], ["gpu_percent", "GPU", "5 3"], ["ram_percent", "RAM", "2 3"]];
  let runId, log, latest, model, renderKey, markerKey;
  let pinned = null;
  let checkpoint = null;
  let runStatus;
  let gpu = null;
  let profileRequest = 0;

  function parseLog(text) {
    const epochs = new Map();
    const markers = [];
    const timed = [];
    const lines = text.split(/\r?\n/);
    lines.forEach((raw, index) => {
      const prefix = raw.match(isoPrefix)?.[0];
      if (!prefix) return;
      const time = Date.parse(prefix.replace(" ", "T"));
      const date = prefix.slice(0, 10);
      const calendar = new Date(date + "T00:00:00Z");
      if (!Number.isFinite(time) || !Number.isFinite(calendar.valueOf()) || iso(calendar.valueOf()).slice(0, 10) !== date) return;
      const entry = { time, index, raw };
      timed.push(entry);
      const message = raw.slice(prefix.length);
      const epoch = message.match(/\bepoch\s*=\s*(\d+)(?=[\s/,;]|$)/i);
      if (epoch) {
        const number = Number(epoch[1]);
        if (!epochs.has(number)) epochs.set(number, time);
        else if (epochs.get(number) !== time) epochs.set(number, null);
      }
      if (/\b(?:checkpoint\s+(?:saved|written)|(?:saved|wrote)\s+(?:a\s+)?checkpoint)\b/i.test(message)) markers.push(entry);
    });
    return { lines, timed: timed.sort((a, b) => a.time - b.time), epochs, markers };
  }

  function closestIndex(times, time) {
    let low = 0;
    let high = times.length - 1;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (times[middle] < time) low = middle + 1;
      else high = middle;
    }
    return low > 0 && time - times[low - 1] <= times[low] - time ? low - 1 : low;
  }

  function select(time, marker = null) {
    pinned = time;
    checkpoint = marker;
    render();
  }

  function svgElement(name, attributes, text) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function draw(container, points, series, time, percent = false) {
    const { times } = model;
    container.replaceChildren();
    const values = points.flatMap((point) => series.map(([key]) => point[key])).filter(Number.isFinite);
    if (!values.length) {
      container.textContent = percent ? "Chưa có mẫu tải máy có thời gian." : "Chưa có điểm loss ghép được với thời gian.";
      return;
    }
    const start = times[0], end = times.at(-1);
    const min = percent ? 0 : Math.min(0, ...values);
    let max = percent ? 100 : Math.max(0, ...values);
    if (max === min) max = 1;
    const scale = Math.max(Math.abs(min), max);
    const x = (stamp) => end === start ? 260 : 52 + 416 * (stamp - start) / (end - start);
    const y = (value) => 87 - 74 * (value / scale - min / scale) / (max / scale - min / scale);
    const svg = svgElement("svg", { viewBox: "0 0 500 112", preserveAspectRatio: "none",
      "aria-hidden": "true", "data-selectable": "" });
    for (const value of [min, max]) {
      svg.append(svgElement("path", { d: "M52 " + y(value) + "H468", stroke: "var(--border)" }),
        svgElement("text", { x: 46, y: y(value) + 3, "text-anchor": "end" }, Number(value.toPrecision(3))));
    }
    for (const [stamp, anchor, position] of start === end ? [[start, "middle", 260]] :
      [[start, "start", 52], [end, "end", 468]]) {
      svg.append(svgElement("text", { x: position, y: 107, "text-anchor": anchor }, iso(stamp).slice(11, 19)));
    }
    for (const marker of model.markers) {
      const position = x(marker.time);
      svg.append(svgElement("path", { d: "M" + (position - 3) + " 94h6l-3 -5Z", fill: "currentColor" }));
    }
    if (time >= start && time <= end) {
      svg.append(svgElement("path", { d: "M" + x(time) + " 10V89", stroke: "var(--warning)", "stroke-dasharray": "3 3" }));
    }
    const legend = document.createElement("div");
    legend.className = "run-series";
    for (const [key, name, dash] of series) {
      if (!points.some((point) => Number.isFinite(point[key]))) continue;
      let path = "";
      let continuing = false;
      for (const point of points) {
        if (Number.isFinite(point[key])) {
          const position = x(point.time) + " " + y(point[key]);
          path += (continuing ? " L" : " M") + position;
          svg.append(svgElement("circle", { cx: x(point.time), cy: y(point[key]), r: point.time === time ? 3 : 1.5,
            fill: point.time === time ? "var(--warning)" : "var(--text)" }));
          continuing = true;
        } else continuing = false;
      }
      svg.append(svgElement("path", { d: path.trim(), fill: "none", stroke: "var(--text)", "stroke-dasharray": dash || "" }));
      const label = document.createElement("span");
      if (dash) label.dataset.line = dash === "5 3" ? "dashed" : "dotted";
      const exact = points.find((point) => point.time === time && Number.isFinite(point[key]));
      label.textContent = name + (exact ? " " + exact[key] + (percent ? "%" : "") : "");
      legend.append(label);
    }
    svg.addEventListener("click", (event) => {
      const bounds = svg.getBoundingClientRect();
      const fraction = Math.max(0, Math.min(1, ((event.clientX - bounds.left) * 500 / bounds.width - 52) / 416));
      select(times[closestIndex(times, start + fraction * (end - start))]);
    });
    container.append(svg, legend);
  }

  const iso = (time) => new Date(time).toISOString();
  function renderLog(time) {
    const note = byId("run-log-note");
    const pre = byId("run-log-context");
    const first = log.timed[0]?.time, last = log.timed.at(-1)?.time;
    pre.replaceChildren();
    if (first === undefined) {
      const text = log.lines.filter((line) => line.trim()).slice(-5).join("\n");
      note.textContent = text ? "Các dòng cuối chưa có mốc giờ để đối chiếu." : "Chưa có đầu ra từ lượt chạy.";
      pre.textContent = text;
      return;
    }
    if (time === undefined || time < first || time > last) {
      note.textContent = "Mốc này nằm ngoài phạm vi log có thời gian đang đọc.";
      return;
    }
    const entry = log.markers.find((marker) => marker.time === time && marker.raw === checkpoint) ??
      log.timed[closestIndex(model.logTimes, time)];
    note.textContent = entry.time === time ? "Log trùng mốc · " + iso(entry.time) :
      "Log gần nhất · " + iso(entry.time) + " · lệch " + Math.abs(time - entry.time) / 1000 + " giây";
    const before = log.lines.slice(Math.max(0, entry.index - 2), entry.index);
    const after = log.lines.slice(entry.index + 1, entry.index + 3);
    const mark = document.createElement("mark");
    mark.textContent = entry.raw;
    pre.append(before.length ? before.join("\n") + "\n" : "", mark, after.length ? "\n" + after.join("\n") : "");
  }

  function render() {
    const { loss, machine, times } = model;
    const time = pinned ?? times.at(-1);
    slider.max = String(Math.max(0, times.length - 1));
    slider.disabled = !times.length;
    slider.value = String(times.length ? closestIndex(times, time) : 0);
    timeValue.textContent = time === undefined ? "Chưa có mốc" : iso(time);
    slider.setAttribute("aria-valuetext", timeValue.textContent);
    follow.setAttribute("aria-pressed", String(pinned === null));
    draw(byId("run-loss"), loss, lossSeries, time);
    const selectedMachine = machine.map((row) => ({ ...row, gpu_percent: workbenchGpu.reading(row, gpu)?.percent }));
    draw(byId("run-machine"), selectedMachine, machineSeries, time, true);
    renderLog(time);
  }

  function addProfileRow(label, value) {
    const row = document.createElement("div");
    const title = document.createElement("dt");
    const detail = document.createElement("dd");
    title.textContent = label;
    detail.textContent = value;
    row.append(title, detail);
    profileRows.append(row);
  }

  function renderProfile(data) {
    const { run, profile, streams, artifacts } = data;
    profileRows.replaceChildren();
    profileFiles.replaceChildren();
    addProfileRow("Thư mục dự án", run.root);
    addProfileRow("Thời gian (UTC)", [run.started_at, run.ended_at].filter(Boolean).join(" → "));
    if (run.exit_code !== null) addProfileRow("Mã thoát", run.exit_code);
    if (profile) {
      const { git, interpreter, script } = profile;
      const change = git.dirty === null ? "Chưa xác định thay đổi" : git.dirty ? "Có thay đổi chưa commit" : "Sạch";
      addProfileRow("Chụp metadata (UTC)", profile.captured_at);
      addProfileRow("Git", git.status === "available" ?
        [git.branch, git.commit || "Chưa đọc được commit", change].filter(Boolean).join(" · ") : "Git không khả dụng");
      addProfileRow("Môi trường Python", [interpreter.id, interpreter.version || "Chưa đọc được phiên bản",
        interpreter.platform, interpreter.architecture].filter(Boolean).join(" · "));
      addProfileRow("Interpreter", interpreter.executable);
      addProfileRow("SHA-256 mã chạy", script.sha256 || fingerprintLabel(script.status));
      const parameters = profile.parameters.map(({ name, value }) => name + "=" + value).join(" · ");
      addProfileRow("Tham số chạy", profile.argument_count + " đối số" + (parameters ? " · " + parameters : ""));
      addProfileRow("Lấy mẫu GPU", profile.gpu_sampling ? "Bật" : "Tắt");
      for (const file of profile.config_files) {
        addProfileRow(file.path, file.sha256 || fingerprintLabel(file.status));
      }
    }
    if (data.artifact_directory) addProfileRow("Thư mục kết quả", data.artifact_directory);
    const number = new Intl.NumberFormat("vi");
    const kinds = { log: "Log", machine: "Số đo máy", training: "Chỉ số train", artifact: "Kết quả" };
    for (const file of [...streams, ...artifacts]) {
      const item = document.createElement("li");
      item.textContent = kinds[file.kind] + " · " + file.path + " · " + number.format(file.bytes) + " B";
      profileFiles.append(item);
    }
    if (!profileFiles.childElementCount) {
      const item = document.createElement("li");
      item.textContent = "Chưa có tệp đầu ra.";
      profileFiles.append(item);
    }
    const status = profile ? "Đã đọc hồ sơ." : run.status === "starting" ?
      "Đang chụp hồ sơ trước khi chạy." : "Lượt này chưa có hồ sơ môi trường lúc chạy.";
    profileStatus.textContent = status + (data.artifacts_limited ? " Danh sách tệp đã giới hạn." : "");
  }

  function fingerprintLabel(status) {
    if (status === "too_large") return "Tệp vượt 1 MiB";
    return status === "changed" ? "Tệp thay đổi trong lúc đọc" : "Chưa đọc được";
  }

  async function loadProfile() {
    if (!runId || !profilePanel.open) return;
    const id = runId;
    const request = ++profileRequest;
    profileRefresh.disabled = true;
    profileStatus.textContent = "Đang đọc hồ sơ…";
    try {
      const data = await window.localWorkbench.call("/runs/" + id + "/profile");
      if (request === profileRequest && id === runId) renderProfile(data);
    } catch (error) {
      if (request === profileRequest) profileStatus.textContent = error.message;
    } finally {
      if (request === profileRequest) profileRefresh.disabled = false;
    }
  }

  function clear() {
    runId = log = model = latest = renderKey = markerKey = undefined;
    pinned = checkpoint = null;
    runStatus = undefined;
    profileRequest += 1;
    profileRows.replaceChildren();
    profileFiles.replaceChildren();
    profileStatus.textContent = "";
    profileRefresh.disabled = false;
    sourceLinks.replaceChildren();
    panel.hidden = true;
  }

  function update(result) {
    if (result.run.id !== runId) {
      clear();
      runId = result.run.id;
    }
    if (runStatus !== result.run.status) {
      runStatus = result.run.status;
      loadProfile();
    }
    if (result.log.changed) {
      log = parseLog(result.log.text);
      const links = window.WorkbenchSourceLinks;
      const targets = new Map();
      for (const line of log.lines.slice().reverse()) {
        const target = links.reference(line, result.run.root);
        if (!target) continue;
        const key = JSON.stringify([target.path, target.line, target.column]);
        if (!targets.has(key)) targets.set(key, target);
        if (targets.size >= 20) break;
      }
      sourceLinks.replaceChildren(...[...targets.values()].map(links.button));
    }
    if (!log) log = parseLog("");
    const key = JSON.stringify([result.training, result.machine, result.run.status]);
    if (latest === log && renderKey === key) return;
    const markers = log.markers.slice(-20).reverse();
    const markerText = JSON.stringify(markers.map((marker) => marker.raw));
    if (markerText !== markerKey) {
      markerKey = markerText;
      checkpoints.replaceChildren();
      for (const marker of markers) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = iso(marker.time).slice(11, 23);
        button.title = marker.raw;
        button.addEventListener("click", () => select(marker.time, marker.raw));
        checkpoints.append(button);
      }
      if (!checkpoints.childElementCount) checkpoints.textContent = "Chưa thấy dòng ghi lưu checkpoint có thời gian.";
    }
    latest = log;
    renderKey = key;
    const loss = result.training.map((point) => ({
      ...point, time: point.timestamp ? Date.parse(point.timestamp) : log.epochs.get(point.epoch)
    })).filter((point) => Number.isFinite(point.time)).sort((a, b) => a.time - b.time);
    const machine = result.machine.map((point) => ({ ...point, time: Date.parse(point.timestamp) }))
      .filter((point) => Number.isFinite(point.time)).sort((a, b) => a.time - b.time);
    const logTimes = log.timed.map((entry) => entry.time);
    const times = [...new Set([...logTimes, ...loss.map((point) => point.time), ...machine.map((point) => point.time)])]
      .sort((a, b) => a - b);
    model = { loss, machine, logTimes, times, markers };
    byId("run-detail-meta").textContent = result.run.script + " · " + result.run.status + " · " + runId;
    const unsynced = result.training.length - loss.length;
    const missing = unsynced ? " " + unsynced + " điểm loss thiếu mốc tin cậy, vẫn xem được trong biểu đồ theo epoch." : "";
    const scope = result.run.source === "attached" ? "PID " + result.run.pid + " · CPU/RAM theo tiến trình · " : "";
    byId("run-coverage").textContent = scope + "UTC · Tối đa 64 KiB log gần nhất và 120 điểm mỗi loại chỉ số." + missing;
    panel.hidden = false;
    render();
  }

  slider.addEventListener("input", () => select(model.times[Number(slider.value)]));
  follow.addEventListener("click", () => select(null));
  profilePanel.addEventListener("toggle", loadProfile);
  profileRefresh.addEventListener("click", loadProfile);
  window.WorkbenchRunDetail = { clear, update, timedLoss: () => model?.loss ?? [],
    selectTime(stamp) { if (model) select(stamp); },
    setDevice(device) {
      if (device === gpu) return;
      gpu = device;
      if (model) render();
    },
  };
})();
