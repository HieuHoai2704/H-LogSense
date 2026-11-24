# Baseline review and proposed LogSense comparison

Date: 2026-11-03. This document records published results, not locally reproduced
performance. Metrics use 0–1 units unless explicitly marked as percentages.
Do not combine the following experiments into a single leaderboard.

## 1. What the algorithms do

| Method | Input and mechanism | Training information | Planned role |
|---|---|---|---|
| Explicit rules | Counts/rates/keywords against configured thresholds | Defined rules; optional normal reference | First explainable operational baseline |
| Isolation Forest | Numerical feature vectors; isolation by randomized trees | Unlabeled training partition | Initial unsupervised detector |
| Logistic Regression | Feature vectors; linear classification | Normal and anomaly labels | Supervised baseline |
| Decision Tree (DT) | Feature vectors; learned feature thresholds | Normal and anomaly labels | Simple nonlinear baseline |
| 1-nearest neighbor (1-NN) | Assign the label of the closest training example | Labeled reference examples | Lightweight research comparator |
| PCA residual | Event-count vectors; reconstruction outside normal subspace | Reference distribution | Later numerical comparator |
| Invariant Mining (IM) | Check learned relations among event counts | Reference event-count behavior | Research comparator |
| DeepLog | LSTM predicts candidate next events | Normal event sequences | Later sequence comparator |
| LogRobust | Semantic representations and attention Bi-LSTM | Labeled sequences in the reviewed comparisons | Later deep comparator |
| NeuralLog | Semantic message representations and Transformer | Labeled sequences | Later parser-free comparator |
| Event novelty / ECVC | Unseen templates / distance between count vectors | Normal sequences | Cheap sanity checks |

These are concise conceptual descriptions. A reimplementation must use the exact
method's publication and artifact, not infer settings from this overview.

## 2. P07 / LightAD — ICSE 2024

Source: [paper](https://boxiyu.github.io/assets/pdf/LightAD.pdf), sections 3.3–4.1,
Table 2 (PDF page 5). Table was visually checked against the downloaded PDF.

### Author-reported F1

| Method | HDFS | BGL | Thunderbird subset |
|---|---:|---:|---:|
| CNN | 0.9867 | 0.7419 | 0.9211 |
| LogRobust | 0.9874 | 0.7520 | 0.9310 |
| NeuralLog | 0.9956 | 0.9641 | 0.9345 |
| KNN, N=1 | 0.9988 | 0.9802 | 0.9970 |
| DT | 0.9990 | N/A | N/A |
| SLFN | 0.9962 | N/A | N/A |

Protocol: HDFS block grouping, random 80/20; supercomputer corpora chronological
80/20. Five runs averaged. Message-based comparison uses evaluation windows and
stride 10. Thunderbird uses 10 million messages, not the full archive.
KNN tokenizes without headers/numerical tokens and uses Jaccard distance for
message-wise data; HDFS uses grouped frequency vectors. DT/SLFN N/A is not zero.
LightAD is the comparison/optimization framework, not a single extra detector.

Project inference: retain a simple supervised comparator. High F1 alone does not
establish generalization to new systems or operational usefulness.

## 3. P06 / NeuralLog — 2021

Source: [paper full text](https://arxiv.org/html/2108.01955v3), section V-B,
Table III. Values below are author-reported F1.

| Method | HDFS | BGL |
|---|---:|---:|
| Logistic Regression | 0.96 | 0.23 |
| SVM | 0.96 | 0.46 |
| Invariant Mining | 0.94 | 0.18 |
| LogRobust | 0.99 | 0.75 |
| Log2Vec | 0.94 | 0.88 |
| NeuralLog | 0.98 | 0.98 |

HDFS: block sessions, random 80/20. BGL: chronological 80/20, 20-message windows,
stride 1. Drain supplies events for count-based baselines; NeuralLog uses semantic
representations and a Transformer. These are sequence metrics, not independent
event metrics. Directly ranking these numbers against section 2 is invalid.

## 4. P08 / Critical Review — FSE 2024

Source: [author PDF](https://www.skopik.at/ait/2024_fse.pdf), sections 4.1–4.3,
Table 2 (PDF page 13), visually checked. Selected F1 **percentages** below refer
to original HDFS (Xu et al.), sequence-identifier grouping.

| Method | Random | Chronological |
|---|---:|---:|
| New event types | 53.9% | 73.3% |
| ECVC | 96.0% | 53.9% |
| ECVC with IDF | 96.5% | 82.9% |
| DeepLog | 85.6% | 86.8% |
| LogAnomaly | 87.4% | 88.1% |

Training uses 1% normal sequences; test includes remaining normal and anomalous
sequences. Random results average 25 runs; chronological results use one run.
The paper sweeps thresholds/candidate sizes to maximize F1; this is not an
independently validated operational threshold. Our experiments must select
thresholds on validation only. Different HDFS versions give different results.

## 5. P04 / DeepLog — CCS 2017

Source: [conference PDF](https://acmccs.github.io/papers/p1285-duA.pdf), section 5.1,
Table 4 (PDF page 10). Exact author-reported counts on the paper's HDFS test split:

| Method | False positives | False negatives |
|---|---:|---:|
| PCA | 277 | 5,400 |
| Invariant Mining | 2,122 | 1,217 |
| TF-IDF comparator | 95,833 | 1,256 |
| N-gram | 1,360 | 739 |
| DeepLog | 833 | 619 |

The paper reports approximately 0.96 F1 for DeepLog. The test unit is a block
session, not a line; DeepLog trains on normal sessions. Default settings include
history 10, candidate count 9, two layers and 64 memory units. Dataset versions
and training supervision differ from sections 2–4; do not compare raw counts
across test populations. OpenStack experiments differ from our public release.

## 6. Other collected papers

| Paper | Baseline relevance | Result handling |
|---|---|---|
| P01 Loghub | HDFS event-count matrix; classical supervised/unsupervised methods | Benchmark figures; see original IV-C, no figure values guessed here |
| P02 HDFS origin | PCA-based console-log mining | Original method/provenance; no new numeric transcription |
| P03 Supercomputer origin | Alert characterization and filtering | PDF acquisition unresolved; not a modern ML leaderboard |
| P05 Drain | Template extraction | Parsing accuracy differs from anomaly F1 |
| P09 Loghub-2.0 | Parser benchmarking | Template annotations do not imply anomaly labels |

## 7. Recommended experiment for this project

This section is a proposed design, not a published result or an implementation.

1. Start with BGL non-overlapping windows and explicitly derive window targets
   from event alert tags. Maintain an event-level comparison as a separate task.
2. Freeze chronological train/validation/test partitions before learned feature
   extraction. Keep complete groups together and isolate boundary-crossing windows.
3. Compare rules, Isolation Forest, Logistic Regression and DT on identical units,
   features and held-out test data. Add 1-NN only as a separately documented track
   if using paper-style token/Jaccard inputs.
4. Exclude target tags and derived labels from every feature. Fit vocabulary,
   transformations and learned parsers on training data only; document novelty.
5. Choose thresholds on validation. Keep anomaly labels out of unsupervised fit.
   State explicitly when a training-normal subset uses ground truth.
6. Report precision, recall, F1, average precision (explicitly named AP rather than
   silently equating it with trapezoidal PR-AUC), false-positive rate, support,
   timing boundaries, hardware, seeds and peak memory.
7. Check duplicate sequences and temporal shifts. Retain raw split results; do
   not search test labels for the best threshold or pick only the best seed.

| Local method | Dataset/version | Unit/split | Local results |
|---|---|---|---|
| Rules | Not run | Pending implementation | Not measured |
| Isolation Forest | Not run | Pending implementation | Not measured |
| Logistic Regression | Not run | Pending implementation | Not measured |
| DT / 1-NN | Not run | Pending implementation | Not measured |

No reviewed scores are acceptance targets for LogSense AI. Reproduction requires
the exact sample, parser, labels, split, supervision and evaluation policy.
