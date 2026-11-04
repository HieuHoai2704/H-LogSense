# Enterprise log investigation UI references

Collected: 2026-11-03. Scope: public first-party documentation and documented
interface examples. No authenticated product trial, user study or exhaustive
market review was performed. Interfaces depend on release, edition and permissions.
These are products in the same problem category, not companies named LogSense AI.

## Comparison

| Product / screen | Documented structure and interaction | Proposed adaptation | Defer / avoid |
|---|---|---|---|
| Elastic / Kibana Anomaly Explorer | Time picker, top influencers, swimlanes and anomaly records; selecting a lane interval exposes matching anomalies | Detector lanes linked to an investigation table; observed/reference evidence | Do not call host counts statistical influencers or reuse proprietary score semantics |
| Datadog / Log Explorer | Query/facet workflow; detail panel puts infrastructure/application context above actual log content | Host/service facets and a structured side drawer with raw content | Trace correlation requires real identifiers and retained trace data |
| Grafana / Explore and Logs Drilldown | Query or point-and-click exploration; log volume, log list, inline/sidebar details and surrounding context | Expand details in place, wrap/copy logs, inspect neighboring records | Avoid introducing LogQL/Loki or another backend just to copy a screen |
| Splunk / Search & Reporting | Search/time scope, event timeline, fields sidebar and event viewer | One investigation canvas with field filters and time selection | Do not expose SPL or every report/alert feature in an initial student UI |
| Dynatrace / Logs app | Query/date selection, histogram, records and detail context; query filters differ from search in already loaded results | Make server query scope distinct from local highlighting/search, if both exist | Do not imply browser-only filtering scans an entire dataset |
| Google Cloud / Logs Explorer | Query, Fields, Timeline and Query results panes; pane visibility and entry summaries are configurable | Collapsible context, adjustable columns, clear time scope and linked results | Do not confuse scroll-to-time with a query that changes the global time range |

The reusable investigation pattern is **scope → query/filter → temporal overview
→ records → evidence**. This is our synthesis, not a vendor claim that their full
platform consists of a single page. Most provide many additional applications.

## Official source and visual-reference register

### R01 — Elastic

- [View anomaly detection results](https://www.elastic.co/docs/explore-analyze/machine-learning/anomaly-detection/ml-ad-view-results).
- Visual targets: “Influencers in the Kibana Anomaly Explorer”, anomaly swimlanes,
  anomaly records and alerts illustrations on the page.
- Important distinction: bucket, influencer and record scores are different
  result types. A count of logs by host is not evidence of statistical influence.
- The user's earlier reference shares these concepts; exact screenshot version
  and provenance were not independently established.

### R02 — Datadog

- [Log facets](https://docs.datadoghq.com/logs/explorer/facets/).
- [Log side panel](https://docs.datadoghq.com/logs/explorer/side_panel/?lang_pref=en).
- Visual targets: facet panel and log detail panel examples.
- Context/content separation is useful for a small drawer. Attribute actions can
  refine a query without requiring a separate screen.
- Side-panel evidence was accessible through the indexed first-party page; a
  direct fetch of the bare URL returned an unsupported Markdown content type.

### R03 — Grafana Labs

- [Logs in Explore](https://grafana.com/docs/grafana/latest/visualizations/explore/logs-integration/).
- [What are the Drilldown apps?](https://grafana.com/docs/learning-hub/explore-your-data/00-intro/02-what-is-drilldown/).
- Visual targets: log volume/list, log details and log-context examples.
- Explore supports inline and sidebar detail modes. Drilldown provides a
  point-and-click entry path; it is not the same screen as classic Explore.

### R04 — Splunk

- [About the Search app — versioned documentation](https://help.splunk.com/en/splunk-enterprise/search/search-manual/10.4/use-the-search-app/about-the-search-app).
- [Timeline investigation](https://help.splunk.com/en/splunk-enterprise/search/search-manual/10.6/retrieve-events/use-the-timeline-to-investigate-events).
- Visual targets: Search dashboard and search results area, including timeline,
  fields sidebar and events viewer.
- Record the documentation version when taking reference screenshots; do not
  assume every edition currently has identical controls.

### R05 — Dynatrace

- [Current Logs app](https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-logs-app).
- [Query and filter logs](https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-logs-app/query-and-filter).
- Visual targets: Logs app gallery with histogram, severity trends and log details.
- The classic Log Viewer is a separate reference; it is not used as evidence of
  the current Logs app's exact layout.

### R06 — Google Cloud

- [Logs Explorer interface](https://docs.cloud.google.com/logging/docs/view/logs-explorer-interface).
- Visual targets: interface overview and sections for Query, Fields, Timeline
  and Query results.
- The documentation distinguishes changing time scope, scrolling to an entry,
  and zooming to a time interval. These should not be one ambiguous action.

Use linked official illustrations as references; no vendor logos, screenshots,
CSS or proprietary assets were copied into the application's design.

## Recommended composition for this project

1. Start with query/time controls and optional dataset context, not a large logo.
2. Use collapsible host/service facets, inspired by field/facet exploration.
3. Retain an anomaly swimlane because detection, not just log volume, is central.
4. Connect selection to the result table and inspectable evidence drawer.
5. Keep the original white/teal system with readable type and strong priority cues.
6. Keep raw log severity distinct from assigned anomaly priority and model scores.
7. Implement one understandable query interaction before advanced query languages,
   trace correlation, live-tail or natural-language assistants.

Only the visible project wordmark was removed in this increment. Research patterns
above are design recommendations, not newly implemented product features.
