# BGL Isolation Forest audit and controlled improvement

Measured on 2026-11-04. All results below are actual local measurements, not
published benchmark reproductions. No UI, database schema, source ingestion,
Git remote, push or merge was changed by this task.

## Outcome

On the same new chronological test set of **89,119 observed host-windows**,
the selected IF policy improves F1 from **0.172765 to 0.420182** and average
precision from **0.082801 to 0.184521**. It remains a weak detector for operational
recall: **404 of 658 positive windows are missed**. This experiment does not
approve automatic alerting or establish cross-dataset generalization.

The selected model uses the original five features, 200 trees, max_samples=1024,
seed=42, and a 20,000-window reservoir drawn across the entire training period.
Its native-score threshold is **-0.7587904039488941**, with strict `<` comparison.
The threshold is calibrated using validation labels, maximizing validation F1
subject to an **empirical validation FPR <= 1%**. This is label-blind model fitting
with supervised calibration, not a fully unsupervised end-to-end policy. The FPR
constraint is not a guarantee about unseen data.

## Source audit: verified facts and changes

| Finding | Evidence before this task | Resolution / current status |
|---|---|---|
| Label separation | Window feature SQL selected timestamp/host/Level/message; original BGL labels were queried only by evaluation. The BGL parser keeps label prefixes outside parsed message. | Preserved. Context fitting and IF fitting never receive ground-truth labels. Model-fit input and label-mutation tests added. |
| Detection unit | UTC-aligned nonempty host-window; any original BGL alert among all observed events supplies the window target. | Preserved at 300 seconds for the comparison. No event-level/window-level metric mixing; no point adjustment. |
| Chronological split | First 50% of elapsed time train, next 25% validation, last 25% test; all hosts at one timestamp share a phase. | Shared aligned split helper; exact [start,end) boundaries frozen before feature extraction. |
| First-N sampling | Only the first 20,000 train/validation vectors were used, so later training regimes could be excluded. | V2 uses deterministic algorithm-R reservoir sampling over all training windows. Legacy baseline deliberately retains old first-N semantics. |
| Sparse validation | Prior 100K run had 11,165 train, 60 validation, 79,109 test units. Merely requiring a nonempty validation set was insufficient. | New study has 30,815 validation units and requires at least 20 labeled units of each class. Failure has no test-based fallback. |
| Threshold semantics | Validation score p01 controls a quantile of mixed validation observations; it is not a 1% false-positive guarantee. | Explicit labeled calibration, whole-score-tie handling, deterministic tie-break, finite native threshold and recorded policy. |
| Feature collapse | Different singleton templates with similar Level/message length can map to identical original features. | Added train-only template/host context candidate and tests. It performed worse on validation and **was not selected**. |
| Score direction | Lower `score_samples` was correctly anomalous; evaluation negated native scores only for AP ranking. | Preserved. Scores are not probabilities and are not comparable across detectors. |
| Test exposure | Existing 100K test results were already inspected. | Preserved as historical evidence only. Model selection used validation from the 1M snapshot; final test is a later period beyond the old test. |
| Production path | Legacy policy is executed by the separate worker; predictions/evidence are persisted in MySQL. | Added an opt-in frozen-study replay job using existing tables and worker. Default legacy jobs remain available. |

Audit locations:

- `app/services/window_detection.py`: original streaming window features, legacy
  fitting, batched prediction persistence and full-membership evaluation.
- `app/services/detector_calibration.py`: UTC split, reservoir sampling, metrics,
  constrained validation threshold sweep.
- `app/services/window_features.py`: bounded train-only template frequencies and
  host moments, frozen unknown-template/unknown-host handling.
- `scripts/audit_isolation_forest.py`: preregistration, independent stage gates,
  validation selection and one-time test access.
- `app/services/window_deployment.py`: trusted local artifact verification and
  opt-in MySQL persistence; `app/api/jobs.py`: validated job configuration.

## Data, provenance and split

Source is the actual imported first 1,000,000 lines of Loghub BGL, dataset 3 in
the retained QA/benchmark schema. Frozen input revision: **2000**; maximum event
ID: **1110000**. The existing full-source verification matched all raw bytes,
parsed fields, labels and provenance against the archive prefix, with SHA-256
`51cdd00c485ba0f1af049e3dbce93027e4814432e97bb2e05ddfe69bb3c4bd65`.
See [source verification](../database/measurements/full-source-verification.json).
It is a partial imported archive, not a complete production observation period.

| Phase | UTC [start,end) | Observed host-windows | Events in those windows | Singleton windows |
|---|---|---:|---:|---:|
| Train | 2005-06-03 22:40 → 2005-06-14 20:45 | 390,636 | 772,578 | 269,650 |
| Validation | 2005-06-14 20:45 → 2005-06-20 07:45 | 30,815 | 77,082 | 26,248 |
| Test | 2005-06-20 07:45 → 2005-06-25 18:50 | 89,119 | 150,335 | 39,111 |

Five parsed events have no observed host and are excluded from host-window
modeling; no host was invented. The imported event count remains 1,000,000.
Validation has 1,554 positive and 29,261 negative windows (5.043% positive).
Test has 658 positive and 88,461 negative windows (**0.73834% positive**).
This shift matters when interpreting precision and average precision.

All metrics require an original label for **every observed event** in a unit;
the study fails rather than silently dropping incompletely labeled units.
No empty windows or coverage guarantees are fabricated. A full-window feature
is available only after window end; the existing anomaly anchor is window start,
not a real-time detection timestamp. Unit membership stored for the drawer is
an explicit sample of at most 20 logs, while labels use the entire unit.

## Leakage prevention and experiment protocol

Study ID: `92195e61ec414ff092e20a795670408a`.

1. Wrote an exclusive immutable protocol before extraction or label queries:
   fixed dataset revision, aligned splits, feature candidates, tree/sample grid,
   reservoir seed, FPR budget, candidate tie-break and sensitivity seeds.
2. Streamed parsed events from MySQL in timestamp/ID order into three private
   feature files. Ground-truth fields and raw line label prefixes are excluded.
3. Fitted references and IF on train only. Template normalization is a declared
   deterministic decimal/hex-token replacement, not an inferred Drain model.
   Train-only contextual reference used 845 templates and 33,312 hosts. Its
   statistics never update during validation/test transformation. Applying a
   reference fitted on all training windows to training windows is an offline
   fitted transform, not a causal online training simulation.
4. Queried **validation labels only**, evaluated the preregistered four candidates
   and sensitivity cases, and wrote the selected artifact and selection hashes.
   No test feature file, scores or labels were read during selection.
5. Created the one-time test access marker before reading test labels. Checked
   frozen protocol/manifest/artifact/selection and dataset revision before and
   after evaluation. All three methods used identical test units and labels.
6. Kept selection unchanged after test. Repeat test access or a modified
   manifest/selection/artifact fails closed. Test predictions are retained
   privately with a checksum for independent arithmetic verification.

The observed test is now exposed: it must not be reused to select another model.
The guards protect against accidental reruns within the study; they cannot stop
an operator from deliberately reusing the same period under a different ID.

## Before/after on the same independent test

"Before" below means the **legacy policy retrained on this study's common
training period**, not the previously evaluated 100K model. Legacy IF uses first
20K training units, 100 trees, max_samples=256, seed=42 and first-20K-validation
p01 threshold. Legacy count rule uses training first-20K p99. Legacy thresholds
are -0.7874179733694656 (IF) and 1.0 (count). Legacy floating expm1/log1p count
reconstruction is preserved for faithful comparison.

| Method | Precision | Recall | F1 | AUPRC (AP) | FPR | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---|
| Legacy count rule | 0.013158 | 1.000000 | 0.025974 | 0.101403 | 0.557873 | 658 / 49,350 / 0 / 39,111 |
| Legacy IF | 0.142716 | 0.218845 | 0.172765 | 0.082801 | 0.009778 | 144 / 865 / 514 / 87,596 |
| Selected IF V2 | **0.460980** | **0.386018** | **0.420182** | **0.184521** | **0.003357** | 254 / 297 / 404 / 88,164 |

AUPRC here is sklearn **average precision**, not trapezoidal PR area. The
no-skill AP reference is test prevalence, 0.007383. Undefined metric denominators
are `null`. No results are rounded before evaluation or threshold persistence.
V2 emits 551 anomalies; the legacy IF emits 1,009; the count rule emits 50,008.

The comparison jointly changes sampling, model size and label-informed threshold
selection. It does not isolate a causal contribution from any one change, and
does not show that adding features improved IF. The legacy rule has no labeled
calibration; a separately calibrated rule is a future comparison on new data.

Historical 100K evidence, **not a same-cohort before/after**: legacy IF had
TP=0, FP=5, FN=529, F1=0, AP=0.254564; legacy rule had F1=0.269795. Those figures
must not be compared directly with the later 1M-derived test as a gain estimate.

## Sensitivity analysis: validation only

Each candidate uses the same 20K reservoir and seed=42; each threshold is chosen
on validation under the preregistered FPR constraint.

| Feature set | Trees / samples | Distinct training vectors | Validation F1 | Validation AP | Validation FPR |
|---|---|---:|---:|---:|---:|
| Original 5 | 100 / 256 | 131 | 0.164959 | 0.358828 | 0.008100 |
| Context 9 | 100 / 256 | 2,801 | 0.053796 | 0.297019 | 0.002529 |
| Original 5 (selected) | 200 / 1024 | 131 | **0.465019** | **0.386678** | 0.009501 |
| Context 9 | 200 / 1024 | 2,801 | 0.222871 | 0.318196 | 0.009296 |

The four extra context features are event-weighted train-template surprisal,
unseen-template fraction, standardized host log-count deviation, and an unseen
host indicator. Smoothing and host fallback are explicit and bounded (100K
templates / 50K hosts), with fail-closed resource limits. Increased feature
diversity alone did not improve validation quality.

For the selected model family, threshold sensitivity on validation:

| Threshold policy | Validation F1 | Validation recall | Validation FPR |
|---|---:|---:|---:|
| Validation quantile 0.001 | 0.000000 | 0.000000 | 0.001059 |
| Validation quantile 0.005 | 0.000000 | 0.000000 | 0.005195 |
| Validation quantile 0.01 | 0.048491 | 0.028958 | 0.008783 |
| Validation quantile 0.02 | 0.202159 | 0.132561 | 0.009501 |
| Validation quantile 0.05 | 0.413458 | 0.411197 | 0.030689 |
| sklearn auto offset -0.5 | 0.253776 | 1.000000 | 0.312327 |
| Selected constrained F1 | 0.465019 | 0.357143 | 0.009501 |

Ties matter: the q02 boundary is -0.7587904039488942; the chosen strict threshold
is its next representable float -0.7587904039488941. This includes an entire tied
score group, rather than arbitrarily breaking equal-score observations.
The threshold sweep explicitly processes complete tie groups in O(n log n).
Do not shorten the threshold's decimal representation in deployment.

Additional seeds **17 and 73** were sensitivity checks, not candidates for
selection. Their validation F1 values were 0.465604 and 0.464241, with AP 0.400531
and 0.392178 respectively. Seed 42 remained fixed. No sensitivity candidate was
evaluated on test, and no confidence interval or multi-period robustness claim
is inferred from these two checks.

## Reproduce and use the frozen profile

Install the existing project requirements and provide DATABASE_URL securely in
the process environment. Use a MySQL account authorized for the chosen dataset.
Do not put connection passwords in CLI arguments, reports or Git. Run from the
repository root with `.venv\\Scripts\\python.exe` on Windows or
`.venv/bin/python` on macOS/Linux. The portable command form is:

```sh
python -m scripts.audit_isolation_forest --stage prepare --dataset-id DATASET_ID --study-id NEW_32_HEX_ID
python -m scripts.audit_isolation_forest --stage validate --study-id NEW_32_HEX_ID
python -m scripts.audit_isolation_forest --stage test --study-id NEW_32_HEX_ID
```

Inspect validation and the frozen selection **before** the final command. If
validation is inadequate, stop and design a new experiment without opening test.
Changing the protocol requires a new study and an unexposed evaluation period.

All model binaries, host/template references, cached features, test predictions
and browser screenshots remain under ignored `.local/if_studies/`. **Never load
untrusted joblib/pickle files**; checksums detect changed trusted local files,
not malicious operator-created pickles. No upload path produces these artifacts.

To persist the already frozen profile via the existing authenticated jobs API:

```json
{
  "dataset_id": 3,
  "idempotency_key": "my-unique-frozen-if-replay",
  "configuration": {
    "detector": "isolation_forest",
    "study_id": "92195e61ec414ff092e20a795670408a"
  }
}
```

POST to `/api/v1/detection/jobs` with an authorized analyst/manager/admin session
and CSRF header, then run the existing `python -m scripts.worker --once` outside
Flask requests. Do not add seed/time/window overrides to a frozen-study job.
The worker verifies dataset identity, revision, max event ID, model SHA, feature
SHA, exact feature schema and scope. It persists native scores/predictions in
batches of 200 using the existing FK-scoped tables, immutable version metadata
and observed/reference evidence. An unchanged completed job is idempotent;
interrupted committed batches can resume without duplicate predictions.

This is **replay of the immutable study test interval**, not automatic inference
on future imports. An import changes the input revision and invalidates the
profile snapshot. Jobs without `study_id` still execute the legacy policy. No UI
control was added and no silent default model replacement occurred. IF output
priority remains the existing fixed Medium policy, not calibrated confidence.

## Measurements and verification

Environment: Windows 10 build 26300, Python 3.10.11, sklearn 1.7.2, NumPy 2.2.6,
local MySQL 8.4.7, IF n_jobs=1. Feature extraction took **17.136 seconds**;
validation and all sensitivity fits took **11.555 seconds**; final test SQL,
scoring, evaluation and compressed prediction export took **5.663 seconds**.
Peak process working set of the separate test-stage process was **191.313 MiB**,
not total MySQL/browser/system RAM. These are single measured runs, not p50/p95.

| Check | Status | Measured evidence |
|---|---|---|
| Default test discovery | PASS | 166 discovered, 110 passed, 56 guarded MySQL tests skipped; 8.446s |
| Guarded real MySQL suite | PASS | 63/63, no skips; 56 unique DB tests plus 7 artifact guards; 9.322s |
| New targeted tests | PASS | 10 calibration + 9 features + 11 study gates + 7 artifact guards + 4 DB adapter tests |
| Existing workspace browser regression | PASS | 21 fixture interaction groups; no page errors |
| Existing drawer browser regression | PASS | 13 fixture interaction groups; no page errors |
| Frozen real model persistence | PASS | Run 3: 89,119 predictions, 551 flagged predictions and 551 anomaly outputs |
| Persisted score/decision fidelity | PASS | Every MySQL DOUBLE score and boolean equals the frozen NPZ output exactly |
| Persisted evaluation | PASS | Confusion counts exactly equal; AP/ratios agree within 1e-14 after JSON roundtrip |
| Completed-run retry | PASS | Same run 3; no new predictions/outputs; 0.534s |
| Actual REST/evidence | PASS | Unauthenticated 403, scoped dataset read 200, other dataset 403; evidence DB-159 has actual redacted source provenance/version/threshold |
| Private credential scan / compile / whitespace | PASS | Actual ignored credential values absent from changed files; compileall and git diff --check pass |
| New frozen profile browser E2E | NOT RUN | Actual frozen-profile API/evidence and existing fixture browser workflows tested separately |
| Native macOS / complete BGL archive / repeated p95 | NOT RUN | This run is Windows and the 1M imported prefix only |
| Total MySQL replay runtime | NOT RECORDED | A strict float-equality verification stopped before elapsed was saved; no timing reconstructed |

The first post-persistence verification used exact equality for JSON metric
ratios and stopped at a one-ULP decimal roundtrip difference (254/551). This was
a verification tolerance issue, not a model or classification change. Follow-up
checks compared all native DOUBLE scores and decisions exactly, confusion counts
exactly, and computed metric ratios with relative tolerance 1e-14 and absolute
tolerance 1e-15. No model, threshold, features or selection changed.

Verification results and MySQL replay evidence are recorded in the adjacent
measurement files. Unit guards check exact native-score comparisons, ties,
nonfinite inputs, undefined metrics, temporal alignment, reservoir tail
representation, train-only references, unknown templates/hosts, mutation of
labels/future data, protocol/selection tampering and repeat test access. Real
MySQL tests cover native-score evidence persistence, FK/dataset/revision
isolation, idempotency and interruption after a committed batch followed by
resume. Browser fixture tests exercise the unchanged workspace and drawer;
they do not establish real-data browser quality or screen-reader certification.

### Evidence files

- [Frozen protocol](measurements/if-bgl-2026-11-04/protocol.json)
- [Dataset/feature manifest](measurements/if-bgl-2026-11-04/manifest.json)
- [Validation and complete sensitivity results](measurements/if-bgl-2026-11-04/validation.json)
- [Frozen selection](measurements/if-bgl-2026-11-04/selection.json)
- [Independent test results](measurements/if-bgl-2026-11-04/test-results.json)
- [Source fingerprints](measurements/if-bgl-2026-11-04/code-provenance.json)
- [One-time test access marker](measurements/if-bgl-2026-11-04/test-access.json)
- [Real MySQL replay and REST evidence](measurements/if-bgl-2026-11-04/persistence.json)
- [Verification and explicit NOT RUN scope](measurements/if-bgl-2026-11-04/verification.json)
- [Guarded MySQL suite](measurements/if-bgl-2026-11-04/mysql-tests.json)
- [Workspace browser regression](measurements/if-bgl-2026-11-04/browser-workspace.json)
- [Drawer browser regression](measurements/if-bgl-2026-11-04/browser-evidence.json)

## Remaining limits

- One real BGL prefix and one global temporal split, with substantial prevalence
  and volume shift. No rolling-origin/cross-dataset confidence claim.
- The IF still misses 61.4% of positive test windows and has 297 false positives;
  a window alert is not a confirmed incident or root cause.
- Context features were rejected by validation; label-aware threshold selection
  needs representative trustworthy labels and is not a label-free deployment
  policy. The historical label-blind profile remains explicitly separate.
- Full source time coverage and late-arrival completeness are unknown. No
  fabricated empty host windows, missing coverage or synthetic production metrics.
- The DB replay uses bounded batches but existing ORM per-unit persistence is
  slower than vectorized experimental scoring. It is not a live-throughput SLO.
- Native macOS execution, future-import inference, calibrated priorities,
  online drift detection and external data generalization were NOT RUN here.

The sklearn semantics are documented in
[IsolationForest 1.7](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.IsolationForest.html)
and [average_precision_score](https://scikit-learn.org/1.7/modules/generated/sklearn.metrics.average_precision_score.html).
