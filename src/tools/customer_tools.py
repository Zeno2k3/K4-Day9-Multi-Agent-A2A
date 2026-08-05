"""Deterministic Customer Agent tools.

Scoped data: customers.csv + the orders->customer_unique_id index. No
items/payments/products access.
"""
from __future__ import annotations

from src.config import MAX_RELATED_ORDER_IDS
from src.data.loader import DataStore


def resolve_customer_unique_id(ds: DataStore, customer_id: str) -> str | None:
    customer = ds.customers_by_id.get(customer_id)
    return customer.customer_unique_id if customer else None


def fetch_related_order_ids(
    ds: DataStore, customer_unique_id: str, exclude_order_id: str
) -> list[str]:
    """Other orders by the same person, oldest purchase first, excluding the
    claimed order itself. Ordering by order_purchase_timestamp ascending is
    a documented assumption (README does not specify order) — see
    architecture.md."""
    entries = ds.orders_by_unique_id.get(customer_unique_id, [])
    others = [(oid, ts) for oid, ts in entries if oid != exclude_order_id]
    others.sort(key=lambda pair: pair[1])
    return [oid for oid, _ts in others][:MAX_RELATED_ORDER_IDS]


def is_repeat_customer(related_order_ids: list[str]) -> bool:
    return len(related_order_ids) > 0
