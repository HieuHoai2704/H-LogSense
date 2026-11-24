# Public dataset catalog

Checked: 2026-11-03. Eight distinct corpora, primarily distributed by Loghub.
These are not eight independent repositories. Paper IDs refer to [PAPERS.md](PAPERS.md).

## Inventory

Provider-reported raw sizes, not compressed download sizes or local measurements.

| ID | Dataset | Lines | Raw size | Paper provenance | Recommended role |
|---|---|---:|---:|---|---|
| D01 | BGL | 4,747,963 | 708.76 MiB | P01, P03, P07 | Initial labeled workflow |
| D02 | HDFS_v1 | 11,175,629 | 1.47 GiB | P01, P02, P04, P07 | Session benchmark |
| D03 | OpenStack | 207,820 | 58.61 MiB | P01, P04 | Cloud-log extension |
| D04 | Hadoop | 394,308 | 48.61 MiB | P01, P08 | Job-level study after label audit |
| D05 | Thunderbird | 211,212,192 | 29.60 GiB | P01, P03, P07 | Later scale test |
| D06 | Linux | 25,567 | 2.25 MiB | P01 | Parser/explorer demo |
| D07 | OpenSSH | 655,146 | 70.02 MiB | P01 | Authentication-log ingestion |
| D08 | Apache | 56,481 | 4.90 MiB | P01 | Web-server error-log ingestion |

Source: [Loghub inventory](https://github.com/logpai/loghub).
P01 lists the corpora; P08 names commonly used anomaly benchmarks. A provenance
entry does not mean every paper trained a detector on every listed corpus.

## Labels, formats and processing gates

### D01 — BGL

- [Provider documentation](https://github.com/logpai/loghub/tree/master/BGL).
- Text logs have alert tags in the first field: `-` means non-alert; other tags
  identify alert categories. Preserve tags as targets, exclude them from features.
- Source evidence: provider README and P03. Proposed window target: any alert in
  a non-overlapping window; report this as a derived window label, not event F1.
- Inspect epoch/text timestamp agreement and timezone before normalization.

### D02 — HDFS_v1

- [Provider documentation](https://github.com/logpai/loghub/tree/master/HDFS#hdfs_v1).
- Ground truth is normal/anomaly per block trace; join using block IDs.
- Do not independently split lines belonging to the same block. Preserve all
  extracted block IDs when messages reference multiple blocks.
- Record missing labels and incomplete sessions. A truncated line subset may
  break sessions, so create benchmark subsets from complete groups.

### D03 — OpenStack

- [Provider documentation](https://github.com/logpai/loghub/tree/master/OpenStack).
- CloudLab logs include normal execution and injected failures. Local inspection
  identifies VM-instance annotations; event-to-instance mapping still needs a parser.
- Local inspection found four injected-anomaly VM IDs in `anomaly_labels.txt`.
  P04 uses VM-instance sessions. Reconstruct identifiers and scenarios; do not
  automatically equate an entire file/scenario label with independent event truth.
- Release scale differs from P04; treat exact reproduction as unresolved.

### D04 — Hadoop

- [Provider documentation](https://github.com/logpai/loghub/tree/master/Hadoop).
- WordCount/PageRank runs include injected failures; `abnormal_label.txt`
  describes job IDs. Keep each job within a single partition.
- [Issue #56](https://github.com/logpai/loghub/issues/56) reports potential incorrect
  labels. A maintainer added a warning without reproducing the investigation.
  Do not assume a closed issue means the archive has corrected labels.
- Preserve original labels and separately version any independently audited fixes.

### D05 — Thunderbird

- [Provider documentation](https://github.com/logpai/loghub/tree/master/Thunderbird).
- Alert/non-alert tagging follows the first-field convention described by the
  provider. Exclude that field from model input.
- Use streaming reads and chronological segments. Retain original line ranges;
  do not apply a paper's subset metrics to the full release.

### D06–D08 — Linux, OpenSSH and Apache

- [Linux](https://github.com/logpai/loghub/tree/master/Linux),
  [OpenSSH](https://github.com/logpai/loghub/tree/master/OpenSSH),
  [Apache](https://github.com/logpai/loghub/tree/master/Apache).
- The provider inventory does not mark these as anomaly-labeled. Do not invent
  precision/recall/F1 using severity or keywords as supposed ground truth.
- Inspect source timestamp conventions, especially missing year/offset fields;
  explicit assumptions belong in import metadata.
- Apache here is a web-server **error** log corpus, not an access-log benchmark.

## Download sources and artifact identity

All links below are published by the [versioned Zenodo release v8](https://zenodo.org/records/8196385).
All eight archives were downloaded and matched provider MD5; none was fully
extracted. See [measured sizes](DATA_PREVIEW.md). The table below preserves the
published compressed sizes in provider decimal units.

| Dataset | Public archive | Compressed size |
|---|---|---:|
| BGL | [BGL.zip](https://zenodo.org/records/8196385/files/BGL.zip?download=1) | 57.5 MB |
| HDFS_v1 | [HDFS_v1.zip](https://zenodo.org/records/8196385/files/HDFS_v1.zip?download=1) | 186.6 MB |
| OpenStack | [OpenStack.tar.gz](https://zenodo.org/records/8196385/files/OpenStack.tar.gz?download=1) | 5.4 MB |
| Hadoop | [Hadoop.zip](https://zenodo.org/records/8196385/files/Hadoop.zip?download=1) | 3.4 MB |
| Thunderbird | [Thunderbird.tar.gz](https://zenodo.org/records/8196385/files/Thunderbird.tar.gz?download=1) | 2.0 GB |
| Linux | [Linux.tar.gz](https://zenodo.org/records/8196385/files/Linux.tar.gz?download=1) | 232.0 kB |
| OpenSSH | [SSH.tar.gz](https://zenodo.org/records/8196385/files/SSH.tar.gz?download=1) | 4.6 MB |
| Apache | [Apache.tar.gz](https://zenodo.org/records/8196385/files/Apache.tar.gz?download=1) | 262.9 kB |

Published MD5 values are recorded in [datasets.json](datasets.json); verify them
after download and additionally calculate SHA-256 for local version tracking.

## Terms and reproducibility

Zenodo permits research/academic use under its stated notice, asks for repository
attribution and applicable paper citation, and requires retaining the notice with
copies. Do not replace these terms with an assumed MIT/CC license or infer
commercial permission. Consult the release notice and original data provenance.

Downloads are in `data/raw/` outside version control. Preserve immutable originals,
parser version, file hash, split manifests and sampling ranges. Streaming and chunked
features avoid requiring the expanded corpus plus all intermediates in RAM.

For experiments, define event/window/session targets first, partition time/groups
before fitting any vocabulary, scaler or learned parser, then tune thresholds on
validation only. Drop or isolate groups/windows crossing split boundaries.
Report class support and undefined metrics explicitly. Benchmark reproducibility
and operational usefulness must be assessed separately.
