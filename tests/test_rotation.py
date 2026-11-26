from datetime import datetime, timedelta, timezone

from dualvault.config import Retention
from dualvault.rotation import split


def ts(x):
    return x


def test_keep_last_only():
    now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    items = [now - timedelta(hours=i) for i in range(10)]
    keep, delete = split(
        items, ts, Retention(keep_last=3, keep_daily=0, keep_weekly=0, keep_monthly=0)
    )
    assert keep == items[:3]
    assert len(delete) == 7


def test_daily_keeps_newest_per_day():
    base = datetime(2026, 1, 31, 23, tzinfo=timezone.utc)
    items = [base - timedelta(hours=6 * i) for i in range(20)]  # 4 per day, 5 days
    keep, _ = split(items, ts, Retention(keep_last=0, keep_daily=3, keep_weekly=0, keep_monthly=0))
    assert len(keep) == 3
    assert len({k.date() for k in keep}) == 3
    for k in keep:  # newest snapshot of its day
        assert all(i <= k for i in items if i.date() == k.date())


def test_monthly_and_never_empty():
    base = datetime(2026, 6, 15, tzinfo=timezone.utc)
    items = [base - timedelta(days=10 * i) for i in range(40)]
    keep, delete = split(
        items, ts, Retention(keep_last=1, keep_daily=0, keep_weekly=0, keep_monthly=6)
    )
    assert items[0] in keep
    assert len({(k.year, k.month) for k in keep}) == 6
    assert len(keep) + len(delete) == 40
