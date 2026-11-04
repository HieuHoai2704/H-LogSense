# Research library

Initial collection date: 2026-11-03 (Asia/Saigon).

This is a source collection and preliminary screening, not a systematic literature
review or a claim of reproduced results. Papers and dataset metadata were checked
on primary publication, author, institutional, and dataset-provider pages.
All eight cataloged dataset archives have been downloaded locally and their MD5
values match the provider. Eight paper PDFs are available; P03 failed at both the
old mirror (404) and original author host (DNS failure). Raw downloads are ignored
by Git. Local archive inspection and published baseline review are now available.

- [Paper register](PAPERS.md): references, evidence inspected, and project relevance.
- [Dataset catalog](DATASETS.md): eight distinct datasets, paper provenance,
  label semantics, public archive links, and adoption gates.
- [Acquisition manifest](datasets.json): machine-readable download metadata.
- [Measured data preview](DATA_PREVIEW.md): archive/log sizes and actual file structure.
- [Baseline review](BASELINE_REVIEW.md): published metrics and evaluation protocols.
- [Enterprise UI references](ENTERPRISE_UI_REFERENCES.md): six products, official
  visual sources and interaction patterns for the single-workspace design.
- [Download status](download_status.json): dataset verification and initial PDF attempts.
- [Paper status](paper_download_status.json): paper download outcomes including the P03 retry.

## Proposed reading and adoption order

1. Read P01, P07 and P08 before designing evaluation.
2. Use a small BGL subset for the first labeled ingestion/detection workflow.
3. Add HDFS_v1 only after session grouping and evaluation are supported.
4. Audit OpenStack and Hadoop artifacts before using their labels.
5. Reserve Thunderbird for later scale tests.
6. Use Linux, OpenSSH and Apache for ingestion/search demonstrations; these
   releases do not supply anomaly ground truth in the Loghub inventory.

These are recommendations, not implementation changes. Research collection should
not delay the course MVP. Future research work should append dated evidence here;
this collection does not create an automatic recurring search.

## Acquisition gate

Before importing any archive: review its current terms, download outside Git,
verify the published checksum, compute a local SHA-256, inventory archive contents,
check extraction paths and expanded size, inspect the actual label files and
timestamp conventions, and record the exact preprocessing/split configuration.

Published MD5 values in the manifest identify provider artifacts and detect
accidental corruption; they are not a cryptographic authenticity guarantee.
Archive listing/sample scope is recorded in `archive_inventory.json`. Thunderbird
has only first-member inspection; the other seven have complete listings.
Public availability does not imply unrestricted commercial use.
