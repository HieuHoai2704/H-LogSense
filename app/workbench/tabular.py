"""Bounded, read-only data profiling for local workbench files."""

from collections import Counter
import csv
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import json
import math
import re

from .files import WorkspaceError

MAX_ROWS = 5000
MAX_COLUMNS = 64
PREVIEW_ROWS = 20
PARQUET_FILE_BYTES = 256 * 1024 * 1024
PARQUET_DECODE_BYTES = 24 * 1024 * 1024
NUMERIC = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)


def column_names(names):
    if len(names) > MAX_COLUMNS or any(not name.strip() or len(name) > 200 for name in names) or len(set(names)) != len(names):
        raise WorkspaceError("Up to 64 unique, non-empty column names of at most 200 characters are required.", 422)
    return list(names)


def csv_rows(text):
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    fields = column_names(next(reader, []))
    for row in reader:
        if row:
            yield dict(zip(fields, (value if value != "" else None for value in row))) if len(row) == len(fields) else None


def invalid_number(value):
    raise ValueError(value)


def jsonl_rows(text):
    for line in StringIO(text):
        if line.strip():
            try:
                row = json.loads(line, parse_constant=invalid_number)
                yield row if isinstance(row, dict) else None
            except (ValueError, RecursionError):
                yield None


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str, separators=(",", ":"))


def short(value, limit=160):
    text = value if isinstance(value, str) else encoded(value)
    return text if len(text) <= limit else text[:limit] + "…"


def observed_type(value, is_csv):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float, Decimal)) or (is_csv and NUMERIC.fullmatch(value.strip())):
        return "number"
    return {str: "text", list: "array", dict: "object"}.get(type(value), type(value).__name__)


def distribution(values, kind):
    if kind == "number":
        numeric = []
        for value in values:
            try:
                number = float(value)
            except (ValueError, OverflowError):
                continue
            if math.isfinite(number):
                numeric.append(number)
        if numeric:
            low, high = min(numeric), max(numeric)
            if low == high:
                return {"kind": "histogram", "min": low, "max": high, "counts": [len(numeric)]}
            scale = max(abs(low), abs(high))
            start, end = low / scale, high / scale
            counts = [0] * 8
            for value in numeric:
                index = int((value / scale - start) / (end - start) * len(counts))
                counts[max(0, min(index, len(counts) - 1))] += 1
            return {"kind": "histogram", "min": low, "max": high, "counts": counts}
    if kind in {"text", "boolean", "mixed"}:
        values = Counter((encoded(value), short(value)) for value in values if isinstance(value, (str, bool, int, float)))
        return {"kind": "top", "values": [{"label": label, "count": count} for (_, label), count in values.most_common(8)]}
    return None


def summarize(source, format_name, fields=None, total=None, bounded=False):
    fields = fields or {}
    records = []
    scanned = malformed = duplicates = 0
    seen = set()
    columns = dict.fromkeys(fields)
    for row in source:
        if scanned == MAX_ROWS:
            bounded = True
            break
        scanned += 1
        if row is None:
            malformed += 1
            continue
        try:
            digest = sha256(encoded(row).encode("ascii")).digest()
        except (RecursionError, ValueError):
            malformed += 1
            continue
        new_names = [name for name in row if name not in columns]
        if new_names:
            columns.update(dict.fromkeys(column_names([*columns, *new_names])))
        duplicates += digest in seen
        seen.add(digest)
        records.append(row)
    summaries = []
    for name in columns:
        values = [row[name] for row in records if row.get(name) is not None]
        types = sorted({observed_type(value, format_name == "csv") for value in values})
        kind = types[0] if len(types) == 1 else "mixed" if types else "unknown"
        summaries.append({"name": name, "type": fields.get(name) or kind, "observed_types": types,
                          "missing": len(records) - len(values), "distribution": distribution(values, kind)})
    return {"format": format_name, "scanned_rows": scanned, "valid_rows": len(records), "malformed_rows": malformed,
            "duplicate_rows": duplicates, "total_rows": total if total is not None else None if bounded else scanned,
            "sampled": bounded or (total is not None and total > scanned), "columns": summaries,
            "preview": [[None if row.get(name) is None else short(row[name]) for name in columns]
                        for row in records[:PREVIEW_ROWS]]}


def text_profile(text, format_name):
    if format_name == "jsonl":
        return summarize(jsonl_rows(text), format_name)
    # Read the header separately so a header-only CSV still exposes its schema.
    try:
        header = next(csv.reader(StringIO(text, newline=""), strict=True), [])
        return summarize(csv_rows(text), format_name, dict.fromkeys(column_names(header)))
    except (csv.Error, RecursionError):
        raise WorkspaceError("CSV syntax is invalid.", 422) from None


def parquet_profile(path):
    try:
        import pyarrow
        from pyarrow import parquet
    except ImportError:
        raise WorkspaceError("Install requirements-workbench.txt to read Parquet.", 503) from None
    with path.open("rb") as stream:
        stream.seek(0, 2)
        if stream.tell() > PARQUET_FILE_BYTES:
            raise WorkspaceError("Parquet exceeds the 256 MiB preview limit.", 413)
        stream.seek(0)
        try:
            with parquet.ParquetFile(stream, thrift_string_size_limit=8 * 1024 * 1024,
                                     thrift_container_size_limit=200_000,
                                     arrow_extensions_enabled=False) as file:
                schema = file.schema_arrow
                fields = {name: str(schema.field(name).type) for name in column_names(schema.names)}
                groups, rows, decoded = [], 0, 0
                for index in range(file.num_row_groups):
                    group = file.metadata.row_group(index)
                    decoded += group.total_byte_size
                    if decoded > PARQUET_DECODE_BYTES or rows >= MAX_ROWS:
                        break
                    groups.append(index)
                    rows += group.num_rows
                records = (row for batch in file.iter_batches(batch_size=128, row_groups=groups, use_threads=False)
                           for row in batch.to_pylist())
                return summarize(records, "parquet", fields, total=file.metadata.num_rows)
        except (pyarrow.ArrowException, ValueError, OverflowError, RecursionError):
            raise WorkspaceError("Could not read the Parquet file, or its schema exceeds the preview limit.", 422) from None
