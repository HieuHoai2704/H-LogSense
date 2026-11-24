"use strict";

(() => {
  const panel = document.getElementById("external-preview");
  if (!panel) return;
  // logs.html includes this panel without i18n.js; fall back to the English key there.
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
    status.textContent = tr("{0} rows read · {1} valid · {2} malformed · {3} duplicates",
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
  const api = window.localWorkbench.scope("analysis");
  let revision = 0;
  const view = window.createWorkbenchViewState(api);
  if (api.authorized) {
    const explorerStatus = document.getElementById("analysis-explorer-status");
    const onError = (message) => { explorerStatus.textContent = message; };
    function showFile(path, format) {
      revision += 1;
      form.elements.path.value = path;
      const suffix = path.split(".").at(-1).toLowerCase();
      if (format) form.elements.format.value = format;
      else if (["csv", "jsonl", "parquet"].includes(suffix)) form.elements.format.value = suffix;
      syncFormat();
      data.hidden = output.hidden = true;
      status.textContent = "";
      form.closest("details").open = true;
    }
    const explorer = window.createWorkbenchExplorer({
      api,
      onFile(path) {
        showFile(path);
        view.patch({ analysis_file: path, analysis_format: form.elements.format.value });
      },
      onError,
    });
    const scope = { api, view, root: null, recent: [] };
    async function openRoot(result) {
      const changed = result.root !== scope.root;
      if (changed) {
        revision += 1;
        form.elements.path.value = "";
        data.hidden = output.hidden = true;
        status.textContent = "";
      }
      Object.assign(scope, { root: result.root, recent: result.recent });
      api.setProject(result.project);
      if (changed) {
        await view.load(scope.root);
        if (view.data.analysis_file) showFile(view.data.analysis_file, view.data.analysis_format);
      }
      chooser.update(scope);
      explorerStatus.textContent = "";
      await explorer.open(scope.root, api, view);
    }
    const chooser = window.bindWorkbenchFolder({ getScope: () => scope, onOpen: openRoot });
    api.call("/session").then(openRoot).catch((error) => onError(error.message));
    form.elements.format.addEventListener("change", () => {
      if (scope.root && form.elements.path.value) view.patch({ analysis_format: form.elements.format.value });
    });
  }

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
      view.patch({ analysis_file: values.path, analysis_format: values.format });
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
