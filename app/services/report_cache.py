"""A small in-process cache for reports that scan a whole dataset (data quality, Log Explorer insights).

Entries are keyed by what the report depends on, such as the dataset's ``input_revision`` (raised by every
import batch) and its newest anomaly id, so a changed dataset is recomputed on the next request and an
unchanged one is served at once. Each server or worker process keeps its own small LRU.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Hashable
import copy
from threading import Lock
from typing import Any, TypeVar

T = TypeVar("T")
SIZE = 64

_entries: OrderedDict[Hashable, Any] = OrderedDict()
_lock = Lock()


def cached(key: Hashable, compute: Callable[[], T]) -> T:
    """``compute()`` once per key; callers get a deep copy, so changing a result never edits the cache."""
    with _lock:
        if key in _entries:
            _entries.move_to_end(key)
            return copy.deepcopy(_entries[key])
    value = compute()
    with _lock:
        _entries[key] = value
        _entries.move_to_end(key)
        while len(_entries) > SIZE:
            _entries.popitem(last=False)
    return copy.deepcopy(value)


def clear() -> None:
    with _lock:
        _entries.clear()
