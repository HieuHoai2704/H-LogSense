# scripts/ — developer and operator commands

Everything here supports the product in `app/`. Run commands from the repository root:

```text
python -m scripts.<group>.<command> [options]
```

Academic and course material lives in `academic/`, never here. Scripts may import `app`, but `app` never
imports `scripts`.

## run/ — run and operate the product

| Command | Purpose |
| --- | --- |
| `scripts.run.workbench` | Start the local workbench from a source checkout (`--browser`, `--no-browser`). |
| `scripts.run.workbench_run` | Background supervisor used by workbench training runs. |
| `scripts.run.worker` | Analysis worker for queued detection jobs (outside the Flask server). |
| `scripts.run.ingestion_worker` | Ingestion worker for queued uploads. |
| `scripts.run.database` | Operator CLI: register datasets, ingest BGL, create users, send notifications. |
| `scripts.run.mysql_runtime` | Lifecycle of the owned local MySQL runtime (start, stop, exec, grants, backup). |
| `scripts.run.logsense_client` | Authenticated Python client for the JSON API. |
| `scripts.run.desktop` | Tkinter companion for the authenticated workspace. |

## ml/ — models the product loads

| Command | Purpose |
| --- | --- |
| `scripts.ml.audit_isolation_forest` | Preregistered IF study; writes `.local/if_studies`, replayed by `app/services/window_deployment.py`. |
| `scripts.ml.audit_if_holdout` | July holdout study; writes `.local/if_new_holdout`, loaded by `app/services/validated_if.py`. |
| `scripts.ml.bgl_window_baseline` | Evaluate the product's BGL detectors with disjoint temporal selection. |

## qa/ — verification

| Command | Purpose |
| --- | --- |
| `scripts.qa.qa_workbench_browser` | Workbench browser E2E against an isolated loopback launcher. |
| `scripts.qa.qa_workbench_desktop` | Native desktop window smoke test (WebView2, WKWebView, WebKitGTK). |
| `scripts.qa.qa_investigation_v2`, `scripts.qa.qa_evidence_drawer` | Investigation and Evidence Drawer browser checks on synthetic data. |
| `scripts.qa.qa_platform`, `scripts.qa.qa_dataset_crud`, `scripts.qa.qa_university_e2e_browser` | Authenticated browser QA on MySQL data. |
| `scripts.qa.qa_accessibility` | Automated axe-core scan. |
| `scripts.qa.verify_mysql` | Provision new test schemas, migrate and run the MySQL test suites. |
| `scripts.qa.verify_university_e2e`, `scripts.qa.verify_university_filters` | Real-BGL release verification and filter matrix. |
| `scripts.qa.verify_detectors`, `scripts.qa.verify_validated_if_bgl`, `scripts.qa.verify_import_restart` | Detector, frozen-model and import-restart proofs. |

## bench/ — performance

`scripts.bench.benchmark_api`, `scripts.bench.benchmark_bgl`, `scripts.bench.benchmark_investigation_v3`.

## release/ — packages

| Command | Purpose |
| --- | --- |
| `scripts.release.package_workbench --output DIR` | Build the source ZIP, Windows/macOS/Linux ZIPs and SHA-256 list. Installers come from `packaging/`. |
| `scripts.release.qa_portfolio_install DIR [--desktop]` | Install a built ZIP in a fresh environment and run the checks. |
