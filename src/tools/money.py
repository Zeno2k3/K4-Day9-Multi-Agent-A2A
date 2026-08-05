"""Integer-cent money math to avoid float rounding artifacts (e.g. 18.269999999999996)."""
from __future__ import annotations

from collections.abc import Iterable


def to_cents(value: float) -> int:
    return round(value * 100)


def cents_to_float(cents: int) -> float:
    return round(cents / 100.0, 2)


def sum_cents(values: Iterable[float]) -> int:
    return sum(to_cents(v) for v in values)
