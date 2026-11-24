# docs/ — product documentation

Start with the [project README](../README.md), then pick the area you work on.

| You want to… | Read |
| --- | --- |
| Understand the system | [architecture/](architecture/README.md) · [database architecture](database/ARCHITECTURE.md) · [schema](database/SCHEMA.md) · [ERD](database/ERD.md) |
| Run MySQL and import BGL | [MySQL runbook](database/MYSQL_RUNBOOK.md) · [BGL pipeline](database/BGL_PIPELINE.md) · [uploads](database/UPLOADS.md) · [dataset CRUD](database/DATASET_CRUD.md) |
| Call the API | [API reference](database/API.md) |
| Work on detectors and models | [detectors](database/DETECTORS.md) · [Isolation Forest audit](ml/ISOLATION_FOREST_AUDIT.md) · [July holdout](ml/IF_JULY_HOLDOUT.md) · [BGL window baseline](ml/BGL_WINDOW_BASELINE_RESULTS_VI.md) |
| Work on the interface | [ui/](ui/README.md) |
| Test and verify | [testing](database/TESTING.md) · [platform release verification](releases/PORTFOLIO_VERIFICATION.md) · [benchmarks](benchmarks/v3/REPORT.md) |
| Release | [releases/](releases/UNIVERSITY_MVP_V1_PLAN.md) · [backlog](releases/BACKLOG.md) |
| Use the app (Vietnamese) | [user guide](development/USER_GUIDE_VI.md) |

| Folder | Contents |
| --- | --- |
| `architecture/` | Investigation V3 proposal, data/query and timeline API design |
| `database/` | Schema, migrations, pipelines, API, runbooks, QA reports and measurements |
| `ml/` | Detector design, model audits and measured results |
| `ui/` | UI specifications, wireframes and verification screenshots |
| `releases/` | Release plans, QA results and checklists |
| `benchmarks/` | Benchmark workloads and reports |
| `development/` | User guide, code structure and the Git baseline record |
| `history/` | Superseded design and review reports kept for reference |

Academic material (papers, research notes, course reports) is in [`academic/`](../academic/README.md), not here.
