"""Timestamp parsing and hour-variance math shared by delivery/policy tools.

Timestamps are always kept as the raw CSV string for output; datetime
parsing here is only ever used for arithmetic, never for re-formatting the
value that gets written to output/EC_0NN.json.
"""
from __future__ import annotations

from datetime import datetime

_FMT = "%Y-%m-%d %H:%M:%S"


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, _FMT)


def hours_between(later: str | None, earlier: str | None) -> float | None:
    """(later - earlier) in hours, rounded to 2dp. None if either side is missing."""
    later_dt = parse_ts(later)
    earlier_dt = parse_ts(earlier)
    if later_dt is None or earlier_dt is None:
        return None
    delta = later_dt - earlier_dt
    return round(delta.total_seconds() / 3600.0, 2)
