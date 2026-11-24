# Post-University MVP backlog

This backlog keeps enterprise optimization and research separate from closing
[University MVP v1.0](UNIVERSITY_MVP_V1_PLAN.md). It is not a promise of delivered
features. Do not promote an item into the release solely to make the portfolio
look larger. Correctness/security defects in current scope remain immediate work.

Measured priority within this backlog: the 100K E2E took 165.39s for the rule
worker and 117.46s for IF; per-unit persistence dominated and worker RSS sampled
about 670MiB. The rule issued 478,389 SQL statements and IF 318,057. Benchmark
bulk persistence and streaming evaluation before choosing an optimization;
do not delay current MVP verification/source review to build a new platform.
These are historical operator-chain measurements, not a benchmark of the new
upload worker or frozen July inference. Dataset CRUD, Flask-WTF forms and
bounded queued upload are now implemented; their expanded MySQL/API checks and
new 11/11-group actual 100K upload/browser E2E pass, recorded in
[current release QA](DATASET_UPLOAD_RELEASE_QA.md).
See [the historical measurements](E2E_REAL_BGL.md).

Research follows the [Graduation Thesis roadmap](GRADUATION_THESIS_ROADMAP_VI.md).
The [tested University MVP baseline](UNIVERSITY_MVP_BASELINE_VI.md) is the fixed
software reference for that work.

## Enterprise platform work

| Item | Trigger / evidence required before implementation |
|---|---|
| Pre-aggregated buckets, cache, summary tables, partitioning or columnar analytics | A defined workload, actual SQL EXPLAIN and measured latency/query cost show current indexed MySQL aggregation is insufficient |
| Optimize per-unit prediction persistence | Measured batched ORM cost on a required workload; preserve native DOUBLE scores, unique run/unit identities, atomic progress and restart safety |
| Distributed scheduler, Redis/Celery, automatic worker recovery | Multiple workers/hosts are actually required; define ownership leases, retry semantics and idempotency before adding services |
| Real-time log ingestion | Explicit operational need, bounded backpressure, authentication and a tested policy for late events and coverage recomputation |
| Real-Time AI Training Monitoring | **DEFERRED.** Begin only after the Graduation Thesis is complete. Scope includes a Python collector/SDK, HTTP batch ingestion keyed by `run_id`, epoch and loss metrics, GPU utilization and VRAM usage, a training dashboard, and training alerts. Validate Windows and macOS connectivity over a private LAN with authenticated, encrypted transport and firewall rules restricted to approved devices. |
| General model registry and drift-aware future inference | A bounded opt-in July frozen IF profile is already implemented; a broader registry/update policy needs a concrete task. Preserve immutable fit/calibration/schema/threshold hashes and input compatibility; never apply the July profile to earlier June data |
| Enterprise identity, multi-tenant administration and global throttling | Defined tenant identity and trust model, not just additional roles; authorization and isolation tests across all data paths |
| Retention and immutable publication manifests | Approved data lifecycle and deletion policy, auditability and coverage semantics; no silent deletion of retained research data |
| SMTP delivery operations | Authorized provider/recipient, deliverability feedback, bounded retry/dedup and secret handling; existing outbox remains at-least-once |
| Off-device backups, PITR and disaster recovery | Defined recovery objective and an actual restore exercise; existing local restart/restore is not off-device recovery |
| Hosted deployment, TLS, CI/CD and observability | A tested university release first, then reviewed hosting/cost/privacy and explicit deployment/publication approval |
| New comparison dashboard or additional navigation | A concrete investigation task that current workspace cannot support; retain one coherent workspace and meaningful actions |

## Research work

| Item | Required experiment discipline |
|---|---|
| Rolling temporal validation on larger BGL regions | Preregister new chronological splits; June 20-25 and July 21-28 are now exposed tests and cannot be reused for selection. The completed July study is in [IF_JULY_HOLDOUT.md](../ml/IF_JULY_HOLDOUT.md) |
| Supervised classifier baseline | Ground-truth/unit compatibility, time-separated fit/calibration/test and an untouched final test; report label-informed supervision explicitly |
| Fair label-calibrated rule comparison | Apply the same available validation supervision and FPR budget on a new held-out period; do not reuse the exposed IF test for selection |
| Template mining / additional contextual features | July train-only context candidates did not win validation; preserve that result. Any new vocabulary/reference and ablation must use fresh preregistered splits, not retune the now-exposed July test |
| Window-size/detection-unit research | Treat changed units as a new target; never present event/window/session metrics as interchangeable |
| Drift detection / adaptive thresholds | Separate drift estimation from labeled test feedback, define update windows and prevent future-data leakage |
| HDFS/session/block datasets | Verify schema/provenance/labels and session boundaries; do not invent block/session IDs for BGL |
| Cross-dataset evaluation and published baselines | Match dataset version, preprocessing, split, unit and metric definitions before claiming a comparable result |
| Explainability | Implement and validate an actual method; keep "Explanation unavailable" until supporting evidence exists, and never infer root cause from score alone |
| Statistical uncertainty and repeated performance measurements | Define independent repeats/workloads; distinguish confidence intervals, seed sensitivity and p50/p95 instead of inventing them from a single run |
| Research paper or conference submission | A reproducible method and credible independent evaluation first; publication is not guaranteed or a release criterion |

## Deferred or conditional classroom additions

Tkinter is conditional on primary lecturer criteria. Dark theme is deferred
because the user's later instruction keeps a white UI. Native macOS execution,
external SMTP and presentation format must be reported as unverified until
actually tested or specified. Flask-WTF, dataset CRUD and validated upload are
implemented release-scope features, not deferred enterprise work. Their software
gates pass; final accepted scope, manual rehearsal and source review/freeze stay in the
[release plan](UNIVERSITY_MVP_V1_PLAN.md). No official lecturer rubric or native
macOS/external SMTP execution is inferred from local tests.
