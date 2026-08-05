"""Deterministic Order & Product Agent tools.

Scoped data: the claimed order's own row, its items, and the products/
sellers/categories referenced by those items. No customer or payment access.
"""
from __future__ import annotations

from src.config import (
    CATEGORY_NAME_LANGUAGE,
    MAX_CATEGORY_NAMES,
    MAX_ITEM_IDS,
    MAX_PRODUCT_IDS,
    MAX_SELLER_IDS,
)
from src.data.loader import DataStore
from src.schemas.handoff_models import OrderCore
from src.schemas.records import ItemRecord
from src.tools.money import cents_to_float, sum_cents


def fetch_order_core(ds: DataStore, order_id: str) -> OrderCore | None:
    order = ds.orders.get(order_id)
    if order is None:
        return None
    return OrderCore(
        order_id=order.order_id,
        customer_id=order.customer_id,
        order_status=order.order_status,
        order_purchase_timestamp=order.order_purchase_timestamp,
        order_approved_at=order.order_approved_at,
        order_delivered_carrier_date=order.order_delivered_carrier_date,
        order_delivered_customer_date=order.order_delivered_customer_date,
        order_estimated_delivery_date=order.order_estimated_delivery_date,
    )


def fetch_items(ds: DataStore, order_id: str) -> list[ItemRecord]:
    return ds.items_by_order.get(order_id, [])


def _dedupe_capped(values: list[str], cap: int) -> list[str]:
    seen: list[str] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return seen[:cap]


def build_item_ids(order_id: str, items: list[ItemRecord]) -> list[str]:
    return [f"{order_id}:{i.order_item_id}" for i in items][:MAX_ITEM_IDS]


def build_seller_ids(items: list[ItemRecord]) -> list[str]:
    return _dedupe_capped([i.seller_id for i in items], MAX_SELLER_IDS)


def build_product_ids(items: list[ItemRecord]) -> list[str]:
    return _dedupe_capped([i.product_id for i in items], MAX_PRODUCT_IDS)


def _category_name(ds: DataStore, item: ItemRecord) -> str | None:
    """Single source of truth for how a category is rendered, so the
    category_names array and the multiple_categories secondary issue can
    never disagree about what counts as a distinct category."""
    product = ds.products_by_id.get(item.product_id)
    pt_name = product.product_category_name if product else None
    if CATEGORY_NAME_LANGUAGE == "en":
        return ds.translate_category(pt_name)
    return pt_name


def build_category_names(ds: DataStore, items: list[ItemRecord]) -> list[str]:
    names: list[str] = []
    for item in items:
        name = _category_name(ds, item)
        if name:
            names.append(name)
    return _dedupe_capped(names, MAX_CATEGORY_NAMES)


def compute_item_total_brl(items: list[ItemRecord]) -> float:
    return cents_to_float(sum_cents(i.price for i in items))


def compute_freight_total_brl(items: list[ItemRecord]) -> float:
    return cents_to_float(sum_cents(i.freight_value for i in items))


def distinct_seller_count(items: list[ItemRecord]) -> int:
    return len({i.seller_id for i in items})


def distinct_category_count(ds: DataStore, items: list[ItemRecord]) -> int:
    return len({name for item in items if (name := _category_name(ds, item))})
