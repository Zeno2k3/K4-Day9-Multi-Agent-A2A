"""Deterministic Payment Agent tools.

Scoped data: order_payments.csv rows for the claimed order, plus the
item_total_brl/freight_total_brl numbers handed off by the Order & Product
Agent (this agent does not re-derive items itself).
"""
from __future__ import annotations

from src.config import MAX_PAYMENT_IDS, RECONCILE_TOLERANCE_CENTS
from src.schemas.records import PaymentRecord
from src.tools.money import cents_to_float, sum_cents, to_cents


def build_payment_ids(order_id: str, payments: list[PaymentRecord]) -> list[str]:
    return [f"{order_id}:{p.payment_sequential}" for p in payments][:MAX_PAYMENT_IDS]


def build_payment_types(payments: list[PaymentRecord]) -> list[str]:
    seen: list[str] = []
    for p in payments:
        if p.payment_type not in seen:
            seen.append(p.payment_type)
    return seen


def compute_payment_total_brl(payments: list[PaymentRecord]) -> float:
    return cents_to_float(sum_cents(p.payment_value for p in payments))


def compute_reconciliation(
    item_total_brl: float,
    freight_total_brl: float,
    payment_total_brl: float,
    has_items: bool,
) -> tuple[float | None, float | None, bool | None]:
    """Returns (expected_total_brl, difference_brl, reconciled).

    All three are None when the order has zero item rows (README §4: an
    itemless order cannot have an expected total to reconcile against).
    """
    if not has_items:
        return None, None, None
    expected_cents = to_cents(item_total_brl) + to_cents(freight_total_brl)
    payment_cents = to_cents(payment_total_brl)
    diff_cents = payment_cents - expected_cents
    reconciled = abs(diff_cents) <= RECONCILE_TOLERANCE_CENTS
    return cents_to_float(expected_cents), cents_to_float(diff_cents), reconciled
