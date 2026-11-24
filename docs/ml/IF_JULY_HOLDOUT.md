# Later July BGL holdout and reusable validated IF profile

Measured on 2026-11-04. The earlier 100K June test and June20-25 test were already exposed. This experiment preregistered a later July period before inspecting its validation labels or test scores. All model/threshold choices below were frozen before the July test was opened.

## Outcome and comparison scope

The selected profile achieves precision **22.52%**, recall **55.43%**, F1 **0.3203**, average precision **0.2656** and FPR **0.2037%** on 172,529 observed parsed host-windows. It misses 82 of 184 positive windows and produces 351 false positives. It is experimental, not an operational alert-quality guarantee.

**Do not describe this as same-test recall 0→55%.** On this new July test, the legacy IF instead gets recall 100% while flagging 101,532 windows and producing 58.81% FPR. The comparison improves precision/F1/AP/FPR with a recall tradeoff. The historical zero-recall June result is a different cohort and remains unchanged.

| Method on the SAME July test | Precision | Recall | F1 | AP | FPR | TP / FP / FN / TN |
|---|---:|---:|---:|---:|---:|---|
| Legacy count rule | 0.002361 | 0.038043 | 0.004446 | 0.029312 | 0.017163 | 7 / 2958 / 177 / 169387 |
| Legacy IF policy | 0.001812 | 1.000000 | 0.003618 | 0.025977 | 0.588053 | 184 / 101348 / 0 / 70997 |
| Validation-selected IF | 0.225166 | 0.554348 | 0.320251 | 0.265610 | 0.002037 | 102 / 351 / 82 / 171994 |

AP means sklearn average precision, not trapezoidal PR area. Rankings use negative native IF score because lower score_samples is more anomalous. No point adjustment or event/window metric mixing is used. Test positive prevalence is 0.10665%; undefined denominators remain null.

## Data, chronology and provenance

Source: actual immutable Loghub BGL archive, 4,747,963 physical lines and 743,185,031 uncompressed bytes. The full member and selected slice are checksummed. No million-event database import, application-schema change or raw source replacement was needed; this controlled experiment used bounded private disk caches.

| Phase, UTC [start,end) | Selected raw rows | Parsed events with host | Observed host-windows | Singleton windows |
|---|---:|---:|---:|---:|
| Train: July1→July14 | 835,354 | 835,053 | 580,095 | 339,881 |
| Validation: July14→July21 | 403,295 | 403,051 | 232,151 | 70,649 |
| Test: July21→July28 | 313,651 | 313,594 | 172,529 | 39,300 |

All dates are 2005 and all boundaries UTC 00:00, aligned to 300-second windows. Test starts strictly later than the exposed June 25T18:50 UTC end. Windows sharing one timestamp cannot cross phases. Raw epoch is authoritative; printed timestamps are preserved/validated by the existing parser, not used as the split clock.

**Availability qualification:** the existing parser rejected 537 selected nine-field lines as invalid_field_count: 278 train, 219 validation, 40 test. Another 65 events had no supplied host: 23 train, 25 validation, 17 test. These rows are explicitly excluded; no message/host was invented. This is a target over observed **parsed host-windows**, not a claim of complete raw-source-window ground truth. Parser rejection is an observed classification, not proof that the upstream data is corrupt. No parser/cohort/model change was made after test exposure.

Labels used for a unit are original BGL tokens: any non-dash alert among ALL its observed parsed events. Separate validation/test passes count labels for exactly the same host/time bucket and require the count to equal the feature count. No silently unlabeled unit is dropped. Unknown source coverage remains unknown.

The source was checked for chronological reversals (actual count 0). An external 50K-event chunk sort and heap merge still enforce timestamp/source-line ordering and reject duplicated physical references; a dedicated unit test proves correct aggregation when input is out of order. Offline sample_ids are **physical source lines**, not MySQL event IDs.

Archive SHA-256: `d67fd82a711aea0157a9b83175892c6ee60e384a2ddf5bc51f39118453816da8`.
Full BGL member SHA-256: `666130b15ef44eb32fd02bd053e6c6e007c37696b5e7e8b9d8e45b729876a5d2`.
Selected raw slice SHA-256: `53be3e731ac024aa1782f816dfb7c636646035abe0350eb0a4d92544b9b7099c`.

## Audit: features, fitting, score direction and threshold

Five base features are log1p event count, supplied high-severity fraction, distinct-template fraction, dominant-template fraction and log1p mean message length. The deterministic decimal/hex normalization is declared explicitly; it is not an inferred Drain parser. Features never include the original label token, raw line prefix, absolute timestamp, physical line number, event ID or a numeric host identifier. Host is used for grouping; candidate context references use train-only host statistics.

The candidate context adds mean train-template surprisal, unseen-template fraction, standardized host log-count deviation and an unseen-host flag. Its vocabulary, counts and moments are fitted on train only and never updated by validation/test. The reference used 2,349 templates and 34,075 hosts. Context candidates did not win validation and were not deployed.

All fits remain label blind and may contain real anomalies; training was not filtered using labels. Legacy IF uses the first 20K chronological train units, 100 trees, max_samples 256, seed 42, and the first 20K validation native-score p01 threshold. Legacy count uses training first 20K count p99. These are faithful old policies retrained on the common new period, not the old June artifacts.

New candidates use deterministic reservoir sampling of 20K units across all 580,095 train windows. Four preregistered base/context × 100/256 or 200/1024 tree/sample combinations are calibrated on validation only. Threshold maximizes validation F1 under an empirical FPR<=1% budget; ties use AP, lower FPR then candidate ID. Whole score ties and strict comparison are handled explicitly. This calibration uses validation labels; it is not a wholly unsupervised end-to-end system.

Selected model: **base features, 100 trees, max_samples 256, seed 42**, threshold **-0.7700419045395783**, strict native `<`. Both the sampling and threshold policy change; this comparison does not isolate one causal contribution. score_samples is not probability. contamination=auto governs sklearn offset but the deployed classification uses the separately frozen validation threshold; no contamination value was tuned on test.

| Validation candidate | F1 | AP | FPR |
|---|---:|---:|---:|
| base-100-256 | 0.398046 | 0.465184 | 0.009686 |
| context-100-256 | 0.255171 | 0.279770 | 0.009407 |
| base-200-1024 | 0.326218 | 0.374254 | 0.003249 |
| context-200-1024 | 0.214694 | 0.256657 | 0.007283 |

Validation has 2,862 positive and 229,289 negative units. Test has 184 positive and 172,345 negative units. This prevalence change limits how precision/AP generalize.

## Sensitivity and frozen holdout discipline

Threshold sensitivity used only validation: quantiles 0.001/0.005/0.01/0.02/0.05 and sklearn auto offset. The table below is the selected family, not additional test evaluations.

| Validation threshold policy | F1 | Recall | FPR |
|---|---:|---:|---:|
| q=0.001 | 0.000000 | 0.000000 | 0.001016 |
| q=0.005 | 0.000000 | 0.000000 | 0.002530 |
| q=0.01 | 0.299680 | 0.245283 | 0.004889 |
| q=0.02 | 0.413870 | 0.521314 | 0.012456 |
| q=0.05 | 0.513824 | 1.000000 | 0.023621 |
| auto offset | 0.062743 | 1.000000 | 0.372918 |

Seeds 17 and 73 were preregistered sensitivity checks on validation only; seed 42 remained fixed. They were not candidates for test-driven selection:

| Validation sensitivity seed | F1 | AP | FPR |
|---|---:|---:|---:|
| 17 | 0.447959 | 0.471095 | 0.009987 |
| 73 | 0.381573 | 0.479498 | 0.009734 |

Protocol was exclusively written at 2026-11-04T12:39:01Z before feature extraction/label queries; selection froze at 12:41:38Z before the one-time test marker. Selection, source, feature and binary hashes were verified before test. Test now exposed: do not reuse July 21-28 for future model selection. Repeat-test/reselection guards fail closed; deliberate reuse under another ID still requires human research discipline.

## Reusable inference profile (no retraining)

`app/services/validated_if.py` reuses the actual frozen model. model_card() reports source-qualified metrics, native direction, features, calibration and cutoff without unpickling. load_frozen_model() verifies contained fixed paths and protocol/manifest/validation/selection/artifact checksums before loading a trusted local joblib file. Binary feature count/tree count/seed must match the frozen contract. Hashes detect changes to trusted artifacts; they do not make untrusted pickle safe. No upload path is a model-loading path.

run_validated(engine,dataset_id,job_key,configuration) accepts exactly:
```json
{
  "detector": "isolation_forest",
  "model_id": "f3e5a88403ab48fb84ea36904214e867"
}
```

Inference streams the actual MySQL dataset in timestamp/ID order, builds the same 300-second host-window features and persists batches of 200 through the existing prediction/evidence machinery. It **never** persists offline study source-line IDs as UnitEvent membership. Dataset revision, maximum event ID, cache SHA, model version and eligible time range are frozen for retry. The stable logical detector is host-window-if-validated and version is the frozen selection hash. No new schema/framework or automatic retraining is introduced.

Only closed windows with start **at/after 2005-07-21T00:00:00Z** are eligible. Earlier events/units, future/open bins and missing hosts are counted/excluded. A wholly earlier June dataset fails clearly; applying a July-trained model to June would introduce temporal leakage. Do not silently apply this model to the historical 100K demo.

Input cache is generated from actual DB rows, not the offline study cache. Row locks and revision checks stop changed inputs; committed batches resume without duplicate predictions. Native score, threshold, feature evidence and version remain inspectable. Explanation unavailable is retained; no importance or root cause is fabricated.

For uploaded logs without independently trusted Loghub labels, local evaluation may have 0 eligible ground-truth units and null metrics. The separate July model-card metrics must not be relabeled as performance on the uploaded dataset. Model-card quality is specific to the observed parsed target and period.

## Measured work and verification

Feature preparation: **42.479s**; validation and sensitivity fits **28.149s**; final test **9.819s**. Separate final test process peak working set **179.66 MiB** on Windows / Python 3.10.11 / sklearn 1.7.2 / NumPy 2.2.6. These are single measured runs, not p50/p95 or complete-system memory.

New pure tests: 7/7 PASS for fresh chronological bounds, out-of-order merge/exact count, label mutation invariance, duplicate references, phase gates and finite/count matrices. Five additional inference artifact guards pass. Six guarded MySQL tests in test_validated_if_mysql.py cover native scores/actual membership, no invented GT, pre-cutoff rejection, dataset/revision isolation, future/missing-host exclusions, committed-batch interruption/resume and the first-window default time extent. All six passed in the final full guarded run: **123/123 tests, zero skips, 31.979s**. The suite also includes overlapping pure guards; this is not 123 distinct database cases. A default discovery skip remains NOT RUN until the separate guarded execution.

### Actual BGL-to-DB inference proof

`scripts/qa/verify_validated_if_bgl.py` created a separate owned QA schema and
ingested exact original source bytes for 20 complete singleton windows already
flagged by the frozen model. These are deliberately selected functional examples,
**not an unbiased dataset or another accuracy evaluation**. Selection used the
already frozen predictions, not ground-truth labels. The original independent
test measurements above were not rerun, fitted or changed.

The proof persisted 20 actual MySQL predictions and 20 outputs. Every native
score exactly equals its original frozen offline score, membership references
actual dataset event IDs, and Timeline/Evidence/CSV agree on all 20 records.
Import took 0.070s and inference 0.193s in this tiny functional sample; those
numbers are not large-data performance claims. Raw source-line origin and bytes
are retained privately with checksums. The slice is actual July 25 BGL data,
after the model's calibration cutoff.

This exercise exposed a separate P1 API defect: the default time range began at
the first raw timestamp (03:10:30), excluding all outputs anchored at window
start (03:10:00). The default bound now includes completed output anchors; an
explicit user's `[start,end)` range is unchanged. Read-only rechecking on the
same persisted outputs now returns 20 by default and matching CSV, with no
rescoring or parameter changes. The initial zero-count finding remains in the
proof report and a dedicated MySQL regression covers default, explicit and empty
dataset behavior.

[Actual DB profile proof](measurements/if-july-holdout-2026-11-04/actual-db-profile-proof.json)

## Evidence and reproduction

```text
python -m scripts.ml.audit_if_holdout --stage prepare
python -m scripts.ml.audit_if_holdout --stage validate
python -m scripts.ml.audit_if_holdout --stage test
```

This recorded study is single-use and retained. Do not delete its markers or create a new study ID to retune against the exposed July test. Source/cache/model/prediction binaries remain ignored under .local; public reports contain metadata and measurements only. Use a genuinely new period for another selection experiment.

- [Frozen protocol](measurements/if-july-holdout-2026-11-04/protocol.json)
- [Manifest and source counts](measurements/if-july-holdout-2026-11-04/manifest.json)
- [Validation and sensitivity](measurements/if-july-holdout-2026-11-04/validation.json)
- [Selection](measurements/if-july-holdout-2026-11-04/selection.json) / [test access](measurements/if-july-holdout-2026-11-04/test-access.json)
- [Independent test](measurements/if-july-holdout-2026-11-04/test-results.json)
- [Parser/host availability qualification](measurements/if-july-holdout-2026-11-04/availability-audit.json)
- [Deployable model card](measurements/if-july-holdout-2026-11-04/model-card.json)
- [Actual BGL-to-MySQL inference and evidence](measurements/if-july-holdout-2026-11-04/actual-db-profile-proof.json)
- [Historical June IF audit](ISOLATION_FOREST_AUDIT.md)
