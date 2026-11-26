"""Retention policy: decide which snapshots to keep (grandfather-father-son)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TypeVar

from dualvault.config import Retention

T = TypeVar("T")


def _bucket_keys() -> list[tuple[str, Callable[[datetime], tuple]]]:
    return [
        ("keep_daily", lambda d: (d.year, d.month, d.day)),
        ("keep_weekly", lambda d: d.isocalendar()[:2]),
        ("keep_monthly", lambda d: (d.year, d.month)),
    ]


def select_to_keep(
    items: Iterable[T], timestamp: Callable[[T], datetime], policy: Retention
) -> set[int]:
    """Return the indexes (in the given iterable) of items that must be kept.

    * ``keep_last``: the N most recent snapshots.
    * ``keep_daily/weekly/monthly``: the most recent snapshot of each of the
      last N days/weeks/months that have at least one snapshot.
    """
    items = list(items)
    order = sorted(range(len(items)), key=lambda i: timestamp(items[i]), reverse=True)
    keep: set[int] = set(order[: policy.keep_last])
    for attr, key in _bucket_keys():
        limit = getattr(policy, attr)
        seen: set[tuple] = set()
        for i in order:
            if len(seen) >= limit:
                break
            k = key(timestamp(items[i]))
            if k not in seen:
                seen.add(k)
                keep.add(i)
    return keep


def split(
    items: Iterable[T], timestamp: Callable[[T], datetime], policy: Retention
) -> tuple[list[T], list[T]]:
    """Return ``(keep, delete)`` lists, newest first."""
    items = sorted(items, key=timestamp, reverse=True)
    keep_idx = select_to_keep(items, timestamp, policy)
    keep = [x for i, x in enumerate(items) if i in keep_idx]
    delete = [x for i, x in enumerate(items) if i not in keep_idx]
    return keep, delete
