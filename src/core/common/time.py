from __future__ import annotations

"""Canonical UTC helpers for core-first runtime code.

These helpers keep backward-compatible string formats that previously relied on
legacy naive-UTC clock calls while switching the actual clock source to timezone-aware
UTC datetimes.
"""

from datetime import date, datetime, timezone

UTC = timezone.utc


def utc_now() -> datetime:
    """Return a timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC.

    Naive datetimes are treated as already being in UTC to preserve legacy
    legacy naive-UTC semantics used across the project.
    """

    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def utc_now_seconds() -> datetime:
    """Return current UTC datetime rounded to seconds."""
    return utc_now().replace(microsecond=0)


def utc_date(dt: datetime | None = None) -> date:
    return ensure_utc(dt or utc_now()).date()


def utc_date_str(dt: datetime | None = None) -> str:
    return utc_date(dt).isoformat()


def utc_timestamp_compact(dt: datetime | None = None) -> str:
    """Return legacy compact UTC timestamp: YYYYmmdd_HHMMSS."""
    return ensure_utc(dt or utc_now()).strftime("%Y%m%d_%H%M%S")


def utc_isoformat(dt: datetime | None = None) -> str:
    """Return UTC ISO timestamp with +00:00 offset and second precision."""
    return ensure_utc(dt or utc_now()).replace(microsecond=0).isoformat()


def utc_isoformat_z(dt: datetime | None = None) -> str:
    """Return UTC ISO timestamp with trailing Z and second precision."""
    return utc_isoformat(dt).replace("+00:00", "Z")


__all__ = [
    "UTC",
    "ensure_utc",
    "utc_date",
    "utc_date_str",
    "utc_isoformat",
    "utc_isoformat_z",
    "utc_now",
    "utc_now_seconds",
    "utc_timestamp_compact",
]
