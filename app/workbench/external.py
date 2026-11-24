"""Read-only previews for external formats with explicit evaluation units."""

from collections import Counter
import csv
from datetime import datetime
from io import StringIO
import json
import re

from app.parsers.hdfs import BLOCK, parse_hdfs

from .files import WorkspaceError

# Anchored at the timestamp; the optional "nova.log.1" source token is split off first. A single
# optional (\S+\.log\S*) group backtracked quadratically on long tokens (a 1 MiB line took minutes).
OPENSTACK = re.compile(r"(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:\.\d+)?)\s+(\d+)\s+(\w+)\s+(\S+)\s+(.*)")
FIRST_TOKEN = re.compile(r"(\S+)\s+(.*)")
MAX_RECORD_CHARS = 64 * 1024
INSTANCE = re.compile(r"\[instance:\s*([a-fA-F0-9-]{36})\]")
REQUEST = re.compile(r"\breq-[a-fA-F0-9-]{36}\b")


def parse_line(line, format_name):
    if format_name == "jsonl":
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError
        return structured(row)
    if format_name == "hdfs":
        item = parse_hdfs(line)
        return {
            "timestamp_raw": item.timestamp_raw,
            "thread": item.thread,
            "level": item.level,
            "component": item.component,
            "message": item.message,
            "units": list(item.block_ids),
        }
    if len(line) > MAX_RECORD_CHARS:
        raise ValueError
    source, match = None, OPENSTACK.fullmatch(line)
    if not match:
        split = FIRST_TOKEN.fullmatch(line)
        if split and ".log" in split.group(1):
            source, match = split.group(1), OPENSTACK.fullmatch(split.group(2))
    if not match:
        raise ValueError
    stamp, process, level, component, message = match.groups()
    datetime.fromisoformat(stamp)
    return {
        "source": source,
        "timestamp_raw": stamp,
        "process": process,
        "level": level,
        "component": component,
        "message": message,
        "request_ids": REQUEST.findall(message),
        "units": list(dict.fromkeys(INSTANCE.findall(message))),
    }


def structured(row):
    message = row.get("message")
    if not isinstance(message, str):
        raise ValueError
    return {
        key: row[key] for key in ("timestamp", "level", "host", "message") if isinstance(row.get(key), str)
    }


def evaluate(text, unit):
    if unit not in ("event", "hdfs_block", "openstack_instance"):
        raise WorkspaceError("Choose an evaluation unit that matches the prediction file.")
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames or not {"unit_id", "label", "prediction"}.issubset(reader.fieldnames):
        raise WorkspaceError("Evaluation CSV needs unit_id,label,prediction columns.", 422)
    counts = Counter()
    seen = set()
    for row in reader:
        key = row["unit_id"]
        label, prediction = row["label"], row["prediction"]
        if not key or key in seen or label not in ("0", "1") or prediction not in ("0", "1"):
            raise WorkspaceError("Each unit needs a unique ID and a label/prediction of 0 or 1.", 422)
        if unit == "hdfs_block" and not BLOCK.fullmatch(key):
            raise WorkspaceError("HDFS IDs must be block IDs.", 422)
        if unit == "openstack_instance":
            from uuid import UUID

            try:
                if str(UUID(key)) != key:
                    raise ValueError
            except ValueError:
                raise WorkspaceError("OpenStack IDs must be VM UUIDs.", 422) from None
        seen.add(key)
        counts[label, prediction] += 1
    if not seen:
        raise WorkspaceError("The evaluation file has no data.", 422)
    tp, fp, fn, tn = (counts[pair] for pair in (("1", "1"), ("0", "1"), ("1", "0"), ("0", "0")))

    def ratio(a, b):
        return a / b if b else None

    return {
        "unit": unit,
        "units": len(seen),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "f1": ratio(2 * tp, 2 * tp + fp + fn),
        "fpr": ratio(fp, fp + tn),
    }


def analyze(text, format_name, unit=None):
    if format_name == "evaluation":
        return evaluate(text, unit)
    if format_name not in ("hdfs", "openstack", "jsonl", "csv"):
        raise WorkspaceError("Choose HDFS, OpenStack, JSONL, CSV or evaluation CSV.")
    # Physical lines only: str.splitlines() also breaks on \x85, \u2028 and form feeds inside a record.
    source = (
        csv.DictReader(StringIO(text), strict=True)
        if format_name == "csv"
        else [line.removesuffix("\r") for line in text.split("\n")[: -1 if text.endswith("\n") else None]]
    )
    counts = Counter()
    sample = []
    units = set()
    malformed = 0
    try:
        for index, line in enumerate(source, 1):
            if isinstance(line, str) and not line.strip():
                continue
            try:
                parsed = structured(line) if format_name == "csv" else parse_line(line, format_name)
            except (ValueError, RecursionError):
                malformed += 1
                continue
            level = parsed.get("level", "").upper()
            counts[
                level
                if level in {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"}
                else "unknown"
            ] += 1
            units.update(parsed.get("units", ()))
            if len(sample) < 30:
                sample.append({"record": index, **parsed})
    except csv.Error:
        raise WorkspaceError("CSV syntax is invalid.", 422) from None
    return {
        "format": format_name,
        "events": sum(counts.values()),
        "malformed": malformed,
        "severity": dict(counts),
        "distinct_unit_ids": len(units) if format_name in ("hdfs", "openstack") else None,
        "unit": {"hdfs": "hdfs_block", "openstack": "openstack_instance"}.get(format_name, "event"),
        "preview": sample,
    }
