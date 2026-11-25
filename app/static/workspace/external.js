"use strict";

(() => {
  const panel = document.getElementById("external-preview");
  if (!panel) return;
  // Fall back to the English key when i18n.js is absent.
  const tr = window.logsenseTranslate || ((message, ...values) =>
    message.replace(/\{(\d+)\}/g, (match, index) => Number(index) < values.length ? String(values[index]) : match));
  const form = panel.querySelector("form");
  const output = document.getElementById("external-raw");
  const status = document.getElementById("external-status");
  const data = document.getElementById("external-data");
  const column = document.getElementById("external-column");
  const number = new Intl.NumberFormat(document.documentElement.lang, { maximumSignificantDigits: 8 });
  let columns = [];
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  function row(tag, values) {
    const cells = values.map((value) => {
      const cell = element(tag, value ?? "—");
      if (tag === "th") cell.scope = "col";
      return cell;
    });
    const result = element("tr");
    result.append(...cells);
    return result;
  }
  function renderDistribution() {
    const graph = document.getElementById("external-distribution");
    const chart = columns[Number(column.value)]?.distribution;
    graph.replaceChildren();
    if (!chart || (chart.kind === "top" && !chart.values.length)) {
      graph.textContent = tr("No distribution for this data type yet.");
      return;
    }
    const histogram = chart.kind === "histogram";
    const bins = histogram ? chart.counts.map((count, index) => {
      const size = chart.counts.length;
      const edge = (i) => (1 - i / size) * chart.min + (i / size) * chart.max;
      const label = size === 1 ? number.format(chart.min) : "[" + number.format(edge(index)) + ", " +
        number.format(edge(index + 1)) + (index === size - 1 ? "]" : ")");
      return { count, label };
    }) : chart.values;
    if (histogram) graph.append(element("p", tr("{0} → {1} · {2} equal bins", number.format(chart.min), number.format(chart.max), bins.length)));
    const max = Math.max(1, ...bins.map((item) => item.count));
    for (const { label, count } of bins) {
      const line = element("div");
      const meter = element("progress");
      meter.max = max;
      meter.value = count;
      meter.setAttribute("aria-label", label || tr("Empty string"));
      meter.textContent = count + "/" + max;
      line.append(element("span", (label || tr("(empty string)")) + " · " + count + " "), meter);
      graph.append(line);
    }
  }

  function renderReport(report) {
    columns = report.columns;
    document.getElementById("external-columns").replaceChildren(...columns.map((item) =>
      row("td", [item.name, item.type, number.format(item.missing)])));
    column.replaceChildren(...columns.map((item, index) => new Option(item.name, index)));
    column.disabled = !columns.length;
    renderDistribution();
    const sample = document.getElementById("external-sample");
    const header = element("thead");
    const body = element("tbody");
    if (columns.length) header.append(row("th", columns.map((item) => item.name)));
    body.append(...report.preview.map((item) => row("td", item)));
    sample.replaceChildren(header, body);
    status.textContent = tr("Rows read: {0} · valid: {1} · malformed: {2} · duplicates: {3}",
      number.format(report.scanned_rows) + (report.total_rows === null ? "" : "/" + number.format(report.total_rows)),
      number.format(report.valid_rows), number.format(report.malformed_rows), number.format(report.duplicate_rows)) +
      (report.sampled ? " · " + tr("Statistics cover only the rows read.") : "");
    data.hidden = false;
  }

  column.addEventListener("change", renderDistribution);
  const unit = form.elements.unit;
  const syncFormat = () => { unit.disabled = form.elements.format.value !== "evaluation"; };
  form.elements.format.addEventListener("change", syncFormat);
  syncFormat();
  // The Project page owns the folder tree; this panel reads files from the project open there.
  const api = window.localWorkbench;
  let revision = 0;
  function clear() {
    revision += 1;
    data.hidden = output.hidden = true;
    status.textContent = "";
  }
  function show(path) {
    clear();
    form.elements.path.value = path;
    const suffix = path.split(".").at(-1).toLowerCase();
    if (["csv", "jsonl", "parquet"].includes(suffix)) form.elements.format.value = suffix;
    syncFormat();
    panel.hidden = false;
    panel.open = true;
    panel.scrollIntoView({ block: "nearest" });
    form.elements.path.focus();
  }
  window.workbenchExternal = {
    show,
    supports: (path) => /\.(csv|jsonl|parquet|log|txt)$/i.test(path),
    reset() { clear(); form.elements.path.value = ""; },
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const observed = ++revision;
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    status.textContent = tr("Reading file…");
    data.hidden = output.hidden = true;
    try {
      const values = Object.fromEntries(new FormData(form));
      const report = await api.call("/external", "POST", values);
      if (observed !== revision) return;
      if (report.columns) renderReport(report);
      else {
        output.textContent = JSON.stringify(report, null, 2);
        output.hidden = false;
        status.textContent = tr("File read.");
      }
    } catch (error) {
      if (observed === revision) status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
})();
