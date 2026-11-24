"""Loghub HDFS_v1 records. The source wall clock has no supplied time zone."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
import re

BLOCK = re.compile(r"\bblk_-?[0-9]+\b", re.ASCII)
HEADER = re.compile(r"([0-9]{6})\s+([0-9]{6})\s+([0-9]+)\s+(\w+)\s+([^:]+):\s*(.*)", re.ASCII)
EPOCH = datetime(1970, 1, 1)
MAX_LINE = 256 * 1024


@lru_cache(maxsize=16384)
def wall_seconds(date, time):
    value = datetime.strptime(date + time, "%y%m%d%H%M%S")
    return (value - EPOCH) // timedelta(seconds=1)


def wall_iso(seconds):
    return (EPOCH + timedelta(seconds=seconds)).isoformat()


@dataclass(frozen=True, slots=True)
class Record:
    timestamp_raw: str
    wall_seconds: int
    thread: str
    level: str
    component: str
    message: str
    block_ids: tuple[str, ...]


def parse_hdfs(line):
    match = HEADER.fullmatch(line)
    if not match:
        raise ValueError("Invalid HDFS header.")
    date, time, thread, level, component, message = match.groups()
    return Record(
        date + " " + time,
        wall_seconds(date, time),
        thread,
        level,
        component,
        message,
        tuple(dict.fromkeys(BLOCK.findall(message))),
    )


def physical_lines(stream):
    """Yield (physical line number, bytes or None) without buffering oversized lines."""
    line_number = 0
    while raw := stream.readline(MAX_LINE + 1):
        line_number += 1
        if len(raw) <= MAX_LINE:
            yield line_number, raw
            continue
        while raw and not raw.endswith(b"\n"):
            raw = stream.readline(MAX_LINE + 1)
        yield line_number, None
