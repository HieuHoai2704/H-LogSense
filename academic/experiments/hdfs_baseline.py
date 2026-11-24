"""Analyze the full Loghub HDFS_v1 archive as disjoint block sessions."""

import argparse
import json
from pathlib import Path

from academic.experiments.hdfs_analysis import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory for SQLite, predictions and report")
    parser.add_argument("--max-validation-fpr", type=float, default=0.01)
    args = parser.parse_args()
    report = run(args.archive, args.output, budget=args.max_validation_fpr, progress=lambda line: print(line, flush=True))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
