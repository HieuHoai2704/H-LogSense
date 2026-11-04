# Proposed baseline commit files

**Gate 1 review only. Nothing is staged or committed.**

Intended file count: **100**. Root `.gitignore` is the only planned replacement of an existing file; its exact proposed content is `GITIGNORE_PROPOSED.txt`. All other existing files remain byte-for-byte unchanged.

The approval manifest is included in this list; its self-hash is stored only in the private preparation receipt to avoid a circular hash definition.

## [root] — 4 files

```text
.gitignore
README.md
config.py
requirements.txt
```

## app — 17 files

```text
app/__init__.py
app/access.py
app/api/__init__.py
app/api/anomalies.py
app/demo.py
app/presentation.py
app/services/__init__.py
app/services/evidence.py
app/services/investigation.py
app/services/redaction.py
app/static/css/console.css
app/static/css/main.css
app/static/js/dashboard.js
app/static/js/evidence.js
app/templates/dashboard.html
app/templates/partials/workspace.html
app/templates/query_error.html
```

## data — 1 files

```text
data/raw/LOGHUB_LICENSE.txt
```

## docs — 70 files

```text
docs/EVIDENCE_DRAWER.md
docs/INVESTIGATION_V2_IMPLEMENTATION.md
docs/PROGRESS_TRACKER.md
docs/SINGLE_WORKSPACE.md
docs/UI_EXPERT_ASSESSMENT.md
docs/UI_PREVIEW.md
docs/UI_REVIEW.md
docs/UI_REVIEW_PROMPT.md
docs/WORKSPACE_V2_DESIGN.md
docs/architecture/INVESTIGATION_V3_PROPOSAL.md
docs/architecture/README.md
docs/architecture/V3_DATA_AND_QUERIES.md
docs/architecture/V3_TIMELINE_API.md
docs/benchmarks/v3/REPORT.md
docs/benchmarks/v3/environment.json
docs/benchmarks/v3/fixture-baseline.json
docs/benchmarks/v3/fixture-profile.txt
docs/benchmarks/v3/unit-test-report.txt
docs/benchmarks/v3/workload-matrix.json
docs/development/BASELINE_COMMIT_FILES.md
docs/development/BASELINE_COMMIT_MANIFEST.json
docs/development/GITIGNORE_PROPOSED.txt
docs/development/GIT_BASELINE_REPORT.md
docs/research/BASELINE_REVIEW.md
docs/research/DATASETS.md
docs/research/DATA_PREVIEW.md
docs/research/ENTERPRISE_UI_REFERENCES.md
docs/research/PAPERS.md
docs/research/README.md
docs/research/archive_inventory.json
docs/research/datasets.json
docs/research/download_status.json
docs/research/paper_download_status.json
docs/ui/README.md
docs/ui/TIMELINE_V2_UI_SPEC.md
docs/ui/VERIFICATION.md
docs/ui/evidence-drawer/browser-report.json
docs/ui/evidence-drawer/evidence-1366.png
docs/ui/evidence-drawer/evidence-1440.png
docs/ui/evidence-drawer/evidence-390.png
docs/ui/evidence-drawer/evidence-ml-details.png
docs/ui/evidence-drawer/evidence-page.json
docs/ui/evidence-drawer/evidence-related.png
docs/ui/evidence-drawer/evidence-safe-raw.png
docs/ui/evidence-drawer/evidence-selected-1440.png
docs/ui/evidence-drawer/unit-test-report.txt
docs/ui/generate_wireframes.py
docs/ui/implementation-v2/browser-report.json
docs/ui/implementation-v2/selected-scope.csv
docs/ui/implementation-v2/unit-test-report.txt
docs/ui/implementation-v2/verification-environment.json
docs/ui/implementation-v2/workspace-1024.png
docs/ui/implementation-v2/workspace-1366.png
docs/ui/implementation-v2/workspace-1440.png
docs/ui/implementation-v2/workspace-evidence.png
docs/ui/implementation-v2/workspace-partial.png
docs/ui/implementation-v2/workspace-selection.png
docs/ui/source-integrity.json
docs/ui/timeline-v2-compact.png
docs/ui/timeline-v2-compact.svg
docs/ui/timeline-v2-desktop.png
docs/ui/timeline-v2-desktop.svg
docs/ui/timeline-v2-evidence.png
docs/ui/timeline-v2-evidence.svg
docs/ui/timeline-v2-selection.png
docs/ui/timeline-v2-selection.svg
docs/ui/timeline-v2-states.png
docs/ui/timeline-v2-states.svg
docs/ui/token-contrast.json
docs/ui/wireframe-render-check.json
```

## scripts — 5 files

```text
scripts/benchmark_investigation_v3.py
scripts/download_research.py
scripts/inspect_research_archives.py
scripts/qa_evidence_drawer.py
scripts/qa_investigation_v2.py
```

## tests — 3 files

```text
tests/test_evidence.py
tests/test_investigation_v2.py
tests/test_workspace.py
```

## Exclusions

Full raw archives, virtual environments, bytecode, local browser/runtime state, downloaded PDFs/extracted text and private backups are excluded. Nothing is deleted. Curated small synthetic CSV/JSON and screenshots in documentation remain included.

Native Git ignore matching and exact staging are deferred until Gate 2 approval.
