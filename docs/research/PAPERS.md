# Paper register

Screened: 2026-11-03. Notes below distinguish source findings from proposed
LogSense AI applications. No published performance is claimed as our own.

## P01 — Loghub

- Title: **Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics**.
- Authors: Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu.
- Venue: ISSRE 2023; arXiv first submission 2020, inspected version v3 (2023).
- [Paper](https://arxiv.org/abs/2008.06448v3) · [Full text](https://arxiv.org/html/2008.06448v3).
- Inspected: dataset inventory/Table I, usage and benchmark sections.
- Evidence: collects system-log corpora for parsing and anomaly analysis.
- Project use (proposal): provenance anchor for D01–D08. A shared distributor
  does not make these eight corpora eight independent providers.

## P02 — HDFS origin

- Title: **Detecting Large-Scale System Problems by Mining Console Logs**.
- Authors: Wei Xu, Ling Huang, Armando Fox, David Patterson, Michael I. Jordan.
- Venue: SOSP 2009.
- [Author-hosted paper](https://people.eecs.berkeley.edu/~jordan/papers/xu-etal-sosp09.pdf).
- Inspected: paper identity, abstract; dataset linkage additionally checked in
  [Loghub HDFS documentation](https://github.com/logpai/loghub/tree/master/HDFS).
- Evidence: console-log mining and system problem detection; HDFS provenance.
- Project use (proposal): study session count features and a PCA comparison after
  the initial rule-based/Isolation Forest workflow.

## P03 — Supercomputer log origin

- Title: **What Supercomputers Say: A Study of Five System Logs**.
- Authors: Adam Oliner, Jon Stearley. Venue: DSN 2007.
- [Publisher record](https://ieeexplore.ieee.org/document/4273008/) · [Primary data description](https://www.usenix.org/cfdr-data#hpc4).
- Inspected: USENIX HPC4 description and BGL/Thunderbird provider citations;
  not a complete reading of the original paper.
- Download attempts: old mirror returned 404; original author URL
  `https://adam.oliner.net/files/oliner_dsn_2007.pdf` failed DNS resolution.
  No local PDF is claimed for this paper.
- Evidence: alert-tagged logs from multiple supercomputers; alert detection
  differs from establishing physical failures or root causes.
- Project use (proposal): preserve alert-category provenance and avoid treating
  benchmark alert labels as confirmed incident causes.

## P04 — DeepLog

- Title: **DeepLog: Anomaly Detection and Diagnosis from System Logs through Deep Learning**.
- Authors: Min Du, Feifei Li, Guineng Zheng, Vivek Srikumar. Venue: CCS 2017.
- [Conference paper](https://acmccs.github.io/papers/p1285-duA.pdf).
- Inspected: architecture and section 5.1.2 (datasets/setup).
- Evidence: sequence modeling; groups HDFS by block and OpenStack by instance.
  Its OpenStack experiment reports 1,335,318 entries, unlike the Loghub release
  inventory's 207,820. HDFS counts also differ between paper and release.
- Project use (proposal): future sequence baseline; do not claim reproduction
  using a similarly named archive without reconciling the version and protocol.

## P05 — Drain

- Title: **Drain: An Online Log Parsing Approach with Fixed Depth Tree**.
- Authors: Pinjia He, Jieming Zhu, Zibin Zheng, Michael R. Lyu. Venue: ICWS 2017.
- [Author page](https://pinjiahe.github.io/publication/2017-ICWS) · [Paper](https://pinjiahe.github.io/files/pdf/research/ICWS17.pdf).
- Inspected: abstract and method overview; [official implementation documentation](https://github.com/logpai/logparser/tree/main/logparser/Drain).
- Evidence: online template extraction with a fixed-depth tree.
- Project use (proposal): add template parsing when features need it; distinguish
  extracting timestamp/severity fields from discovering message templates.

## P06 — NeuralLog

- Title: **Log-based Anomaly Detection Without Log Parsing**.
- Authors: Van-Hoang Le, Hongyu Zhang. Year: 2021 (inspected arXiv v3).
- [Paper](https://arxiv.org/abs/2108.01955v3) · [Full text](https://arxiv.org/html/2108.01955v3).
- Inspected: evaluation section V-B and Table III; local PDF downloaded.
  Detailed reproduction remains pending.
- Evidence: studies parsing errors and proposes semantic representations with
  Transformer classification.
- Project use (proposal): retain original logs so future parser-free experiments
  can be compared with template-based methods. Not an MVP dependency.

## P07 — LightAD / classical ML comparison

- Title: **Deep Learning or Classical Machine Learning? An Empirical Study on Log-Based Anomaly Detection**.
- Authors: Boxi Yu et al. Venue: ICSE 2024.
- [Author-hosted paper](https://boxiyu.github.io/assets/pdf/LightAD.pdf) · [DOI](https://doi.org/10.1145/3597503.3623308).
- Inspected: abstract, section 3.3/Table 1 and evaluation discussion.
- Evidence: compares simpler methods with deep learning; uses HDFS, BGL,
  Thunderbird, Spirit and Liberty, with subsets for the large corpora.
- Project use (proposal): compare simple baselines and audit repeated sequences;
  do not confuse a paper's selected subset with an entire released dataset.

## P08 — Dataset validity critique

- Title: **A Critical Review of Common Log Data Sets Used for Evaluation of Sequence-Based Anomaly Detection Techniques**.
- Authors: Max Landauer, Florian Skopik, Markus Wurzenberger.
- Venue: Proceedings of the ACM on Software Engineering, 1(FSE), 2024.
- [Institutional record and abstract](https://publications.ait.ac.at/en/publications/a-critical-review-of-common-log-data-sets-used-for-evaluation-of-/) · [DOI](https://doi.org/10.1145/3660768).
- Inspected: institutional metadata and downloaded author PDF, sections 4.1–4.3
  and Table 2; table visually checked. Reproduction remains pending.
- Evidence: questions whether common datasets actually require sequential
  reasoning; names HDFS, BGL, Thunderbird, OpenStack and Hadoop.
- Project use (proposal): require non-sequential baselines before making claims
  about benefits of sequence models. Dataset familiarity is not validity evidence.

## P09 — Loghub-2.0 / parser evaluation

- Title: **A Large-Scale Evaluation for Log Parsing Techniques: How Far Are We?**
- Authors: Zhihan Jiang et al. Venue: ISSTA 2024; inspected arXiv v2.
- [Paper](https://arxiv.org/abs/2308.10828v2).
- Inspected: abstract and venue metadata.
- Evidence: introduces large-scale annotated parser benchmarks and investigates
  rare-event parsing performance.
- Project use (proposal): evaluate template extraction separately; template
  annotations are not automatically anomaly labels.

## Research questions to investigate, not novelty claims

- How much does a chronological split change results versus a session-grouped split?
- Which gains remain after auditing duplicate sequences and label-derived features?
- How do fixed and adaptive thresholds behave over time with a fixed alert budget?
- How much parser behavior changes downstream anomaly scores?

A later full review should record exact sections, artifacts, split definitions,
compute requirements and reproduction status for each selected method.
