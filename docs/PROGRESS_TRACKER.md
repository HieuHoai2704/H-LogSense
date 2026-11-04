# Progress tracker

Updated: 2026-11-03.

V3 architecture review completed as a proposal/report only: distinct R/P/U/E/A
counts, SQL-side aggregate/query design, detector/run identity, coverage and
snapshot semantics, and a staged 10K/100K/1M matrix. Measured the current
six-anomaly HTTP/DOM baseline; no MySQL/EXPLAIN/large-data results claimed.
See `architecture/README.md` and `benchmarks/v3/REPORT.md`. No application/database
migration or infrastructure startup was performed.

Evidence Drawer increment: scope-wide Previous/Next, explicit raw provenance and
rule/ML availability, safe redacted chunks, bounded cursor-related records,
copy/filter/focus/export actions and public-demo source policy are implemented.
See `EVIDENCE_DRAWER.md`: 50 backend/unit/API tests, 13 drawer browser groups and
21 Investigation regression groups passed. Real log storage, detector execution
and per-user production authorization remain unimplemented.

Latest increment: Adaptive Investigation V2 is implemented for labelled synthetic
sources, with REST aggregation, Overall/detector groups, Severity/Volume, brush,
backend zoom, multi-select facets, paged results, API evidence, server CSV and
coverage/query status. See `INVESTIGATION_V2_IMPLEMENTATION.md` and its generated
browser report. Real MySQL/SQLAlchemy, ingestion, detector runs, authorization and
large-data benchmarks remain blocked by missing backend implementation.

The entries below record earlier increments; the latest report is authoritative.

Workspace v2 completed: compact source/period/timezone/search command bar, shared
filter scope, occupied timeline cells linked to the table, docked evidence panel,
history/partial updates, empty/loading/error states and selected-result CSV.
Eight automated scope/rendering tests and Edge interaction checks passed.
See `WORKSPACE_V2_DESIGN.md`. All records remain synthetic; no model ran.

Latest UI increment: one monitoring workspace; seven-item navigation removed.
Combined host/service/severity filters, context collapse, drawer/Escape, filtered
CSV and mobile behavior verified in Edge. See `SINGLE_WORKSPACE.md`.

## Completed with evidence

- Flask application factory and local configuration.
- White/teal synthetic Anomaly Center preview with responsive navigation,
  server-side fixture filters, drawer and filtered demo CSV.
- Flask smoke checks and Edge interaction checks; see `UI_PREVIEW.md`.
- Research source catalog, download script, checksums and archive inspection tooling.
- Published baseline comparison notes; see `research/BASELINE_REVIEW.md`.
- Eight dataset archives downloaded (2,274,137,596 bytes), all provider MD5 values
  matched, local SHA-256 recorded. No full extraction performed.
- Eight readable PDF papers downloaded; P03 mirror/author acquisition failed.
- Generic promotional UI removed; fixture-derived summary replaces invented volume.
  See `UI_REVIEW.md` for assessment and changes.

Dataset/PDF acquisition status is artifact-specific; consult
`research/datasets.json`, `research/download_status.json`, and
`research/paper_download_status.json`. A catalog entry is not proof of a download.

## Not implemented

MySQL schema/migrations, authentication, actual ingestion/parsers, persisted jobs,
feature engineering, detection, local benchmark evaluation and real-data charts.
No course-MVP milestone is declared complete based on the UI alone.
