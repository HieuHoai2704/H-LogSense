"""Loghub BGL parser. Epoch is authoritative; printed local time is preserved."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import BinaryIO, Iterator

VERSION = "bgl-1.0.0"
MAX_LINE_BYTES = 262144


@dataclass(frozen=True)
class BGLRecord:
    line_number: int
    byte_offset: int
    raw: bytes
    timestamp: datetime | None = None
    label: str | None = None
    host: str | None = None
    message: str | None = None
    attributes: dict | None = None
    error: str | None = None


def parse_line(raw: bytes, line_number: int, byte_offset: int) -> BGLRecord:
    if line_number < 1 or byte_offset < 0:
        raise ValueError("Invalid provenance.")
    base = dict(line_number=line_number, byte_offset=byte_offset, raw=raw)
    if len(raw) > MAX_LINE_BYTES:
        raise ValueError("BGL line exceeds the configured byte limit.")
    try:
        text = raw.decode("utf-8", errors="strict").rstrip("\r\n")
    except UnicodeDecodeError:
        return BGLRecord(**base, error="invalid_utf8")
    # Label, epoch, date, Node, printed time, NodeRepeat, type, component, level, content.
    fields = text.split(maxsplit=9)
    if len(fields) != 10:
        return BGLRecord(**base, error="invalid_field_count")
    (
        label,
        epoch,
        date,
        node,
        printed_time,
        node_repeat,
        facility,
        component,
        level,
        message,
    ) = fields
    try:
        if not epoch.isascii() or not epoch.isdigit():
            raise ValueError()
        timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=int(epoch)
        )
        datetime.strptime(date, "%Y.%m.%d")
        datetime.strptime(printed_time, "%Y-%m-%d-%H.%M.%S.%f")
    except (ValueError, OverflowError):
        return BGLRecord(**base, error="invalid_timestamp")
    if any(
        len(x) > limit
        for x, limit in ((label, 128), (node, 128), (component, 128), (level, 32))
    ):
        return BGLRecord(**base, error="field_too_long")
    return BGLRecord(
        **base,
        timestamp=timestamp,
        label=label,
        host=None if node == "-" else node,
        message=message,
        attributes={
            "epoch": epoch,
            "printed_timestamp": printed_time,
            "date": date,
            "node": node,
            "node_repeat": node_repeat,
            "facility": facility,
            "component": component,
            "level": level,
            "timestamp_policy": "epoch_seconds_utc",
        },
    )


def iter_records(
    stream: BinaryIO, *, first_line=1, byte_offset=0
) -> Iterator[BGLRecord]:
    """Read bounded physical lines. Offset is relative to the uncompressed member.

    Oversized lines abort without advancing a persistent checkpoint. They are not
    silently truncated or decoded lossily. A missing final newline is supported.
    """
    line = first_line
    offset = byte_offset
    while True:
        raw = stream.readline(MAX_LINE_BYTES + 1)
        if not raw:
            return
        yield parse_line(raw, line, offset)
        offset += len(raw)
        line += 1
