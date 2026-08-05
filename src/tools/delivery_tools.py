"""Deterministic Delivery Agent tools.

Scoped data: the order's 5 timestamp fields, plus each item's seller_id and
shipping_limit_date only (price/product data is out of scope for this
agent, even though the same DataStore object is injected — see
architecture.md's access matrix).
"""
from __future__ import annotations

from src.config import MAX_SELLER_IDS
from src.schemas.handoff_models import SellerHandoffFact
from src.schemas.records import ItemRecord
from src.tools.time_utils import hours_between, parse_ts


def compute_delivery_variance_hours(delivered_at: str | None, estimated_at: str | None) -> float | None:
    return hours_between(delivered_at, estimated_at)


def compute_is_late_delivery(delivery_variance_hours: float | None) -> bool | None:
    if delivery_variance_hours is None:
        return None
    return delivery_variance_hours > 0


def compute_seller_handoff(
    items: list[ItemRecord], carrier_handoff_at: str | None
) -> list[SellerHandoffFact]:
    """Groups items by seller_id, using the EARLIEST shipping_limit_date per
    seller (a seller with multiple items only needs to hand off by the time
    their first-due item is due)."""
    earliest_by_seller: dict[str, str] = {}
    seen_sellers: set[str] = set()
    seen_order: list[str] = []
    for item in items:
        if item.seller_id not in seen_sellers:
            seen_sellers.add(item.seller_id)
            seen_order.append(item.seller_id)
        if item.shipping_limit_date is None:
            continue
        current = earliest_by_seller.get(item.seller_id)
        if current is None or parse_ts(item.shipping_limit_date) < parse_ts(current):
            earliest_by_seller[item.seller_id] = item.shipping_limit_date

    results: list[SellerHandoffFact] = []
    for seller_id in seen_order:
        shipping_limit_at = earliest_by_seller.get(seller_id)
        variance = hours_between(carrier_handoff_at, shipping_limit_at)
        late = variance is not None and variance > 0
        results.append(
            SellerHandoffFact(
                seller_id=seller_id,
                shipping_limit_at=shipping_limit_at,
                handoff_variance_hours=variance,
                late_handoff=late,
            )
        )
    return results


def late_handoff_seller_ids(seller_handoffs: list[SellerHandoffFact]) -> list[str]:
    return [s.seller_id for s in seller_handoffs if s.late_handoff][:MAX_SELLER_IDS]
