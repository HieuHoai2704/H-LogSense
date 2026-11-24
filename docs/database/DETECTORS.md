# First persisted detector baselines

`app/services/detection.py` operates on **event units**. It never queries
`ground_truth_labels`. It does not feed raw BGL prefixes, labels, event IDs, host
IDs or absolute time into the model. Native scores remain detector-specific.

| Detector | Features used | Threshold | Meaning |
|---|---|---|---|
| Versioned severity rule | supplied Level in ERROR/FATAL/SEVERE/FAILURE | indicator >= 1 | configured rule; fixed High priority |
| Isolation Forest | message character count, token count, high-severity indicator | `score_samples < offset_` | lower native score is more abnormal; fixed Medium priority |

Priority policies are explicit initial configuration, not learned/calibrated
score conversion. Scores are not probabilities, and the two algorithms are not
comparable on a shared scale. A message containing the word `error` at INFO does
not automatically match the severity rule.

Isolation Forest trains on the first N events ordered by UTC timestamp then ID,
with N bounded to 16..20,000 (default 1,000). Only later events are scored. This
is a chronological holdout; training may contain anomalies because labels are
not consulted. Constant/low-diversity training can produce a weak or degenerate
model; distinct training-vector count is recorded. No automatic label-driven
threshold search, template mining or research-quality performance is claimed.

Model configuration records sklearn/Python versions, random seed, tree/sample
counts, feature schema, native threshold, training boundary and count. A local
joblib artifact and SHA-256 are persisted privately; **never load untrusted
pickle/joblib files**. Version identity includes the fitted artifact hash. The
stable detector key, immutable model/rule version and dataset/input-revision run
are separate entities.

Inference is batched. Each committed batch updates evaluated-unit counters and
outputs atomically under the dataset lock. A revision change stops the run and
marks it failed; failed/running runs are not published through the private API.
Only flagged outputs and their event-unit/membership rows are materialized;
evaluated-unit counts do not equal materialized unit or anomaly row counts.
Restart/resume of detector execution itself is not implemented; use a new run.

```text
python -m scripts.run.database detect --dataset DATASET_ID --kind rule
python -m scripts.run.database detect --dataset DATASET_ID --kind isolation_forest --train-size 10000
```

Evidence stores actual feature values, comparison and threshold. Rule evidence
states the configured match. ML says **Explanation unavailable**; no feature
importance or root cause is fabricated. An authorized evidence API returns the
original parsed event, raw provenance, redacted raw page, version and evidence.

The existing Drawer UI now requests the same contract through a MySQL adapter for
`source=db-ID`. It is browser-tested with actual persisted data. Demo sources keep
their original synthetic API behavior. Window raw evidence is an actual recorded
sample and is labeled as a sample, not the entire detection unit.

`scripts.qa.verify_detectors` evaluates completed runs using original BGL labels,
event-level TP/FP/FN/TN, no point adjustment. For ML it excludes the precise
training boundary. Undefined precision/recall is null, not invented zero/100%.
Metrics on a contiguous 100K prefix are a case study, not a comparable published
benchmark or a claim of generalization.

## Observed host-window detectors

`window_detection.py` constructs UTC-aligned windows per supplied host, streaming
events in timestamp/ID order into a private feature file. Features are log1p event
count, high-severity fraction, distinct-template fraction, dominant-template
fraction and log1p mean message length. Template policy is explicit deterministic
decimal/hex token replacement followed by SHA-256; it is not a fabricated Drain
template or model explanation. Unknown hosts are not replaced with invented IDs.

Time is split globally into first 50% train, next 25% validation and last 25% test.
Host windows sharing the same timestamp cannot straddle phases. At most the first
20,000 train and validation vectors are used. No labels are read while computing
features, fitting, selecting thresholds or predicting. Rule threshold is training
count p99; IF threshold is validation native-score p01. Test labels never tune the
threshold. A sparse prefix can make these periods highly unrepresentative.

All test-window scores and boolean predictions are persisted, including normal
units. Config records feature/template policy, boundaries, input revision/max ID,
seed, sklearn version and private artifact/file hashes. Each unique run/unit has
one prediction; retry reuses committed predictions and does not duplicate output.
Jobs run in the separate worker, hold connection-owned leases and update progress.
Failed/interrupted work can be explicitly requeued only when its worker lease is
free. An input/configuration change requires a new run.

Window labels are computed **after** inference: any original BGL alert among all
observed imported events in that host/window. Eligibility requires a label for
every observed event. This is an observed-window target, not a claim that the
partial archive provides complete time coverage. Precision, recall, F1, FPR and
average-precision AUPRC use only the test units. AUPRC is sklearn average precision,
not trapezoidal interpolation. Undefined metrics remain null.

See `measurements/window-detectors.json`. On the measured 100K prefix the test
split has 79,109 host windows. Rule: TP=92/FP=61/FN=437; IF: TP=0/FP=5/FN=529.
The IF threshold gives zero recall despite nonzero ranking average precision.
Neither baseline is approved for operational alerting. Do not compare these
numbers with the earlier **event-level** evaluation as if they used the same unit.

## Controlled IF V2 audit and opt-in replay

See [the BGL IF audit](../ml/ISOLATION_FOREST_AUDIT.md) for the preregistered
1M-prefix study, train/validation/test boundaries, validation-only calibration
and sensitivity analysis, independent test before/after, and frozen-study job
configuration. V2 model fitting remains label blind; its threshold explicitly
uses validation labels. Context features were tested but not selected. The
frozen profile replays its fixed test snapshot through existing MySQL evidence
tables; it does not silently replace the legacy default or score future imports.
