# Dataset preview and measured storage

Date: 2026-11-03. Eight archives downloaded; each matches the cataloged provider MD5.
SHA-256 and exact byte counts are in `datasets.json`. Nothing has been fully extracted.

## Storage measured locally

MB = 1,000,000 bytes; MiB = 1,048,576 bytes; GiB = 1,073,741,824 bytes.
Log size is obtained from archive member metadata, not disk space already consumed.

| Dataset | Download (MB) | Log content (MiB) | All listed contents (MiB) | Archive listing |
|---|---:|---:|---:|---|
| BGL | 57.489 | 708.76 | 708.76 | Complete |
| HDFS_v1 | 186.646 | 1504.88 | 1743.36 | Complete |
| OpenStack | 5.395 | 58.60 | 58.60 | Complete |
| Hadoop | 3.416 | 46.34 | 46.35 | Complete |
| Thunderbird | 2016.100 | 30315.69 | 30315.69 | First member only |
| Linux | 0.232 | 2.24 | 2.24 | Complete |
| OpenSSH | 4.597 | 70.02 | 70.02 | Complete |
| Apache | 0.263 | 4.90 | 4.90 | Complete |

Actual downloaded archive total: **2,274,137,596 bytes (2.274 GB / 2.118 GiB)**.

Thunderbird: only the first member header and sample were read, avoiding a full 30 GiB decompression.
Its listed contents value is a lower bound for the archive; it is not a full archive inventory.
HDFS includes preprocessed labels, traces and matrices in addition to its raw log.
Hadoop member sizes differ from the rounded provider inventory; this table preserves measured metadata.

## Data shape

| Dataset | Container / format | Target unit | Fields to extract |
|---|---|---|---|
| BGL | Tagged text | Event alert tag | label, epoch, node, timestamp, component, severity, message |
| HDFS_v1 | Text + CSV + NPZ | Block/session | timestamp, severity, component, block ID, message |
| OpenStack | Three log files + label file | VM instance | timestamp, process, service, request/instance ID, message |
| Hadoop | Application/container log tree | Job/application | timestamp, severity, thread, logger, message |
| Thunderbird | Tagged text | Event alert tag | label, epoch, host, timestamp, process, message |
| Linux | Syslog text | Not supplied | month/day, time, host, process, message |
| OpenSSH | SSH daemon log text | Not supplied | month/day, time, host, PID, authentication message |
| Apache | Web-server error log | Not supplied | timestamp, level, message |

## What was inspected

- BGL: `BGL.log` and archive metadata; first-field tag is a target, not an input feature.
- HDFS: raw log sample and `preprocessed/anomaly_label.csv` header (`BlockId,Label`).
- OpenStack: label file contains four injected-anomaly VM IDs. Do not mark every line in the abnormal file anomalous.
- Hadoop: `abnormal_label.txt` groups application IDs under normal/failure scenarios; preserve the upstream label-quality warning.
- Thunderbird: first log member header and a bounded sample, not full expanded content.
- Linux/OpenSSH/Apache: bounded text samples and complete member listings; no anomaly labels inferred.

No complete row counts were recomputed. Catalog line counts remain provider-reported.
No label distribution, timestamp validity or benchmark metric has been calculated locally.

## Example normalized records (illustrative schema, not an implemented parser)

```json
{
  "dataset": "BGL",
  "event_time": "2005-06-03T00:00:00Z",
  "host": "example-node",
  "severity": "INFO",
  "message": "Example system message",
  "label": 0,
  "label_unit": "event",
  "source_line": 1
}
```

The record above is synthetic. Source timestamps require a verified timezone/epoch policy.
HDFS instead needs a separate block-label table; one event can mention multiple block IDs.

## Next usage steps

1. Keep immutable archives under `data/raw/`, excluded from Git.
2. Use a small BGL fixture for parser tests, then a chronological subset for the demo.
3. Version subset line ranges, hashes and complete-session selection rules.
4. Add HDFS after grouped features and joins are tested.
5. Use the large Thunderbird archive only after streaming and memory limits are measured.

Sources: [Loghub](https://github.com/logpai/loghub), [release v8](https://zenodo.org/records/8196385).
Original provider terms were downloaded as `data/raw/LOGHUB_LICENSE.txt`.
Baseline results are documented separately in [BASELINE_REVIEW.md](BASELINE_REVIEW.md).
